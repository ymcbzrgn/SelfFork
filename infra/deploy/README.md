# SelfFork v3 — Self-Host on a Linux Server

A single Docker container brings up the entire SelfFork stack:

- **FastAPI orchestrator** at `http://<server>:8765` — REST + WebSocket
- **Next.js cockpit** served from the same port — your browser UI
- **CLI fleet** (claude-code, codex, gemini-cli) installed inside
- **Playwright + chromium** for browser-driven CLI sign-in flows
- **xvfb** for the rare CLI that insists on a display

The **model lives external**. Point `MODEL_ENDPOINT` at your lab Mac,
GPU rental, or any OpenAI-compatible / Ollama / MLX-server host. CPU-
only deploys are fully supported — the orchestrator is light; the
model is the heavy bit and it's somebody else's problem.

## 1. Prerequisites

A Linux server with:
- Docker 24+ and the Compose plugin
- 4 vCPU + 8 GB RAM minimum (the orchestrator is light; CLI subprocesses + RAG ingest are the load)
- 20 GB disk (most goes to workspace files + audit logs + Mind RAG db)
- A public IP **or** a reverse-proxy that terminates TLS for you
  (Caddy, Traefik, Cloudflare Tunnel — your call)

The cockpit ships **no authentication** in v3 — protect the port at
the network layer. If you must expose `8765` directly to the internet,
do not. Use a private VPN (Tailscale recommended) or a reverse proxy
with auth in front.

## 2. Quick start

```bash
git clone https://github.com/<owner>/selffork.git
cd selffork/infra/deploy

cp .env.example .env
nano .env                                 # set MODEL_ENDPOINT at minimum

docker compose build                      # ~8 min on first build (Playwright + CLI installs)
docker compose up -d
docker compose logs -f selffork           # tail orchestrator stdout
```

Open `http://<server>:8765/` in your browser. The Connections page
walks you through signing in to each CLI provider.

## 3. Model endpoint scenarios

### A — Lab Mac via Tailscale (CPU server, model on Mac)
On the Mac:
```bash
mlx_vlm.server --model mlx-community/gemma-4-26b-a4b-it-4bit --port 8080
```
On the SelfFork host `.env`:
```
MODEL_ENDPOINT=http://100.x.x.x:8080      # your Mac's Tailscale IP
MODEL_PROTOCOL=mlx
```

### B — GPU rental (Hetzner / RunPod / Lambda)
On the GPU host run an inference server, then:
```
MODEL_ENDPOINT=https://gpu.example.com:8080
MODEL_PROTOCOL=openai                     # most rentals expose OpenAI-compat
```

### C — Same-host Ollama (single beefy box)
```
MODEL_ENDPOINT=http://host.docker.internal:11434
MODEL_PROTOCOL=ollama
MODEL_NAME=gemma3:27b                     # whatever you've pulled
```

### D — Anthropic API fallback (no trained adapter; emergency mode)
Set in Settings → Model Endpoint instead of `.env`, since this needs
an API key:
```
MODEL_ENDPOINT=https://api.anthropic.com
MODEL_PROTOCOL=openai                     # via your gateway
```
This loses the operator's fine-tuned reflex; use sparingly.

## 4. Telegram bridge (optional)

The destructive-action soft confirmation (ADR-006 §4.5) routes
through Telegram. To enable:

1. Talk to **@BotFather** on Telegram, create a bot, copy the token.
2. Set `TELEGRAM_BOT_TOKEN` in `.env`.
3. Set `TELEGRAM_WEBHOOK_URL` to your public-facing URL ending in
   `/api/telegram/webhook` (your reverse proxy → SelfFork).
4. `docker compose restart selffork`.

The cockpit Connections page surfaces "Connected as @<your_handle>"
once the webhook handshake completes.

## 5. Volumes & state

| Volume | Path inside container | Contents |
|---|---|---|
| `selffork-auth` | `/opt/selffork/.config/selffork` | CLI sign-in cookies. Persists across restarts so you sign in once. |
| `selffork-data` | `/opt/selffork/.selffork` | Workspaces, kanban DB, audit log, Mind RAG (`projects/`, `audit/`, `mind/`). |

Both are named Docker volumes. Back them up the usual way
(`docker run --rm -v selffork-data:/data -v $(pwd):/backup alpine tar czf /backup/selffork-data.tar.gz -C / data`).

## 6. Updating

```bash
git pull
docker compose build
docker compose up -d
```

Workspace state survives the rebuild because it lives in the named
volume, not the image.

### 6.1 CodexBar CLI (vendored quota sidecar)

The image ships the [CodexBar](https://github.com/steipete/CodexBar) CLI
binary as a sha256-pinned secondary quota source (ADR-007 §4 S-Quota,
`[[codexbar-adoption-2026-05-22]]`). The pin lives in
`infra/deploy/codexbar/manifest.toml`; the `Dockerfile` runs
`infra/deploy/scripts/install-codexbar.sh` at build time to verify and
extract the binary into `/usr/local/bin/codexbar`.

**Bumping the version:** before the first build (and on each upstream
release) the checksums in the manifest must be populated. Run:

```bash
./infra/deploy/scripts/refresh-codexbar-checksums.sh v0.27.0
# or dry-run:
./infra/deploy/scripts/refresh-codexbar-checksums.sh v0.27.0 --dry-run
```

This downloads every platform tarball, computes the sha256, and rewrites
the manifest in place. **S-Quota Wave 2** automates this with
`.github/workflows/codexbar-watch.yml` — every Monday the workflow
queries `steipete/CodexBar` releases, diffs against the pin, and opens
an auto-bump PR when a new tag drops. The PR carries a reviewer
checklist (manifest diff + local smoke + upstream CHANGELOG scan).
Manual dispatch with a specific version is also supported.

**Local-dev install (no Docker):**

```bash
./infra/deploy/scripts/install-codexbar.sh --prefix ~/.local/bin
# or, if checksums aren't pinned yet:
./infra/deploy/scripts/install-codexbar.sh --prefix ~/.local/bin --no-verify
```

The dashboard auto-detects `codexbar` on `PATH`. Disable the sidecar
entirely with `SELFFORK_CODEXBAR_ENABLED=false`.

## 7. Going bare-metal (no Docker)

The container is a convenience; the orchestrator runs natively just
fine. Reference the `Dockerfile` for the dependency list:
- Python 3.12 with `uv pip install -e packages/{orchestrator,body,reflex}`
- Node 20 with `pnpm install && pnpm build` in `apps/web/`
- The CLI binaries installed globally
- `playwright install chromium`
- `xvfb` if you want headless browser flows

Then `selffork ui --host 0.0.0.0 --port 8765`.

## 8. Hardening checklist

Before pointing this at production data:
- [ ] Put a reverse proxy with auth (basic, OAuth, mTLS) in front of port 8765
- [ ] Or restrict access to a private VPN (Tailscale, WireGuard)
- [ ] Configure the destructive whitelist (`Settings → Telegram bridge → Open editor`) to your stack
- [ ] Verify Telegram webhook works end-to-end (the soft-confirm is useless if you can't approve)
- [ ] Snapshot the `selffork-data` volume on a cron (workspace state is what you cannot regenerate)

See `docs/decisions/ADR-006_v2_Pivot.md` for the full deployment rationale.
