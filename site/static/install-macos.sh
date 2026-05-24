#!/usr/bin/env bash
set -euo pipefail

APP_NAME="KnowSayin"
REPO_TARBALL_URL="${KNOWSAYIN_REPO_TARBALL_URL:-https://github.com/aginchan-spec/knowsayin/archive/refs/heads/main.tar.gz}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/knowsayin-install.XXXXXX")"

cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "KnowSayin desktop install currently supports macOS only." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download KnowSayin." >&2
  exit 1
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "tar is required to unpack KnowSayin." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for this early installer. Install Python 3, then run this command again." >&2
  exit 1
fi

echo "Downloading KnowSayin..."
curl -fL "$REPO_TARBALL_URL" -o "$WORK_DIR/knowsayin.tar.gz"
tar -xzf "$WORK_DIR/knowsayin.tar.gz" -C "$WORK_DIR"

PROJECT_DIR="$(find "$WORK_DIR" -maxdepth 1 -type d -name "knowsayin-*" -print -quit)"
if [[ -z "$PROJECT_DIR" || ! -d "$PROJECT_DIR" ]]; then
  echo "Could not find the downloaded KnowSayin source folder." >&2
  exit 1
fi

echo "Installing KnowSayin..."
"$PROJECT_DIR/scripts/install_macos.sh"

if [[ -d "/Applications/$APP_NAME.app" ]]; then
  open "/Applications/$APP_NAME.app" || true
fi

echo "Done. If prompted, allow Accessibility access for KnowSayin in macOS System Settings."
