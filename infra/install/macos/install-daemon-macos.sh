#!/usr/bin/env bash
# SelfFork body daemon — macOS installer (Homebrew tap path).
#
# Operator runs this on each remote macOS host. Approval steps:
#   1. brew tap selffork/tap
#   2. brew install selffork-daemon
#   3. Grant Accessibility + Screen Recording permission via System Settings.
#   4. Load the launchd plist.
set -euo pipefail

BREW_TAP="selffork/tap"
PLIST="/Library/LaunchDaemons/com.selffork.daemon.plist"

echo "→ tapping $BREW_TAP"
brew tap "$BREW_TAP" || true

echo "→ installing selffork-daemon"
brew install selffork-daemon

echo "→ granting Accessibility + Screen Recording permission"
echo "Open System Settings → Privacy & Security → Accessibility"
echo "Add: $(brew --prefix)/bin/selffork-daemon"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"

echo "→ loading launchd plist"
sudo launchctl load -w "$PLIST"
echo "✓ daemon installed; tail logs at /var/log/selffork-daemon.log"
