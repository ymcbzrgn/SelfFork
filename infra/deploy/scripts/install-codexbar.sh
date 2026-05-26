#!/usr/bin/env bash
# install-codexbar.sh — vendored install for the CodexBar CLI binary.
#
# Reads ``infra/deploy/codexbar/manifest.toml`` (next to this script's
# parent), downloads the platform-specific tarball from GitHub Releases,
# sha256-verifies the archive, extracts ``codexbar`` into ``--prefix``,
# and prints a one-line confirmation.
#
# ADR-007 §4 S-Quota / `[[codexbar-adoption-2026-05-22]]`. The Dockerfile
# invokes this script during build so the resulting image carries a
# pinned, verified binary; local-dev operators can run the script
# directly to populate ``/usr/local/bin/codexbar`` on macOS / Linux.
#
# Usage:
#   install-codexbar.sh                         # arch auto-detect, default prefix
#   install-codexbar.sh --prefix /opt/bin       # custom destination
#   install-codexbar.sh --platform linux-x86_64 # force a platform
#   install-codexbar.sh --no-verify             # DEV ONLY — skip sha256
#   install-codexbar.sh --version v0.27.0       # override manifest version

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/../codexbar/manifest.toml"

PREFIX="/usr/local/bin"
PLATFORM=""
VERIFY=1
VERSION_OVERRIDE=""

usage() {
  cat <<'EOF'
install-codexbar.sh — vendored install for CodexBar CLI.

  --prefix <dir>      Destination for the codexbar binary (default /usr/local/bin)
  --platform <name>   Force platform (linux-x86_64|linux-aarch64|macos-arm64|macos-x86_64)
  --no-verify         Skip sha256 verification (DEV ONLY)
  --version <vTag>    Override manifest version
  -h, --help          This message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --platform) PLATFORM="$2"; shift 2 ;;
    --no-verify) VERIFY=0; shift ;;
    --version) VERSION_OVERRIDE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "install-codexbar: unknown flag $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -f "$MANIFEST" ]]; then
  echo "install-codexbar: manifest not found at $MANIFEST" >&2
  exit 2
fi

# Tiny TOML reader — just the fields we need. Avoids adding a runtime
# Python dep when only Bash is on the container at install-time. All
# release-level keys live under ``[release]``; the matcher gates by
# section so a future ``version`` / ``url_template`` field under
# ``[platforms.*]`` cannot silently shadow the canonical value
# (audit-god S-Quota Wave 1 finding #F-08).
manifest_value() {
  local key="$1"
  local section="${2:-release}"
  awk -v key="$key" -v target_section="$section" '
    BEGIN { in_section = 0 }
    /^\[/ {
      if ($0 == ("[" target_section "]")) in_section = 1
      else in_section = 0
      next
    }
    {
      if (!in_section) next
      sub(/^[[:space:]]+/, "")
      if (index($0, key " ") == 1 || index($0, key "=") == 1) {
        sub(/^[^=]+=[[:space:]]*/, "")
        gsub(/^"|"$/, "")
        print
        exit
      }
    }
  ' "$MANIFEST"
}

manifest_platform_sha() {
  local platform="$1"
  awk -v section="[platforms.${platform}]" '
    $0 == section { in_section = 1; next }
    in_section && /^\[/ { in_section = 0 }
    in_section && /^sha256/ {
      sub(/^[^=]+=[[:space:]]*/, "")
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$MANIFEST"
}

VERSION="${VERSION_OVERRIDE:-$(manifest_value version)}"
URL_TEMPLATE="$(manifest_value url_template)"
ARCHIVE_MEMBER="$(manifest_value archive_member)"

if [[ -z "$VERSION" || -z "$URL_TEMPLATE" || -z "$ARCHIVE_MEMBER" ]]; then
  echo "install-codexbar: manifest missing required keys" >&2
  exit 2
fi

# Detect platform when not forced.
if [[ -z "$PLATFORM" ]]; then
  uname_s="$(uname -s)"
  uname_m="$(uname -m)"
  case "$uname_s" in
    Linux)
      case "$uname_m" in
        x86_64|amd64) PLATFORM="linux-x86_64" ;;
        aarch64|arm64) PLATFORM="linux-aarch64" ;;
        *) echo "install-codexbar: unsupported Linux arch $uname_m" >&2; exit 2 ;;
      esac ;;
    Darwin)
      case "$uname_m" in
        arm64) PLATFORM="macos-arm64" ;;
        x86_64) PLATFORM="macos-x86_64" ;;
        *) echo "install-codexbar: unsupported macOS arch $uname_m" >&2; exit 2 ;;
      esac ;;
    *) echo "install-codexbar: unsupported OS $uname_s" >&2; exit 2 ;;
  esac
fi

URL="${URL_TEMPLATE//\{version\}/$VERSION}"
URL="${URL//\{platform\}/$PLATFORM}"

EXPECTED_SHA="$(manifest_platform_sha "$PLATFORM")"
if [[ "$VERIFY" -eq 1 && -z "$EXPECTED_SHA" ]]; then
  cat <<EOF >&2
install-codexbar: no sha256 pinned for $PLATFORM in manifest.
Run scripts/refresh-codexbar-checksums.sh ${VERSION} to pin checksums
(S-Quota Wave 2 — auto-update CI), or pass --no-verify (DEV ONLY).
EOF
  exit 3
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
TARBALL="$TMP_DIR/codexbar.tar.gz"

echo "install-codexbar: downloading ${URL}"
curl -fsSL --retry 3 -o "$TARBALL" "$URL"

if [[ "$VERIFY" -eq 1 ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA="$(sha256sum "$TARBALL" | awk '{print $1}')"
  else
    ACTUAL_SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"
  fi
  if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]]; then
    echo "install-codexbar: sha256 mismatch for $PLATFORM" >&2
    echo "  expected: $EXPECTED_SHA" >&2
    echo "  got     : $ACTUAL_SHA" >&2
    exit 3
  fi
fi

mkdir -p "$PREFIX"

# Extraction strategy (BUG-2 fix, 2026-05-26):
#
# Older versions of this script tried to extract a single tarball
# member by name, which fails when the manifest names a *symlink*
# (the v0.27.0 tarball ships ``codexbar`` as a symlink to the real
# ``CodexBarCLI`` Swift binary). tar(1) extracts the symlink without
# its target, leaving us with a dangling installed file.
#
# Robust path:
#   1. Try the direct member extract. Works when ``archive_member``
#      names the real binary at the tarball root (e.g. CodexBarCLI).
#   2. If that fails OR the extracted entry isn't an executable
#      regular file, extract the whole tarball into a scratch dir
#      and locate the binary by basename — handles subdir-wrapped
#      layouts and symlink-only manifests without a manifest bump.
EXTRACTED=""
if tar -xzf "$TARBALL" -C "$TMP_DIR" "$ARCHIVE_MEMBER" 2>/dev/null; then
  candidate="$TMP_DIR/$ARCHIVE_MEMBER"
  if [[ -f "$candidate" && ! -L "$candidate" ]]; then
    EXTRACTED="$candidate"
  fi
fi
if [[ -z "$EXTRACTED" ]]; then
  EXTRACT_DIR="$TMP_DIR/extract"
  mkdir -p "$EXTRACT_DIR"
  tar -xzf "$TARBALL" -C "$EXTRACT_DIR"
  # Prefer the manifest-named binary; fall back to known Swift-binary
  # alternatives so an upstream rename doesn't blow up the install
  # path mid-flight (operator can still run, file an issue, refresh
  # the manifest at leisure).
  for candidate in "$ARCHIVE_MEMBER" "CodexBarCLI" "codexbar"; do
    found="$(find "$EXTRACT_DIR" -type f -name "$candidate" -perm -u+x -print | head -n 1 || true)"
    if [[ -n "$found" ]]; then
      EXTRACTED="$found"
      break
    fi
  done
fi
if [[ -z "$EXTRACTED" || ! -f "$EXTRACTED" ]]; then
  echo "install-codexbar: could not locate codexbar binary inside ${TARBALL}" >&2
  echo "install-codexbar: archive contents:" >&2
  tar -tzf "$TARBALL" >&2 | head -50
  exit 3
fi

install -m 0755 "$EXTRACTED" "$PREFIX/codexbar"

echo "install-codexbar: installed CodexBar ${VERSION} → ${PREFIX}/codexbar"
