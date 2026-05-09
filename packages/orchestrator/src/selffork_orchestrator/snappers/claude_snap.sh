#!/usr/bin/env bash
# SelfFork Claude Code raw-JSON snapshotter.
#
# Reads Claude Code's statusline stdin JSON push and atomically writes it to
# ~/.selffork/cli-state/raw/claude.json. The Python ClaudeSnapper polls that
# raw file and projects it into the normalized QuotaSnapshot living at
# ~/.selffork/cli-state/claude-code.json.
#
# One-time setup (Yamaç runs this manually):
#   Add the line below to ~/.claude/statusline.sh, immediately after
#   `input=$(cat)`:
#
#       printf '%s' "$input" | /abs/path/to/snappers/claude_snap.sh 2>/dev/null
#
#   The pipe is non-blocking and silent: if the snapper fails the user's
#   status line keeps rendering. SnapperRunner re-reads the raw file at
#   each tick; transient absence is fine.

set -euo pipefail

STATE_DIR="${SELFFORK_RAW_STATE_DIR:-${HOME}/.selffork/cli-state/raw}"
mkdir -p "$STATE_DIR"
DEST="${STATE_DIR}/claude.json"

# Same-directory mktemp + atomic mv → POSIX guarantees readers see either
# the previous full file or the new full file, never partial content.
TMP="$(mktemp "${DEST}.XXXXXX")"
cat > "$TMP"
mv "$TMP" "$DEST"
