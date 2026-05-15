#!/usr/bin/env bash
# SelfFork body daemon — Ubuntu installer (.deb path).
set -euo pipefail

REPO_LINE="deb [trusted=yes] https://apt.selffork.dev stable main"
LIST_FILE="/etc/apt/sources.list.d/selffork.list"

if [[ ! -f "$LIST_FILE" ]]; then
  echo "→ adding selffork apt source"
  echo "$REPO_LINE" | sudo tee "$LIST_FILE" > /dev/null
fi

sudo apt-get update
sudo apt-get install -y selffork-daemon
sudo systemctl enable --now selffork-daemon.service
echo "✓ daemon installed; check status with: systemctl status selffork-daemon"
