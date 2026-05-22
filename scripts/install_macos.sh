#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_NAME="KnowSayin"
VENV_DIR="${KNOWSAYIN_VENV_DIR:-$PROJECT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS. For server/web usage, see README.md." >&2
  exit 1
fi

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "python3 not found. Install Python 3, then run this script again." >&2
  exit 1
fi

cd "$PROJECT_DIR"

if [[ ! -f "$PROJECT_DIR/requirements.txt" ]]; then
  echo "Missing requirements.txt. Run this script from a complete KnowSayin checkout." >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/.env.example" ]]; then
  echo "Missing .env.example. Run this script from a complete KnowSayin checkout." >&2
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PYINSTALLER="$VENV_DIR/bin/pyinstaller"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Virtual environment is missing python: $VENV_PYTHON" >&2
  exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  chmod 600 "$PROJECT_DIR/.env"
fi

KNOWSAYIN_PYINSTALLER="$VENV_PYINSTALLER" "$PROJECT_DIR/scripts/build_macos_app.sh"

INSTALL_DIR="${KNOWSAYIN_INSTALL_DIR:-/Applications}"
echo "Installed $INSTALL_DIR/$APP_NAME.app"
echo "Open it, then enable Accessibility for $APP_NAME.app in macOS Privacy & Security settings."
