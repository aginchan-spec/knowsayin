#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="KnowSayin"
BUNDLE_ID="com.knowsayin.app"
BUILD_DIR="/tmp/knowsayin-build"
DIST_DIR="/tmp/knowsayin-dist"
WORK_DIR="/tmp/knowsayin-pyinstaller"
INSTALL_DIR="${KNOWSAYIN_INSTALL_DIR:-/Applications}"
CONFIG_DIR="${KNOWSAYIN_CONFIG_DIR:-$HOME/Library/Application Support/KnowSayin}"
PYINSTALLER="${KNOWSAYIN_PYINSTALLER:-$(command -v pyinstaller || true)}"

if [[ ! -x "$PYINSTALLER" ]]; then
  PYINSTALLER="$HOME/Library/Python/3.9/bin/pyinstaller"
fi

if [[ ! -x "$PYINSTALLER" ]]; then
  echo "pyinstaller not found. Run: python3 -m pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p "$BUILD_DIR" "$INSTALL_DIR"

ENTRY_FILE="$BUILD_DIR/knowsayin_app_entry.py"
python3 - "$ENTRY_FILE" <<'PY'
from pathlib import Path
import sys

entry = Path(sys.argv[1])
entry.write_text(
    """import os

from app.main import main

if __name__ == "__main__":
    main()
""",
    encoding="utf-8",
)
PY

"$PYINSTALLER" \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --paths "$PROJECT_DIR" \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$BUILD_DIR" \
  "$ENTRY_FILE"

rm -rf "$INSTALL_DIR/$APP_NAME.app"
ditto "$DIST_DIR/$APP_NAME.app" "$INSTALL_DIR/$APP_NAME.app"
xattr -dr com.apple.quarantine "$INSTALL_DIR/$APP_NAME.app" 2>/dev/null || true

mkdir -p "$CONFIG_DIR"
if [[ -f "$PROJECT_DIR/.env" && ! -f "$CONFIG_DIR/.env" ]]; then
  cp -p "$PROJECT_DIR/.env" "$CONFIG_DIR/.env"
  chmod 600 "$CONFIG_DIR/.env"
fi

echo "$INSTALL_DIR/$APP_NAME.app"
