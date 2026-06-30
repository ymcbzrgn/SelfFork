# Claude Code Data Recovery & Handover Kit

> **Purpose.** Preserve **all Claude Code (terminal CLI) data** from a machine that is
> about to be wiped (e.g. a departing teammate's company laptop) onto a portable
> drive, so the conversation history, tool-call transcripts and distilled memory can
> be archived and later ingested into SelfFork's **Mind** RAG pillar.
>
> This folder does **not** modify any existing SelfFork code. The design is below;
> the **implemented collector** lives in [`tool/`](tool/) (Go, single `.exe`) with
> its own [build & usage guide](tool/README.md). The shipped binary is
> `tool/dist/ClaudeBackup.exe`.
>
> **Status (2026-06-30): implemented & tested.** Decisions in
> [§11](#11-open-decisions-to-settle-before-building) are locked; the tool builds
> clean (`go vet` ✓) and was validated by a real-copy test (quarantine + redaction
> + sha256 checksums + live % progress all verified) and a full dry-run over this
> machine (10,819 files / 3.41 GB discovered).
>
> **Locked choices (2026-06-30):** **Go** single static binary · secrets mode **`safe`**
> (quarantine + redact) · scope **`full`** (~3.5 GB, includes rebuildable caches) ·
> auto-run with **live % progress** (§10).

---

## 0. Özet (TR)

Ayrılan ekip arkadaşının bilgisayarı sıfırlanmadan önce, **tüm disklerdeki** ve
(yetki varsa) **tüm kullanıcı profillerindeki** Claude Code verisini bir flash belleğe
almak için tasarlanmış taşınabilir bir yedekleme aracının planıdır.

- **İki katman var:** (1) **merkezî/global** veri (`~/.claude`, `~/.claude.json`,
  `~/.claude-mem`) ve (2) **proje-içi** artefaktlar (her repoda `.claude/`,
  `CLAUDE.md`, `.mcp.json`) — bunlar tüm sürücülere serpilmiş durumda.
- **Altın madeni:** `~/.claude/projects/` (tüm konuşma + tool-call transkriptleri).
- **Duruş:** Şeffaf, denetlenebilir, **stealth yok**. Canlı kimlik bilgileri (OAuth
  token) varsayılan olarak ayrı/işaretli tutulur. Yalnızca **yetkili** olduğun
  makinelerde çalıştır.

> **Not (Anthropic koruması):** Bu aracı kötü-amaçlı-yazılım kalıplarıyla (AV/SmartScreen
> atlatma, kilitli dosyaları shadow-copy ile sızdırma, gizli çalışma) **kurmuyoruz**.
> Meşru bir yedek/devir aracıdır; o tekniklere ihtiyaç yoktur ve dahil edilmeyecektir.

---

## 1. Authorization & ethics (read first)

This tool copies someone's full AI working history, which can contain pasted secrets,
source code and live auth tokens. Use it **only** when all of the following hold:

1. The machine is **company-owned** (or you otherwise own/administer it), and you are
   **authorized** to perform the backup — ideally with the departing user's and/or
   IT's knowledge.
2. The run is **overt**: the tool writes a human-readable `RUN_LOG.txt`, a `MANIFEST`,
   and a `README` into the output drive stating *what* was copied, *when*, *by whom*,
   and *under what authorization*. No hiding, no stealth, no anti-AV behaviour.
3. Any **live credentials** captured (OAuth tokens) are treated as secrets: stored
   separately, access-controlled, and **rotated/invalidated** after handover. For the
   stated goal (preserving *history & knowledge*), credentials are **not** required —
   see the secrets policy in [§6](#6-secrets-handling-policy).

If you cannot meet these, do not run it.

---

## 2. What we are collecting (two layers)

Claude Code persistence splits into two layers. We must capture **both**.

### Layer A — Per-user / global store (one per user account)
| Location (Windows) | macOS / Linux | What it holds |
|---|---|---|
| `%USERPROFILE%\.claude\` | `~/.claude/` | Transcripts, history, memory, plugins, skills, settings, file-history, tasks, caches |
| `%USERPROFILE%\.claude.json` (+ `.backup*`, `.tmp*`) | `~/.claude.json` | Master client state: OAuth account, machine/user IDs, **per-project history + MCP configs** |
| `%USERPROFILE%\.claude-mem\` | `~/.claude-mem/` | **Third-party** `claude-mem` plugin: SQLite memory DB + vector store (distilled cross-session memory) |

The user store can be **relocated** by the `CLAUDE_CONFIG_DIR` env var — the tool must
honor it (read the env var; fall back to the default `~/.claude` if unset). `XDG_CONFIG_HOME`
is **not** honored by Claude Code, so we don't need to check it. Whether
`CLAUDE_CONFIG_DIR` also moves `~/.claude.json` is version-dependent — check both the
configured dir **and** the home root.

### Layer B — Project-level artifacts (scattered across ALL drives)
Found inside individual repos/folders anywhere on disk:
| Pattern | What it is | Copy rule |
|---|---|---|
| `.claude/` directory (not the home one) | Project-local config: `settings.json`, `settings.local.json`, `commands/`, `agents/`, `skills/`, `projects/`, `agent-memory-local/`, `worktrees/`, etc. | Copy the whole dir; **stop descending** at each `.claude` boundary |
| `CLAUDE.md` / `CLAUDE.local.md` | Project memory / context | Copy file, preserve original path |
| `.mcp.json` | Project MCP server config | Copy file, preserve original path |
| `.claude.json` **outside** home (rare) | Project-scoped state | Copy if found (none seen on this machine) |

> **Validated on this machine:** 31 project-level `.claude` directories, 15+ `CLAUDE.md`
> files, project `.mcp.json`, and **nested `.claude` inside git worktrees** (e.g.
> `arke/.claude/worktrees/handoff-v11/.claude`). Only the `C:` volume exists here, but
> the design assumes multiple fixed drives.

### Completeness — exactly what IS and ISN'T captured

**Captured (default run = whole machine):**
- ✅ Every **user profile's** global store (`.claude`, `.claude.json*`, `.claude-mem`)
  — the default auto-requests **Administrator (UAC)** to read other users' profiles.
- ✅ **Machine-level** Claude dirs (`%ProgramData%\ClaudeCode`, `%ProgramFiles%\ClaudeCode`).
- ✅ **All fixed drives** swept for project-level `.claude` / `CLAUDE.md` / `CLAUDE.local.md` / `.mcp.json`.
- ✅ `CLAUDE_CONFIG_DIR` relocation (current user) is honored.

**Not captured by default — by deliberate trade-off (use the flag):**
- ⚠️ **Pruned noise dirs** (`node_modules`, `.git`, `dist`, system dirs…) are skipped
  for speed and **logged** to `EXCLUDED.txt`. A `.claude`/`CLAUDE.md` nested inside one
  would be missed → use **`--exhaustive`** (or **`--everything`**) to scan literally everything.
- ⚠️ **Removable / network drives** are skipped → use **`--include-removable`** (network
  shares still excluded by design). The destination USB is always excluded (no self-copy).

**Inherently out of scope (not file data, or platform-specific):**
- ❌ **macOS Keychain** OAuth token — on macOS the live token isn't a file, so a file
  backup can't capture it (irrelevant for history; you'd re-login anyway).
- ❌ **Windows registry policies** (`HKLM/HKCU\SOFTWARE\Policies\ClaudeCode`) — MDM-only
  org *policy*, not user data. Export manually with `reg export` if ever needed.
- ❌ The **Claude Code program/extension binaries** themselves (re-installable; not data).

So: **default = the whole machine's Claude *data*, completely.** `--everything` adds the
paranoid exhaustive+removable sweep. The two ❌ items are genuinely not file-based user data.

---

## 3. Where the value is (prioritized)

Measured on the reference machine (`Evaict`), total Claude footprint ≈ **3.5 GB**:

| Rank | Path | Size | Why it matters |
|---|---|---|---|
| 1 | `~/.claude/projects/` | **1.2 GB / 3,816 files** | Full conversation + every tool call/result (`<session-uuid>.jsonl`). **The primary trove.** |
| 2 | `~/.claude-mem/claude-mem.db` (+`-wal`,`-shm`) | 310 MB | Distilled long-term memory across all sessions |
| 3 | `~/.claude/history.jsonl` | 4.4 MB / 6,791 prompts | Every prompt ever typed |
| 4 | `~/.claude/file-history/` | 69 MB | Pre/post-edit snapshots of edited source |
| 5 | `~/.claude/{tasks,plans,paste-cache}/` | small | Task plans, plan-mode docs, raw pastes |
| — | Layer B project artifacts | small (~MBs) | Per-repo config, custom commands/agents/skills, project memory |

**Rebuildable / optional (≈1.85 GB, can be excluded for a lean backup):**
`~/.claude/plugins/` (830 MB, re-installable), `~/.claude-mem/chroma/` (915 MB, rebuildable
from the DB), `~/.claude-mem/logs/` (104 MB).

- **Full backup** (literally everything) ≈ 3.5 GB.
- **Lean backup** (drop the three rebuildable caches above) ≈ **1.6 GB** — keeps every
  transcript, history, memory DB, file-history, tasks and config.

---

## 4. Secrets present (handle with care)

These hold credentials or may leak pasted secrets:

| Path | Sensitivity |
|---|---|
| `~/.claude/.credentials.json` | **SECRET** — live OAuth tokens (`claudeAiOauth`, `mcpOAuth`). Highest value. |
| `~/.claude.json` + `.backup*` + `~/.claude/backups/*` | **SECRET** — `oauthAccount`, `userID`, `machineID`, MCP configs (may embed tokens) |
| `~/.claude/config.json` | SENSITIVE — `mcpServers` block (auth headers/env possible) |
| `~/.claude/daemon/pipe.key` | SENSITIVE — 16-byte local IPC key |
| `~/.claude-mem/settings.json` | SENSITIVE — API-key slots (empty on this machine, but would hold keys) |
| `projects/*.jsonl`, `history.jsonl`, `paste-cache/`, `shell-snapshots/`, `file-history/`, `debug/` | Content-level: may contain secrets the user pasted or that appeared in tool output |

> **Platform note:** on **macOS** the OAuth credentials live in the **Keychain**, *not*
> in `.credentials.json` — a file-copy backup will (correctly) **miss** the live token.
> That's fine for the history-preservation goal.

---

## 5. Collection algorithm

Two passes per user account, then a manifest/verify pass.

### Pass A — Global store (no admin needed for the current user)
```
resolve USER_DIR = $CLAUDE_CONFIG_DIR or ~/.claude
copy USER_DIR            -> out/<host>/<user>/global/.claude/
copy ~/.claude.json*     -> out/<host>/<user>/global/      (incl. .backup*, .tmp*)
copy ~/.claude-mem/      -> out/<host>/<user>/global/.claude-mem/   (if present)
apply include/exclude profile (full vs lean) + secrets policy (§6)
```
For the SQLite memory DB, copy `claude-mem.db` **together with** its `-wal` and `-shm`
sidecars (or run a `VACUUM INTO`/`.backup` if sqlite is available) so the DB is consistent.

### Pass B — All-drives project sweep
```
DEST = absolute path of the output drive          # exclude to prevent self-copy
for each FIXED volume V (skip removable/network unless --include-removable):
  if V is under DEST: skip
  walk V depth-first, with:
    - visited-set of (volumeId, fileId) to break junction/symlink cycles
    - on dir named ".claude" (and not the home store): copy whole tree, DO NOT descend
    - on file CLAUDE.md / CLAUDE.local.md / .mcp.json / stray .claude.json: copy w/ provenance
    - in DEFAULT mode: prune the noise list below
    - on Access Denied: log to EXCLUDED.txt and continue
preserve original full path under out/<host>/<user>/by-drive/<V>/<original\path>
```

**Default prune list** (skipped unless `--exhaustive`):
`node_modules`, `.git`, `.next`, `dist`, `build`, `__pycache__`, `.venv`/`venv`,
`target`, `.gradle`, `.m2`, `.cargo`, `.idea`, `.vs`, plus system roots
`C:\Windows`, `C:\$Recycle.Bin`, `C:\System Volume Information`,
`C:\Users\All Users`, `C:\Users\Default`, `C:\ProgramData` (review).
> Trade-off: a `.claude` *can* theoretically nest under a pruned dir. `--exhaustive`
> disables pruning for archival completeness (slower). **Log every pruned/skipped path**
> so the backup never silently claims full coverage.

### Pass C — Manifest, dedup, verify
- Hash every collected file (SHA-256; xxHash as a faster option for huge sets).
- Dedup by hash; copy first occurrence, record duplicates with provenance.
- Emit `MANIFEST.csv` + `MANIFEST.json`, `CHECKSUMS.sha256`, `RUN_LOG.txt`,
  `EXCLUDED.txt`, `SUMMARY.txt`.

---

## 6. Secrets handling policy

The default is built around the **stated goal = preserve history/knowledge**, not steal
auth. Three selectable modes:

| Mode | `.credentials.json` / OAuth fields | Use when |
|---|---|---|
| **`safe` (default)** | Live credentials copied into a separate `__SECRETS__/` bundle, listed in the manifest as `secret`, **excluded** from the main archive; OAuth fields in `.claude.json` copies are **redacted** | Knowledge/history archival → SelfFork Mind |
| `redact-only` | Credentials **omitted entirely**; everything else copied | You explicitly never want tokens on the USB |
| `full` | Everything copied inline, secrets flagged in manifest | True bit-for-bit pre-wipe image, with authorization; **rotate tokens after** |

Whatever the mode, the run log and manifest always **disclose** which secret files were
encountered and what was done with them. (Migration best practice: if you move live
credentials between machines, rotate them afterward.)

---

## 7. Output layout (on the USB)

```
claude-backup/
├── README.txt            # what/when/who/authorization, mode used
├── RUN_LOG.txt           # timeline, per-drive timing, errors
├── MANIFEST.csv / .json  # original_path | size | sha256 | type | status
├── CHECKSUMS.sha256      # for later verification
├── EXCLUDED.txt          # skipped: permissions / pruned / depth / timeout
├── SUMMARY.txt           # counts + totals
└── <HOSTNAME>/
    └── <USERNAME>/
        ├── global/                 # Pass A: ~/.claude, ~/.claude.json*, ~/.claude-mem
        ├── by-drive/
        │   ├── C/Users/.../repo/.claude/        # Pass B, original path preserved
        │   └── D/...
        └── __SECRETS__/            # only in `safe` mode (access-controlled)
```
Each `<HOSTNAME>/<USERNAME>` is self-contained, so one USB can hold several machines.

---

## 8. Packaging options (how to ship the `.exe`)

Goal: copy onto a USB, run on any target machine, **zero pre-installed dependencies**,
**readable/auditable source committed in this repo** (no opaque binary trust problem).

| Option | Zero-dep on target | Double-click | Cross-platform | Auditable | Notes |
|---|---|---|---|---|---|
| **A. Go static binary** ⭐ | ✅ (single self-contained exe) | ✅ | ✅ (win/mac/linux cross-compile) | ✅ (source in repo) | ~2–5 MB; best "drop & run". Recommended for "others will use this". |
| **B. PowerShell `.ps1`** | ✅ (PS 5.1 ships on all Windows) | ⚠️ (needs `-ExecutionPolicy Bypass`) | ❌ Windows-only | ✅✅ (plain text, IT reads before running) | Most *trustworthy* for a handover — the teammate/IT can inspect it. |
| **C. `.ps1` → `.exe` via ps2exe** | ✅ | ✅ | ❌ | ✅ (from the .ps1) | Convenience wrapper of B. |
| D. .NET single-file self-contained | ✅ | ✅ | ⚠️ | ✅ | ~60–150 MB, heavier build. |
| E. Python + PyInstaller | ✅ | ✅ | ⚠️ | ✅ | Large, AV-prone, slow build. |

**Recommendation:** ship the logic as a **readable script** (B) as the source of truth,
plus a **Go binary** (A) or **ps2exe** (C) for double-click convenience. Build the binary
from the committed source so anyone can verify it.

> **SmartScreen/AV on an unsigned USB exe is expected.** The legitimate answers are:
> (1) **code-sign** with a company certificate, (2) run the readable `.ps1` instead, or
> (3) "More info → Run anyway" knowingly. We will **not** add evasion/obfuscation.

---

## 9. Operational notes & gotchas

- **Admin rights:** reading the *current* user's own profile needs no elevation. Reading
  **other users'** `C:\Users\<them>\.claude` requires **Administrator** (profile ACLs).
  Default to current/specified user; enumerate all profiles only when run elevated **and**
  authorized.
- **Locked/in-use files:** don't use shadow-copy tricks. Instead **quit Claude Code first**
  (the machine is being decommissioned anyway), then plain copy with retry; for SQLite use
  the WAL-aware copy above. Log any file that stays locked.
- **USB filesystem:** FAT32 caps single files at 4 GB and is risky for a 1.6–3.5 GB set —
  use an **exFAT or NTFS** drive.
- **Destination self-copy:** always detect and exclude the output drive from Pass B.
- **Cross-platform target:** if the teammate is on macOS/Linux, ship the equivalent shell
  script (or Go binary); remember macOS credentials are in **Keychain**, not a file.
- **Determinism/verify:** the `CHECKSUMS.sha256` lets you verify the archive on the
  destination machine after transfer.

---

## 10. Auto-run & live progress (terminal UX)

The tool is **fire-and-forget**: copy it to the USB, double-click on the target machine,
and it runs end-to-end with sane defaults while a console window shows **percentage
progress**. No questions asked mid-run (any choices come from compiled defaults or an
optional `config.json` next to the exe).

### Auto-run behaviour
- **Double-click → a console window opens and runs automatically.** No install, no flags
  required. (Windows disables USB *AutoRun/AutoPlay* by design for security — we rely on a
  user double-click and will **not** try to bypass that.)
- **Auto-detect everything sane:** output folder = a `claude-backup\` created on **the same
  drive the exe is launched from**; host/user/drives detected at runtime; secrets mode and
  full/lean from defaults (overridable via `config.json` or a one-time prompt if you prefer).
- **Window stays open at the end** (`Press any key to close…`) so the summary is readable;
  also writes everything to `RUN_LOG.txt` so nothing is lost if the window closes.
- Optional `--silent` / `--yes` flags for unattended/IT use; optional desktop shortcut.

### How the percentage is computed
Accurate global % needs a denominator, so the run is **two-phase**:
1. **Discovery (sizing) pass** — fast walk that counts files and sums *bytes to copy*
   (after applying include/exclude + prune rules). Shows an indeterminate spinner.
2. **Copy pass** — `overall% = bytesCopied / totalBytesToCopy`, updated continuously.
   Per-stage sub-bars (global store, then each drive) roll up into the overall number.

A single line is repainted in place via carriage-return (`\r` + ANSI); works in `cmd.exe`,
PowerShell and Windows Terminal. (PowerShell can also use the native `Write-Progress`; Go
prints the bar manually.)

### Mockup — during the run
```text
╔══════════════════════════════════════════════════════════════╗
║   Claude Code Data Recovery Kit  v0.1   (read-only · overt)   ║
╚══════════════════════════════════════════════════════════════╝
 Host: DESKTOP-AB12   User: jdoe   Out: E:\claude-backup
 Mode: safe (creds quarantined)    Profile: full

 [1/3] Discovering Claude data ............ done  (4,102 files · 3.48 GB)

 [2/3] Copying global store   ~/.claude · ~/.claude.json · ~/.claude-mem
   projects/…/d8ac2e33.jsonl
   [██████████████████████░░░░░░░░░░]  68%   2.37 / 3.48 GB   42 MB/s   ETA 00:27

 [3/3] Sweeping drives for project artifacts   (C:, D:)
   C:\Users\jdoe\Desktop\arke\.claude
   [████████████████████████████░░░░]  88%   drive C: 02:11   31 .claude · 15 CLAUDE.md
```

### Mockup — final summary
```text
 ──────────────────────────────────────────────────────────────
  DONE in 06:04    ✓ 4,102 files   ✓ 3.48 GB   ✓ 0 errors
  Secrets quarantined: 4 files → E:\claude-backup\DESKTOP-AB12\jdoe\__SECRETS__
  Manifest: MANIFEST.csv     Verify: CHECKSUMS.sha256
  Skipped:  142 pruned · 3 permission-denied (re-run as Admin for full coverage)
 ──────────────────────────────────────────────────────────────
  Press any key to close…
```

### What the progress line shows
overall **%** + bar · bytes copied / total · throughput (MB/s) · ETA · current file ·
current phase/drive · running artifact counts. On error it never aborts silently — it logs
`[SKIP] <path> — <reason>` and the final summary reports totals skipped.

> **Two-phase cost:** the discovery pass walks the disk once before copying, so a full
> all-drives run starts with a short "Discovering…" delay before the % begins moving.
> That's the price of an honest percentage (vs a fake bar that jumps to 100%).

---

## 11. Open decisions to settle before building

1. ~~**Packaging:** Go binary (A) vs readable PowerShell (B) vs ps2exe (C)?~~ → **LOCKED: Go binary (A).**
2. ~~**Secrets mode default:** `safe` / `redact-only` / `full`?~~ → **LOCKED: `safe`** (quarantine + redact).
3. ~~**Backup completeness:** full vs lean?~~ → **LOCKED: `full` (~3.5 GB)**, includes rebuildable caches.
4. **Multi-user:** current user only, or all profiles (requires admin)? *(proposed default: auto — all profiles when run as Admin, else current user, both logged)*
5. **Zip the result?** (transcripts compress well; keep any single zip < 4 GB.)
6. **Hash:** SHA-256 (standard) vs xxHash (faster for large sets)?
7. **Auto-run posture:** fully unattended (compiled defaults, zero prompts) vs a single
   confirm screen before it starts? Keep window open at end (recommended) vs auto-close?

Once chosen, the implementation goes under `claude-data-recovery/tool/` with its own
build instructions — still without touching existing SelfFork packages.

---

## Appendix — Sources

Per-OS paths, `CLAUDE_CONFIG_DIR`, credentials, managed settings, and backup guidance
were verified against Anthropic's official docs:
- https://code.claude.com/docs/en/claude-directory
- https://code.claude.com/docs/en/settings
- https://code.claude.com/docs/en/iam
- https://code.claude.com/docs/en/server-managed-settings
- https://code.claude.com/docs/en/env-vars

Community migration tooling referenced: `claude-code-backup-guide`, `ccms`, `claude-swap`.
`~/.claude-mem` is a **third-party plugin** directory, not core Claude Code.

*Inventory figures measured on the reference machine (`Evaict`), 2026-06-30. The target
machine's contents will differ — the tool measures and logs actuals at run time.*
