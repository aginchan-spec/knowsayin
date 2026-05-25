#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-${HOME}/android-sdk}}"
DEFAULT_APK_PATH="$(cd "$(dirname "$0")/.." && pwd)/app/build/outputs/apk/debug/app-debug.apk"
DEFAULT_APP_ID="com.knowsayin.android.debug"
DEFAULT_IME_COMPONENT="com.knowsayin.android.debug/com.knowsayin.android.KnowSayinImeService"

ANDROID_HOME_DIR="${ANDROID_HOME:-${DEFAULT_ANDROID_HOME}}"
APK_PATH="${APK_PATH:-${DEFAULT_APK_PATH}}"
APP_ID="${APP_ID:-${DEFAULT_APP_ID}}"
IME_COMPONENT="${IME_COMPONENT:-${DEFAULT_IME_COMPONENT}}"

ADB="${ANDROID_HOME_DIR}/platform-tools/adb"
LOG_PID=""

usage() {
  cat <<'USAGE'
Smoke-test the KnowSayin Android IME on a connected device or emulator.

Usage:
  android/scripts/device-smoke.sh

Optional environment variables:
  ANDROID_HOME        Android SDK root. Default: $ANDROID_HOME, $ANDROID_SDK_ROOT, or ~/android-sdk.
  APK_PATH            Path to APK. Default: <repo>/android/app/build/outputs/apk/debug/app-debug.apk.
  APP_ID              Application ID for uninstall. Default: com.knowsayin.android.debug.
  IME_COMPONENT       Full IME component name. Default: com.knowsayin.android.debug/...KnowSayinImeService.

For a release build, override APK_PATH to the release APK, and set APP_ID and
IME_COMPONENT without the .debug suffix (e.g. APP_ID=com.knowsayin.android).

What it does:
  1. Verify adb, APK, and a single connected device.
  2. Install the debug APK.
  3. List IMEs and attempt to enable/set the KnowSayin IME.
  4. Print clear manual smoke steps using fixed non-private examples.

This script does NOT capture or print private user text. It does not dump
broad logcat output. A filtered opt-in logcat helper is available with --logcat.
USAGE
}

log() {
  printf '[device-smoke] %s\n' "$*"
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "${LOG_PID}" ]]; then
    kill "${LOG_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT

verify_prereqs() {
  if [[ ! -x "${ADB}" ]]; then
    die "adb not found at ${ADB}. Set ANDROID_HOME or ANDROID_SDK_ROOT."
  fi

  if [[ ! -f "${APK_PATH}" ]]; then
    die "APK not found at ${APK_PATH}. Build with './gradlew assembleDebug' first, or set APK_PATH."
  fi

  log "adb: ${ADB}"
  log "apk: ${APK_PATH}"
}

check_device() {
  local devices
  devices="$("${ADB}" devices 2>/dev/null | tail -n +2 | grep -v '^$' || true)"

  if [[ -z "${devices}" ]]; then
    die "No connected device or emulator. Connect a device via USB or start an emulator, then re-run."
  fi

  local count
  count=$(printf '%s\n' "${devices}" | wc -l)

  if [[ "${count}" -gt 1 ]]; then
    die "Multiple devices attached. Use 'adb -s <serial>' to target one, or disconnect extras."
  fi

  local status
  status=$(printf '%s\n' "${devices}" | awk '{print $2}')

  if [[ "${status}" != "device" ]]; then
    die "Device is not ready (status: ${status}). Wait for boot to complete."
  fi

  log "device connected and ready"
}

install_apk() {
  log "installing debug APK..."
  "${ADB}" install -r "${APK_PATH}"
  log "APK installed"
}

enable_ime() {
  log "listing enabled IMEs..."
  "${ADB}" shell ime list -s || true

  log "enabling KnowSayin IME: ${IME_COMPONENT}"
  "${ADB}" shell ime enable "${IME_COMPONENT}" 2>/dev/null || {
    log "ime enable returned non-zero (may already be enabled)"
  }

  log "setting KnowSayin IME as default..."
  "${ADB}" shell ime set "${IME_COMPONENT}" 2>/dev/null || {
    log "ime set returned non-zero (IME may need manual selection in Settings)"
  }

  log "current enabled IMEs:"
  "${ADB}" shell ime list -s || true
}

logcat_helper() {
  local tag_filter="KnowSayin\|Rime\|knowsayin-rime\|AndroidRuntime"
  log "starting filtered logcat (${tag_filter}). Press Ctrl+C to stop."
  "${ADB}" logcat -v brief 2>/dev/null | grep --line-buffered -E "${tag_filter}" || true
}

print_smoke_steps() {
  cat <<STEPS

=== Manual Smoke Steps ===
1. Open any text app (e.g. Messaging, Notes, or a browser search field).
2. Switch to the KnowSayin keyboard (globe key or IME switcher).
3. Type fixed test samples on the KnowSayin keyboard:

   nihao  -> should show Chinese candidate(s), e.g. "你好"
   ba ba  -> should show Chinese candidate(s), e.g. "爸爸"

4. Tap a candidate to commit it. Verify the text appears in the input field.
5. Press Backspace. Verify it deletes one character at a time.
6. Press the CN/EN toggle. Verify the keyboard switches between Chinese (pinyin
   candidates) and direct English mode (QWERTY typing with no candidates).
7. Press the optimize button. Verify the status shows a brief progress/result
   indicator (not a raw native engine string).
8. Press the microphone button. Verify voice permission prompt or voice status.
9. Press the undo button. Verify "nothing to undo" or reversion of last optimize.

=== Post-Smoke Cleanup ===
  adb uninstall ${APP_ID}
STEPS
}

main() {
  local do_logcat=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h)
        usage
        exit 0
        ;;
      --logcat)
        do_logcat=1
        shift
        ;;
      *)
        die "unknown option: $1"
        ;;
    esac
  done

  verify_prereqs
  check_device
  install_apk
  enable_ime
  print_smoke_steps

  if [[ "${do_logcat}" == "1" ]]; then
    logcat_helper
  fi
}

main "$@"
