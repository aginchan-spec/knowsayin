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
ICON_FILE="$PROJECT_DIR/assets/knowsayin.icns"
CODESIGN_IDENTITY="${KNOWSAYIN_CODESIGN_IDENTITY:-}"
REQUIRE_CODESIGN="${KNOWSAYIN_REQUIRE_CODESIGN:-false}"

if [[ ! -x "$PYINSTALLER" ]]; then
  PYINSTALLER="$HOME/Library/Python/3.9/bin/pyinstaller"
fi

if [[ ! -x "$PYINSTALLER" ]]; then
  echo "pyinstaller not found. Run: scripts/install_macos.sh, or install requirements in your active venv." >&2
  exit 1
fi

if [[ -n "$CODESIGN_IDENTITY" ]]; then
  if ! security find-identity -v -p codesigning | grep -F "\"$CODESIGN_IDENTITY\"" >/dev/null; then
    echo "codesign identity not found or not valid: $CODESIGN_IDENTITY" >&2
    exit 1
  fi
elif [[ "$REQUIRE_CODESIGN" == "true" ]]; then
  echo "KNOWSAYIN_REQUIRE_CODESIGN=true but KNOWSAYIN_CODESIGN_IDENTITY is not set." >&2
  exit 1
else
  echo "Warning: building ad-hoc signed app. Accessibility permission may need to be re-granted after every rebuild." >&2
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

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --name "$APP_NAME"
  --osx-bundle-identifier "$BUNDLE_ID"
  --paths "$PROJECT_DIR"
  --distpath "$DIST_DIR"
  --workpath "$WORK_DIR"
  --specpath "$BUILD_DIR"
)

if [[ -f "$ICON_FILE" ]]; then
  PYINSTALLER_ARGS+=(--icon "$ICON_FILE")
fi

if [[ -n "$CODESIGN_IDENTITY" ]]; then
  PYINSTALLER_ARGS+=(--codesign-identity "$CODESIGN_IDENTITY")
fi

"$PYINSTALLER" "${PYINSTALLER_ARGS[@]}" "$ENTRY_FILE"

if [[ -n "$CODESIGN_IDENTITY" ]]; then
  codesign --force --deep --sign "$CODESIGN_IDENTITY" "$DIST_DIR/$APP_NAME.app"
fi

rm -rf "$INSTALL_DIR/$APP_NAME.app"
ditto "$DIST_DIR/$APP_NAME.app" "$INSTALL_DIR/$APP_NAME.app"
xattr -dr com.apple.quarantine "$INSTALL_DIR/$APP_NAME.app" 2>/dev/null || true

mkdir -p "$CONFIG_DIR"
if [[ -f "$PROJECT_DIR/.env" && ! -f "$CONFIG_DIR/.env" ]]; then
  cp -p "$PROJECT_DIR/.env" "$CONFIG_DIR/.env"
  chmod 600 "$CONFIG_DIR/.env"
fi

echo "$INSTALL_DIR/$APP_NAME.app"
