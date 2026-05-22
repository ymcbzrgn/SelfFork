#!/usr/bin/env bash
# refresh-codexbar-checksums.sh — pin SHA256s of a CodexBar release.
#
# ADR-007 §4 S-Quota Wave 2 — auto-update CI helper. Given a target
# release tag (``vX.Y.Z``), fetches every platform tarball, computes
# the sha256, and rewrites ``infra/deploy/codexbar/manifest.toml`` in
# place. The CI workflow (``.github/workflows/codexbar-watch.yml``,
# Wave 2) chains this into a PR. Operators can also invoke it locally
# to dry-run a bump.
#
# Usage:
#   refresh-codexbar-checksums.sh v0.27.0
#   refresh-codexbar-checksums.sh v0.27.0 --dry-run   # print, don't write

set -Eeuo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: refresh-codexbar-checksums.sh <vTag> [--dry-run]" >&2
  exit 2
fi

VERSION="$1"
DRY_RUN=0
if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/../codexbar/manifest.toml"

PLATFORMS=(
  linux-x86_64
  linux-aarch64
  macos-arm64
  macos-x86_64
)

declare -A SHASUMS
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

for platform in "${PLATFORMS[@]}"; do
  url="https://github.com/steipete/CodexBar/releases/download/${VERSION}/CodexBarCLI-${VERSION}-${platform}.tar.gz"
  echo "refresh-codexbar-checksums: fetching $platform"
  curl -fsSL --retry 3 -o "${TMP_DIR}/${platform}.tar.gz" "$url"
  if command -v sha256sum >/dev/null 2>&1; then
    SHASUMS[$platform]="$(sha256sum "${TMP_DIR}/${platform}.tar.gz" | awk '{print $1}')"
  else
    SHASUMS[$platform]="$(shasum -a 256 "${TMP_DIR}/${platform}.tar.gz" | awk '{print $1}')"
  fi
  echo "  $platform = ${SHASUMS[$platform]}"
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "refresh-codexbar-checksums: dry-run; not modifying $MANIFEST"
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "refresh-codexbar-checksums: python3 required to rewrite the manifest" >&2
  exit 2
fi

"$PYTHON_BIN" - "$MANIFEST" "$VERSION" "${SHASUMS[linux-x86_64]}" \
    "${SHASUMS[linux-aarch64]}" "${SHASUMS[macos-arm64]}" \
    "${SHASUMS[macos-x86_64]}" <<'PY'
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
version = sys.argv[2]
sha_linux_x86 = sys.argv[3]
sha_linux_arm = sys.argv[4]
sha_macos_arm = sys.argv[5]
sha_macos_x86 = sys.argv[6]

text = manifest_path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

def replace_value(section: str | None, key: str, new_value: str) -> None:
    """Replace ``key = "..."`` inside ``section`` (or top-level when None)."""
    in_section = section is None
    target_header = f"[{section}]" if section else ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = section is not None and stripped == target_header
            continue
        if not in_section:
            continue
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            prefix = line[: line.find(key)]
            lines[i] = f'{prefix}{key} = "{new_value}"\n'
            return
    raise SystemExit(f"refresh-codexbar-checksums: key '{key}' not found in {section or 'root'}")

replace_value("release", "version", version)
replace_value("platforms.linux-x86_64", "sha256", sha_linux_x86)
replace_value("platforms.linux-aarch64", "sha256", sha_linux_arm)
replace_value("platforms.macos-arm64", "sha256", sha_macos_arm)
replace_value("platforms.macos-x86_64", "sha256", sha_macos_x86)
manifest_path.write_text("".join(lines), encoding="utf-8")
print(f"refresh-codexbar-checksums: manifest rewritten ({manifest_path})")
PY
