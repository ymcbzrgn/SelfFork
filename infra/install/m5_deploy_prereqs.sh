#!/usr/bin/env bash
# M5 Body — Operator deploy prerequisites installer (dry-run by default).
#
# Usage:
#   bash infra/install/m5_deploy_prereqs.sh --check   # dry-run, no install
#   bash infra/install/m5_deploy_prereqs.sh           # interactive install
#   bash infra/install/m5_deploy_prereqs.sh --force   # non-interactive (CI)
#
# Per docs/plans/M5_Smoke_Checklist.md §0. Idempotent: re-running is safe.
# All actual installs require operator confirmation unless --force is passed.

set -euo pipefail

MODE="install"
for arg in "$@"; do
  case "$arg" in
    --check)  MODE="check"  ;;
    --force)  MODE="force"  ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0 ;;
    *)
      echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# ── Colour helpers ──────────────────────────────────────────────────────────
GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; RESET=$'\033[0m'
ok()    { printf "  %sOK%s   %s\n" "$GREEN" "$RESET" "$1"; }
miss()  { printf "  %sMISS%s %s\n" "$YELLOW" "$RESET" "$1"; }
fail()  { printf "  %sFAIL%s %s\n" "$RED" "$RESET" "$1"; }
hdr()   { printf "\n== %s ==\n" "$1"; }

# ── confirm() — interactive yes/no with default-no ─────────────────────────
confirm() {
  local prompt="$1"
  if [ "$MODE" = "check" ]; then
    echo "  [check] skipping: $prompt"; return 1
  fi
  if [ "$MODE" = "force" ]; then return 0; fi
  read -r -p "  $prompt [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]]
}

# ── 1. Python venv + uv ─────────────────────────────────────────────────────
hdr "Python venv + uv"
if [ -d ".venv" ]; then ok ".venv present"; else miss ".venv missing — run: uv venv && uv pip install -e ."; fi
command -v uv >/dev/null 2>&1 && ok "uv on PATH" || miss "uv missing — install: brew install uv"

# ── 2. mlx-vlm (vision tier-1) ──────────────────────────────────────────────
hdr "mlx-vlm (Apple Silicon Tier-1)"
if .venv/bin/python -c "import mlx_vlm" 2>/dev/null; then
  ok "mlx_vlm importable"
else
  miss "mlx_vlm not installed"
  if confirm "install mlx-vlm into .venv?"; then
    .venv/bin/uv pip install mlx-vlm || fail "uv pip install mlx-vlm"
  fi
fi

# ── 3. Pillow (vision preprocess) ───────────────────────────────────────────
hdr "Pillow (vision/preprocess)"
if .venv/bin/python -c "import PIL.Image" 2>/dev/null; then
  ok "PIL importable"
else
  miss "Pillow not installed (1 vision test skipped)"
  if confirm "install Pillow into .venv?"; then
    .venv/bin/uv pip install Pillow || fail "uv pip install Pillow"
  fi
fi

# ── 4. Playwright Chromium (web driver) ─────────────────────────────────────
hdr "Playwright (web driver)"
if .venv/bin/python -c "import playwright" 2>/dev/null; then
  ok "playwright importable"
  if [ -d "$HOME/Library/Caches/ms-playwright/chromium" ] || ls "$HOME/.cache/ms-playwright/chromium"* >/dev/null 2>&1; then
    ok "Chromium binary cached"
  else
    miss "Chromium not installed"
    if confirm "run 'playwright install chromium'?"; then
      .venv/bin/playwright install chromium || fail "playwright install"
    fi
  fi
else
  miss "playwright not installed"
  if confirm "install playwright + chromium?"; then
    .venv/bin/uv pip install playwright && .venv/bin/playwright install chromium \
      || fail "playwright install"
  fi
fi

# ── 5. Go toolchain (daemon build) ──────────────────────────────────────────
hdr "Go (daemon build)"
if command -v go >/dev/null 2>&1; then
  ok "go on PATH: $(go version)"
else
  miss "Go missing — required for packages/body/daemon"
  if confirm "install Go via Homebrew?"; then
    brew install go || fail "brew install go"
  fi
fi

# ── 6. Tailscale (cross-host daemon round-trip) ─────────────────────────────
hdr "Tailscale (daemon mesh)"
if command -v tailscale >/dev/null 2>&1; then
  ok "tailscale CLI present"
  if tailscale status >/dev/null 2>&1; then ok "tailscale up"; else miss "tailscale not logged in — run: sudo tailscale up"; fi
else
  miss "tailscale missing (optional — single-host smoke skips senaryo 8 cross-host)"
  if [ "$MODE" = "force" ]; then
    # Cask install needs admin password (osascript prompt) → would hang in
    # non-interactive CI; skip and let operator handle interactively.
    miss "  (skipping cask install in --force mode; run interactively for tailscale)"
  elif confirm "install Tailscale CLI via Homebrew cask?"; then
    brew install --cask tailscale || fail "brew install tailscale"
  fi
fi

# ── 7. Android Platform Tools (Android driver) ──────────────────────────────
hdr "Android (adb + docker-android)"
command -v adb >/dev/null 2>&1 && ok "adb on PATH" || miss "adb missing — brew install --cask android-platform-tools (optional)"
if command -v docker >/dev/null 2>&1; then ok "docker on PATH"; else miss "docker missing (Android driver senaryosu için)"; fi

# ── 8. Xcode CLT (iOS sim driver) ───────────────────────────────────────────
hdr "iOS (xcrun simctl)"
command -v xcrun >/dev/null 2>&1 && ok "xcrun on PATH" || miss "xcrun missing — Xcode Command Line Tools gerekiyor (xcode-select --install)"
if xcrun simctl list devices 2>/dev/null | grep -q "Booted"; then
  ok "iOS simulator booted"
else
  miss "no iOS simulator booted (xcrun simctl boot <udid> ile başlat)"
fi

# ── 9. Vision config sanity ────────────────────────────────────────────────
hdr "Vision config sanity"
CFG="$HOME/.selffork/config.yaml"
if [ -f "$CFG" ]; then
  ok "$CFG present"
  if grep -q "^vision:" "$CFG"; then
    ok "vision: section present in YAML"
  else
    miss "vision: section missing — defaults will be used until Cockpit Settings writes it"
  fi
else
  miss "$CFG not present — defaults will be used"
fi

# ── 10. Audit dir ──────────────────────────────────────────────────────────
hdr "Audit log directory"
AUDIT="$HOME/.selffork/audit"
if [ -d "$AUDIT" ]; then ok "$AUDIT present"; else
  miss "$AUDIT missing"
  if confirm "create $AUDIT?"; then mkdir -p "$AUDIT" && ok "created"; fi
fi

# ── 11. mlx_vlm.server probe (optional — only if up) ───────────────────────
hdr "mlx_vlm.server probe (optional)"
if curl --connect-timeout 3 --max-time 5 -fsS http://127.0.0.1:8080/v1/models >/dev/null 2>&1; then
  ok "mlx_vlm.server responding on :8080"
  curl --connect-timeout 3 --max-time 5 -s http://127.0.0.1:8080/v1/models | python -c "import sys,json; d=json.load(sys.stdin); print('     models:', [m['id'] for m in d.get('data', [])])" 2>/dev/null || true
else
  miss "mlx_vlm.server not running on :8080 (M5 senaryo 1 öncesi başlat)"
fi

# ── 12. Ollama probe (optional) ────────────────────────────────────────────
hdr "Ollama probe (optional)"
if curl --connect-timeout 3 --max-time 5 -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  ok "ollama responding on :11434"
  curl --connect-timeout 3 --max-time 5 -s http://127.0.0.1:11434/api/tags | python -c "import sys,json; d=json.load(sys.stdin); print('     tags:', [m['name'] for m in d.get('models', [])])" 2>/dev/null || true
else
  miss "ollama not running on :11434 (Linux fallback için gerekli)"
fi

echo
echo "${GREEN}Prereqs check complete.${RESET} Sonraki adım: docs/plans/M5_Smoke_Checklist.md §1."
