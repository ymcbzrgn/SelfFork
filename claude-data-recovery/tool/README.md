# ClaudeBackup — the collector tool

A single, dependency-free **Go** executable that backs up **all Claude Code
(terminal CLI) data** from a machine onto a portable drive. See the design,
scope and **authorization/ethics** note in [`../README.md`](../README.md).

> Overt by design: it prints a live progress bar and writes a manifest, checksums
> and a run log. It does **not** hide, obfuscate, or evade AV. Run it only on
> machines you are authorized to back up.

## What it collects

By **default** it does a whole-machine sweep: **all user profiles** (auto-requests
Administrator via UAC), plus machine-level locations. Use `--quick` for current-user
only, or `--everything` for the most exhaustive sweep.

- **Global store (per user):** `~/.claude/`, `~/.claude.json*` (incl. backups), `~/.claude-mem/`
- **Machine-level:** `%ProgramData%\ClaudeCode\`, `%ProgramFiles%\ClaudeCode\`
  (enterprise `managed-settings.json`, if present)
- **Project artifacts (all fixed drives):** every `.claude/` dir, `CLAUDE.md`,
  `CLAUDE.local.md`, `.mcp.json`
- **Secrets (`safe` mode, default):** live credentials (`.credentials.json`,
  `daemon/pipe.key`) are copied into a segregated `__SECRETS__/` subtree; OAuth /
  token / key fields inside `.claude.json`, `config.json`, `.mcp.json`,
  `settings*.json` are **redacted** in the copies.

## Quick use (the shipped exe)

1. Copy `dist/ClaudeBackup.exe` onto your USB drive.
2. On the target machine, **quit Claude Code**, then double-click the exe.
3. Approve the **UAC prompt** (needed to read all user profiles). It auto-creates
   `claude-backup\` next to itself (on the USB), shows a live `%` progress bar,
   and writes everything there. Window stays open at the end.

For the most thorough sweep: `ClaudeBackup.exe --everything`.

## Flags

```
ClaudeBackup.exe [flags]

  --everything         complete machine sweep: all users + exhaustive + removable
  --quick              fast path: current user only, no elevation, pruned
  --out <dir>          output root (default: <exe dir>\claude-backup)
  --dry-run            discover & plan only; copy nothing (writes a planned manifest)
  --secrets <mode>     safe | redact-only | full        (default: safe)
  --all-users          scan every user profile        (DEFAULT on; needs Administrator)
  --no-elevate         do not auto-request Administrator (UAC)
  --lean               skip rebuildable caches (.claude/plugins, .claude-mem/chroma, logs)
  --exhaustive         do not prune noise dirs during the drive sweep
  --include-removable  also sweep removable drives
  --sweep-root <list>  comma-separated roots to sweep instead of all drives (testing)
  --silent             do not wait for a keypress at the end
  --version
```

Secrets modes: `safe` (quarantine creds + redact, **default**), `redact-only`
(never copy creds at all), `full` (copy everything inline, flagged — rotate
tokens afterward).

## Output layout

```
claude-backup/
  README.txt  RUN_LOG.txt  MANIFEST.csv  MANIFEST.json  CHECKSUMS.sha256  EXCLUDED.txt  SUMMARY.txt
  <HOST>/<USER>/
    global/      ~/.claude, ~/.claude.json*, ~/.claude-mem
    by-drive/    project-level .claude / CLAUDE.md / .mcp.json (original paths preserved)
    __SECRETS__/ quarantined live credentials (safe mode)
```

Verify after transfer: `sha256sum -c CHECKSUMS.sha256` (or `certutil -hashfile`).

## Build from source

Requires Go 1.21+ (built/tested with Go 1.26).

```bash
# from this tool/ directory
go vet ./...
go build -trimpath -ldflags "-s -w" -o dist/ClaudeBackup.exe .

# cross-compile for the same Windows target from macOS/Linux:
GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o dist/ClaudeBackup.exe .
```

The `.exe` under `dist/` is the shipped product and **is committed** (so people
can grab & run it). Collected output is git-ignored and must never be committed.

## Source files

| File | Role |
|---|---|
| `main.go` | flags, config, run flow, banner/summary, keep-window-open |
| `discover.go` | Plan/Item types, global-store + all-drives sweep discovery |
| `secrets.go` | classification (quarantine/redact) + JSON redaction |
| `copyx.go` | copy with retry, sha256 hashing, progress accounting |
| `progress.go` | live percentage bar (bytes copied / total) |
| `manifest.go` | manifest, checksums, run log, summary, README |
| `platform_windows.go` / `platform_other.go` | drive enumeration, reparse-point detection |

## Notes & limits

- `--zip` is accepted but not implemented yet (produces a raw tree).
- Reading **other users'** profiles needs Administrator; without it those paths
  are logged to `EXCLUDED.txt` and skipped (never fatal).
- Locked files are retried briefly, then logged & skipped — no shadow-copy tricks.
- On **macOS** the live OAuth token lives in the Keychain, not a file, so a
  file-copy backup won't capture it (fine for history preservation).
- The `%` denominator is the sum of *source* sizes; redacted JSON is re-emitted
  pretty-printed, so the bar can momentarily read slightly past 100%.
```
