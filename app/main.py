from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import objc
import Quartz
from ApplicationServices import (
    AXIsProcessTrusted,
    AXIsProcessTrustedWithOptions,
    kAXTrustedCheckOptionPrompt,
)
from AppKit import (
    NSAlert,
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivateIgnoringOtherApps,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSPopUpButton,
    NSScreen,
    NSStatusBar,
    NSTextField,
    NSVisualEffectView,
    NSWorkspace,
    NSEvent,
)
from Foundation import NSAttributedString, NSLocale, NSObject, NSTimer
from PyObjCTools import AppHelper

from .model_config import (
    APP_NAME,
    APP_VERSION,
    ENV_PATH,
    DEFAULT_OPTIMIZE_HOTKEY,
    DEFAULT_UNDO_HOTKEY,
    DEFAULT_LANG1_CODE,
    DEFAULT_LANG1_HOTKEY,
    DEFAULT_LANG2_CODE,
    DEFAULT_LANG2_HOTKEY,
    get_active_model_config,
    load_model_settings,
    save_desktop_settings,
)
from .credit_game import CREDIT_GAME_DELTA, CreditQuestion, random_credit_question
from .optimizer import optimize_prompt
from .paste import CapturedText, capture_focused_text, replace_captured_text


APP_BUNDLE_ID = "com.knowsayin.app"
APP_BUNDLE_PATH = "/Applications/KnowSayin.app"
SHARE_DOWNLOAD_URL = "https://knowsayin.com/download"
SHARE_INSTALL_COMMAND = "curl -fsSL https://knowsayin.com/install-macos.sh | bash"


@dataclass(frozen=True)
class HotkeySpec:
    raw: str
    kind: str
    modifiers: frozenset[str]
    keycode: int | None = None
    tap_modifier: str | None = None
    tap_count: int = 0


SUPPORTED_LANGUAGES = [
    ("zh", "中文 (Chinese)"),
    ("en", "English (英文)"),
    ("ja", "日本語 (Japanese)"),
    ("ko", "한국어 (Korean)"),
    ("es", "Español (Spanish)"),
    ("fr", "Français (French)"),
    ("de", "Deutsch (German)"),
    ("ru", "Русский (Russian)"),
    ("pt", "Português (Portuguese)"),
    ("it", "Italiano (Italian)"),
]


class JustSayingApp(NSObject):
    def applicationDidFinishLaunching_(self, notification) -> None:
        self.busy = False
        self.own_pid = os.getpid()
        self.target_app = None
        self.target_pid = None
        self.target_name = None
        self.last_original: str | None = None
        self.last_capture: CapturedText | None = None
        self.hotkey_down: dict[str, bool] = {"optimize": False, "undo": False, "lang1": False, "lang2": False}
        self.previous_modifier_flags = 0
        self.tap_state: dict[str, tuple[int, float]] = {"optimize": (0, 0.0), "undo": (0, 0.0), "lang1": (0, 0.0), "lang2": (0, 0.0)}
        self.hotkey_handlers = []
        self.hotkey_monitors = []
        self.key_event_tap = None
        self.key_event_source = None
        self.key_event_callback = None
        self.needs_accessibility = False
        self.needs_input_monitoring = False
        self.permission_notice_keys: set[str] = set()
        self.last_key_tap_attempt = 0.0
        self.quota_remaining: int | None = None
        self.quota_daily_limit: int | None = None
        self.quota_refill_at = ""
        self.machine_code = ""
        self.extra_url = "https://knowsayin.com"
        self.cloud_plan = "free"
        self.quota_refreshing = False
        self.cloud_available = False
        self.credit_question: CreditQuestion | None = None
        self.credit_game_busy = False
        self.credit_game_next_play_at = ""
        self.credit_game_reset_at = ""
        self.credit_game_remaining_plays: int | None = None
        self.credit_game_limit = 2
        self.credit_game_window_seconds = 60
        self.active_hotkey_capture: str | None = None
        self.hotkey_capture_flags: dict[str, int] = {"optimize": 0, "undo": 0, "lang1": 0, "lang2": 0}
        self.hotkey_capture_taps: dict[str, tuple[str, int, float]] = {
            "optimize": ("", 0, 0.0),
            "undo": ("", 0, 0.0),
            "lang1": ("", 0, 0.0),
            "lang2": ("", 0, 0.0),
        }
        self.settings_hotkey_monitor = None
        self._reload_hotkeys_from_settings()
        self.buttons: list[NSButton] = []
        self.window = self._build_window()
        self._install_status_item()
        self._request_accessibility_permission(show_help=True)
        self._install_hotkeys()
        self.tracker = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.25,
            self,
            "trackFrontApp:",
            None,
            True,
        )
        self.permission_tracker = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            2.0,
            self,
            "checkPermissions:",
            None,
            True,
        )
        self.cloud_tracker = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            60.0,
            self,
            "refreshCloudStatus:",
            None,
            True,
        )
        self.credit_countdown_tracker = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0,
            self,
            "refreshCreditSnackCountdown:",
            None,
            True,
        )
        self.window.orderFrontRegardless()
        self._refresh_cloud_quota_async()

    def windowWillClose_(self, notification) -> None:
        NSApp.terminate_(self)

    def trackFrontApp_(self, timer) -> None:
        front_app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if not front_app:
            return

        pid = front_app.processIdentifier()
        if pid == self.own_pid:
            return

        if pid == self.target_pid:
            return

        self.target_app = front_app
        self.target_pid = pid
        self.target_name = front_app.localizedName() or "target app"
        if not self.busy:
            self._set_status(self._ready_status())

    def optimize_(self, sender) -> None:
        self._start_optimize()

    def quotaButton_(self, sender) -> None:
        self._show_settings_window()

    def undo_(self, sender) -> None:
        self._start_undo()

    def hideFloatingWindow_(self, sender) -> None:
        self._hide_floating_window()

    def showFloatingWindow_(self, sender) -> None:
        self._show_floating_window()

    def openPermissions_(self, sender) -> None:
        self._request_system_accessibility_permission()

    def revealApp_(self, sender) -> None:
        self._reveal_app_in_finder()

    def openSettings_(self, sender) -> None:
        self._show_settings_window()

    def checkUpdate_(self, sender) -> None:
        self._set_status("Checking for KnowSayin updates...")
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def openShare_(self, sender) -> None:
        self._show_share_window()

    def copyShareWebsite_(self, sender) -> None:
        self._copy_share_text("website")

    def copyShareTerminal_(self, sender) -> None:
        self._copy_share_text("terminal")

    def copyShareAgent_(self, sender) -> None:
        self._copy_share_text("agent")

    def answerCreditSnackFirst_(self, sender) -> None:
        self._submit_credit_snack_answer(0)

    def answerCreditSnackSecond_(self, sender) -> None:
        self._submit_credit_snack_answer(1)

    def closeShare_(self, sender) -> None:
        if hasattr(self, "share_window"):
            self.share_window.orderOut_(self)

    def saveSettings_(self, sender) -> None:
        optimize_hotkey = str(self.optimize_hotkey_field.stringValue()).strip()
        undo_hotkey = str(self.undo_hotkey_field.stringValue()).strip()
        lang1_hotkey = str(self.lang1_hotkey_field.stringValue()).strip()
        lang2_hotkey = str(self.lang2_hotkey_field.stringValue()).strip()

        lang1_title = self.lang1_pop_up.titleOfSelectedItem()
        lang2_title = self.lang2_pop_up.titleOfSelectedItem()

        lang1_code = DEFAULT_LANG1_CODE
        for code, label in SUPPORTED_LANGUAGES:
            if label == lang1_title:
                lang1_code = code
                break

        lang2_code = DEFAULT_LANG2_CODE
        for code, label in SUPPORTED_LANGUAGES:
            if label == lang2_title:
                lang2_code = code
                break

        if not self._validate_settings_fields():
            return

        try:
            save_desktop_settings(
                optimize_hotkey=optimize_hotkey or DEFAULT_OPTIMIZE_HOTKEY,
                undo_hotkey=undo_hotkey or DEFAULT_UNDO_HOTKEY,
                lang1_code=lang1_code,
                lang1_hotkey=lang1_hotkey or DEFAULT_LANG1_HOTKEY,
                lang2_code=lang2_code,
                lang2_hotkey=lang2_hotkey or DEFAULT_LANG2_HOTKEY,
            )
        except Exception as exc:
            self.settings_status.setStringValue_(f"Save failed: {exc}")
            return

        self._reload_hotkeys_from_settings()
        self._sync_key_event_tap()
        self._update_hotkey_tooltips()
        self.settings_status.setStringValue_(_localized("Saved.", "已保存。"))
        self._set_status(self._ready_status())
        self._refresh_cloud_quota_async()
        self.active_hotkey_capture = None
        self.settings_window.orderOut_(self)

    def cancelSettings_(self, sender) -> None:
        self.active_hotkey_capture = None
        self.settings_window.orderOut_(self)

    @objc.python_method
    def _start_optimize(self, target_lang: str | None = None) -> None:
        if self.busy:
            return
        if self._quota_exhausted():
            self._open_extra_page()
            return
        if not AXIsProcessTrusted():
            self._request_accessibility_permission(show_help=True)
            return

        self._set_status("Reading the focused text field...")
        self._set_busy(True)
        self._set_button_title(self.optimize_button, "...", primary=True)
        threading.Thread(target=self._optimize_worker, args=(target_lang,), daemon=True).start()

    @objc.python_method
    def _start_undo(self) -> None:
        if self.busy:
            return
        if not self.last_original or self.last_capture is None:
            self._set_status("Nothing to undo.")
            if hasattr(self, "undo_button"):
                self._set_button_title(self.undo_button, "No", primary=False)
                self._reset_title_later()
            return

        self._set_status("Restoring the previous text...")
        self._set_busy(True)
        self._set_button_title(self.undo_button, "...", primary=False)
        threading.Thread(target=self._restore_worker, daemon=True).start()

    @objc.python_method
    def _optimize_worker(self, target_lang: str | None = None) -> None:
        try:
            time.sleep(0.12)
            self._activate_target_app()
            captured = capture_focused_text(self.target_pid)
            original = captured.text.strip()
            if not original:
                raise RuntimeError("The focused text field is empty.")

            AppHelper.callAfter(self._set_status, "Optimizing text...")
            cleaned = optimize_prompt(original, "medium", target_lang=target_lang).strip()
            if not cleaned:
                raise RuntimeError("The optimized result was empty, so nothing was replaced.")

            self._activate_target_app()
            replace_captured_text(captured, cleaned)
            self.last_original = original
            self.last_capture = captured
            AppHelper.callAfter(self._finish, f"Replaced via {captured.method}.")
        except Exception as exc:
            AppHelper.callAfter(self._fail, str(exc))

    @objc.python_method
    def _restore_worker(self) -> None:
        try:
            self._activate_target_app()
            if self.last_capture is None:
                raise RuntimeError("There is no previous text to restore.")
            replace_captured_text(self.last_capture, self.last_original or "")
            AppHelper.callAfter(self._finish_undo, "Restored the previous text.")
        except Exception as exc:
            AppHelper.callAfter(self._fail, str(exc))

    @objc.python_method
    def _finish(self, message: str) -> None:
        self._set_status(message)
        self._set_busy(False)
        self._set_button_title(self.optimize_button, "Done", primary=True)
        self._reset_title_later()
        self._refresh_cloud_quota_async()

    @objc.python_method
    def _finish_undo(self, message: str) -> None:
        self.last_original = None
        self.last_capture = None
        self._set_status(message)
        self._set_busy(False)
        self._set_button_title(self.undo_button, "OK", primary=False)
        self._reset_title_later()

    @objc.python_method
    def _fail(self, message: str) -> None:
        self._set_status(f"Failed: {message}")
        self._set_busy(False)
        self._set_button_title(self.optimize_button, "Failed", primary=True)
        self._reset_title_later()
        self._refresh_cloud_quota_async()

    @objc.python_method
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for button in self.buttons:
            button.setEnabled_(not busy)
        if hasattr(self, "quota_button"):
            self.quota_button.setEnabled_(True)
        if hasattr(self, "hide_button"):
            self.hide_button.setEnabled_(True)
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled_((not busy) and bool(self.last_original))
        self._refresh_connection_indicator()

    @objc.python_method
    def _set_status(self, message: str) -> None:
        self.status_message = message
        if hasattr(self, "optimize_button"):
            self.optimize_button.setToolTip_(self._status_tooltip(message))
        self._refresh_connection_indicator()

    @objc.python_method
    def _reset_title_later(self) -> None:
        threading.Timer(1.1, lambda: AppHelper.callAfter(self._reset_optimize_title)).start()

    @objc.python_method
    def _reset_optimize_title(self) -> None:
        if self.busy:
            return
        if hasattr(self, "optimize_button"):
            title = "Get extra" if self._quota_exhausted() else "Optimize"
            self._set_button_title(self.optimize_button, title, primary=True)
        if hasattr(self, "undo_button"):
            self._set_button_title(self.undo_button, "Undo", primary=False)
            self.undo_button.setEnabled_(bool(self.last_original))
        if hasattr(self, "quota_button"):
            self._refresh_quota_label()
        self._refresh_connection_indicator()

    @objc.python_method
    def _install_status_item(self) -> None:
        length = _appkit_constant("NSVariableStatusItemLength", "NSVariableStatusItemLength")
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(length)
        button = self.status_item.button()
        if button is not None:
            button.setTitle_("KS")
            button.setToolTip_(APP_NAME)

        menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        for title, action in (
            ("Show Floating Window", "showFloatingWindow:"),
            ("Settings", "openSettings:"),
            ("Check for Updates", "checkUpdate:"),
            ("Open Accessibility Settings", "openPermissions:"),
            ("Reveal KnowSayin.app", "revealApp:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            menu.addItem_(item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit", "terminate:", "q")
        quit_item.setTarget_(NSApp)
        menu.addItem_(quit_item)
        self.status_item.setMenu_(menu)

    @objc.python_method
    def _hide_floating_window(self) -> None:
        if hasattr(self, "window"):
            self.window.orderOut_(self)

    @objc.python_method
    def _show_floating_window(self) -> None:
        if not hasattr(self, "window"):
            return
        self.window.orderFrontRegardless()
        self._set_status(self._ready_status())

    @objc.python_method
    def _request_accessibility_permission(self, show_help: bool = False) -> bool:
        if AXIsProcessTrusted():
            self.needs_accessibility = False
            self._refresh_connection_indicator()
            return True

        self.needs_accessibility = True
        self._set_status("macOS Accessibility permission is required.")
        if show_help:
            self._request_system_accessibility_permission()
        return False

    @objc.python_method
    def _open_permission_settings(self, kind: str = "accessibility", reset_stale: bool = True) -> None:
        import subprocess

        urls = []
        if kind in {"all", "accessibility"}:
            if reset_stale and not AXIsProcessTrusted():
                self._reset_accessibility_permission()
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        if kind in {"all", "input"}:
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent")
        if not urls:
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        for url in urls:
            subprocess.run(["open", url], check=False)

    @objc.python_method
    def _request_system_accessibility_permission(self) -> None:
        if AXIsProcessTrusted():
            self.needs_accessibility = False
            self._set_status("Accessibility permission is already authorized.")
            self._refresh_connection_indicator()
            return

        self._reset_accessibility_permission()
        try:
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        except Exception:
            self._open_permission_settings("accessibility", reset_stale=False)
        self._set_status("Turn on KnowSayin in Accessibility settings.")

    @objc.python_method
    def _reset_accessibility_permission(self) -> None:
        import subprocess

        try:
            result = subprocess.run(
                ["tccutil", "reset", "Accessibility", APP_BUNDLE_ID],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            self._set_status("Could not reset Accessibility permission; remove and re-add KnowSayin manually.")
            return

        if result.returncode == 0:
            self._set_status("Reset stale Accessibility permission. Re-add KnowSayin.app in System Settings.")
        else:
            self._set_status("Could not reset Accessibility permission; remove and re-add KnowSayin manually.")

    @objc.python_method
    def _reveal_app_in_finder(self) -> None:
        import subprocess

        subprocess.run(["open", "-R", APP_BUNDLE_PATH], check=False)
        self._set_status(f"Revealed {APP_BUNDLE_PATH}.")

    @objc.python_method
    def _show_permission_notice(self, key: str, title: str, message: str) -> None:
        if key in self.permission_notice_keys:
            return
        self.permission_notice_keys.add(key)
        try:
            NSApp.activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_(title)
            alert.setInformativeText_(message)
            if key == "input-monitoring":
                alert.addButtonWithTitle_("Open Input Monitoring Settings")
            else:
                alert.addButtonWithTitle_("Ask macOS for Permission")
            alert.addButtonWithTitle_("Not Now")
            response = alert.runModal()
            if int(response) == 1000:
                if key == "input-monitoring":
                    self._open_permission_settings("input")
                else:
                    self._request_system_accessibility_permission()
        except Exception:
            pass

    @objc.python_method
    def _check_update_worker(self) -> None:
        try:
            from .cloud_client import get_cloud_config

            model_config = get_active_model_config()
            config = get_cloud_config(model_config.base_url)
            latest = str(config.get("latestVersion") or APP_VERSION)
            download_url = str(config.get("downloadUrl") or "https://knowsayin.com/download")
            if latest == APP_VERSION:
                message = f"You are on the latest version ({APP_VERSION})."
            else:
                message = f"You are on {APP_VERSION}; the latest version is {latest}. Download it from {download_url}."
            AppHelper.callAfter(self._show_update_notice, message)
        except Exception as exc:
            AppHelper.callAfter(self._show_update_notice, f"Update check failed: {exc}")

    @objc.python_method
    def _show_update_notice(self, message: str) -> None:
        self._set_status(message)
        try:
            NSApp.activateIgnoringOtherApps_(True)
            alert = NSAlert.alloc().init()
            alert.setMessageText_("KnowSayin Update")
            alert.setInformativeText_(message)
            alert.addButtonWithTitle_("OK")
            alert.runModal()
        except Exception:
            pass

    @objc.python_method
    def _copy_machine_code(self) -> None:
        if not self.machine_code:
            return
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(self.machine_code, NSPasteboardTypeString)
        self._set_status(f"Machine code copied: {self.machine_code}")
        if hasattr(self, "quota_button"):
            self._set_button_title(self.quota_button, "Copied", primary=False)
        self._reset_title_later()

    @objc.python_method
    def _open_extra_page(self) -> None:
        import subprocess
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        url = self.extra_url or "https://knowsayin.com"
        if self.machine_code:
            parsed = urlparse(url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query.setdefault("machine", self.machine_code)
            url = urlunparse(parsed._replace(query=urlencode(query)))
        subprocess.run(["open", url], check=False)
        self._set_status("Opening KnowSayin website...")

    @objc.python_method
    def _install_hotkeys(self) -> None:
        mask = _appkit_constant("NSEventMaskFlagsChanged", "NSFlagsChangedMask")

        def global_handler(event) -> None:
            self._handle_flags_changed(event)

        def local_handler(event):
            self._handle_flags_changed(event)
            return event

        self.hotkey_handlers = [global_handler, local_handler]
        self.hotkey_monitors = [
            NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(mask, global_handler),
            NSEvent.addLocalMonitorForEventsMatchingMask_handler_(mask, local_handler),
        ]
        if self._needs_key_event_tap():
            self._install_key_event_tap(show_notice=True)
        else:
            self._remove_key_event_tap()

    def controlTextDidBeginEditing_(self, notification) -> None:
        control = notification.object()
        if hasattr(self, "optimize_hotkey_field") and control == self.optimize_hotkey_field:
            self._begin_hotkey_capture("optimize")
        elif hasattr(self, "undo_hotkey_field") and control == self.undo_hotkey_field:
            self._begin_hotkey_capture("undo")
        elif hasattr(self, "lang1_hotkey_field") and control == self.lang1_hotkey_field:
            self._begin_hotkey_capture("lang1")
        elif hasattr(self, "lang2_hotkey_field") and control == self.lang2_hotkey_field:
            self._begin_hotkey_capture("lang2")

    def controlTextDidEndEditing_(self, notification) -> None:
        control = notification.object()
        if (
            (hasattr(self, "optimize_hotkey_field") and control == self.optimize_hotkey_field)
            or (hasattr(self, "undo_hotkey_field") and control == self.undo_hotkey_field)
            or (hasattr(self, "lang1_hotkey_field") and control == self.lang1_hotkey_field)
            or (hasattr(self, "lang2_hotkey_field") and control == self.lang2_hotkey_field)
        ):
            self.active_hotkey_capture = None

    @objc.python_method
    def _begin_hotkey_capture(self, action: str) -> None:
        self.active_hotkey_capture = action
        self.hotkey_capture_flags[action] = 0
        self.hotkey_capture_taps[action] = ("", 0, 0.0)
        label = _hotkey_action_label(action)
        self.settings_status.setStringValue_(
            _localized(
                f"Press the {label} shortcut. It will be captured automatically.",
                f"直接按下 {label} 快捷键，会自动识别。",
            ),
        )

    @objc.python_method
    def _install_settings_hotkey_monitor(self) -> None:
        if self.settings_hotkey_monitor is not None:
            return

        mask = _appkit_constant("NSEventMaskKeyDown", "NSKeyDownMask") | _appkit_constant(
            "NSEventMaskFlagsChanged",
            "NSFlagsChangedMask",
        )

        def settings_hotkey_handler(event):
            if self._capture_settings_hotkey_event(event):
                return None
            return event

        self.settings_hotkey_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask,
            settings_hotkey_handler,
        )

    @objc.python_method
    def _settings_visible(self) -> bool:
        return bool(
            hasattr(self, "settings_window")
            and self.settings_window
            and self.settings_window.isVisible()
        )

    @objc.python_method
    def _capture_settings_hotkey_event(self, event) -> bool:
        if not self._settings_visible():
            return False
        action = self.active_hotkey_capture
        if action not in {"optimize", "undo", "lang1", "lang2"}:
            return False
        event_window = event.window()
        if event_window is not None and event_window != self.settings_window:
            return False

        event_type = int(event.type())
        if event_type == _appkit_constant("NSEventTypeFlagsChanged", "NSFlagsChanged"):
            return self._capture_modifier_hotkey(action, event)
        if event_type == _appkit_constant("NSEventTypeKeyDown", "NSKeyDown"):
            return self._capture_key_hotkey(action, event)
        return False

    @objc.python_method
    def _capture_modifier_hotkey(self, action: str, event) -> bool:
        flags = int(event.modifierFlags())
        previous_flags = self.hotkey_capture_flags.get(action, 0)
        self.hotkey_capture_flags[action] = flags

        active = _active_modifier_names(flags, quartz=False)
        previous_active = _active_modifier_names(previous_flags, quartz=False)
        if not active:
            return True
        if len(active) < len(previous_active):
            return True

        if len(active) == 1:
            modifier = next(iter(active))
            now = time.monotonic()
            previous_modifier, count, last_time = self.hotkey_capture_taps.get(action, ("", 0, 0.0))
            if previous_modifier == modifier and not previous_active and now - last_time <= 0.7:
                count += 1
            else:
                count = 1

            if count >= 3:
                self.hotkey_capture_taps[action] = (modifier, 0, now)
                self._set_captured_hotkey(action, f"{modifier}*3")
                return True

            self.hotkey_capture_taps[action] = (modifier, count, now)
            self._set_captured_hotkey(action, _format_hotkey(active))
            return True

        self.hotkey_capture_taps[action] = ("", 0, 0.0)
        self._set_captured_hotkey(action, _format_hotkey(active))
        return True

    @objc.python_method
    def _capture_key_hotkey(self, action: str, event) -> bool:
        modifiers = _active_modifier_names(int(event.modifierFlags()), quartz=False)
        key_name = KEY_NAMES_BY_CODE.get(int(event.keyCode()))
        if key_name is None:
            self.settings_status.setStringValue_(_localized("That key is not supported yet.", "暂不支持这个按键。"))
            return True
        if not modifiers:
            self.settings_status.setStringValue_(
                _localized("Use at least one modifier, such as Option or Command.", "请至少包含一个修饰键，比如 Option 或 Command。"),
            )
            return True

        self.hotkey_capture_taps[action] = ("", 0, 0.0)
        self._set_captured_hotkey(action, _format_hotkey(modifiers, key_name))
        return True

    @objc.python_method
    def _set_captured_hotkey(self, action: str, raw: str) -> None:
        if action == "optimize":
            field = self.optimize_hotkey_field
        elif action == "undo":
            field = self.undo_hotkey_field
        elif action == "lang1":
            field = self.lang1_hotkey_field
        elif action == "lang2":
            field = self.lang2_hotkey_field
        else:
            return
        field.setStringValue_(raw)
        label = _hotkey_action_label(action)
        self._validate_settings_fields(
            _localized(
                f"Captured {label}: {raw}. Click Save to apply.",
                f"已识别 {label}: {raw}。点击保存后生效。",
            ),
        )

    @objc.python_method
    def _reload_hotkeys_from_settings(self) -> None:
        data = load_model_settings()
        try:
            self.optimize_hotkey = _parse_hotkey(data.get("optimize_hotkey") or DEFAULT_OPTIMIZE_HOTKEY)
        except ValueError:
            self.optimize_hotkey = _parse_hotkey(DEFAULT_OPTIMIZE_HOTKEY)
        try:
            self.undo_hotkey = _parse_hotkey(data.get("undo_hotkey") or DEFAULT_UNDO_HOTKEY)
        except ValueError:
            self.undo_hotkey = _parse_hotkey(DEFAULT_UNDO_HOTKEY)
        try:
            self.lang1_hotkey = _parse_hotkey(data.get("lang1_hotkey") or DEFAULT_LANG1_HOTKEY)
        except ValueError:
            self.lang1_hotkey = _parse_hotkey(DEFAULT_LANG1_HOTKEY)
        try:
            self.lang2_hotkey = _parse_hotkey(data.get("lang2_hotkey") or DEFAULT_LANG2_HOTKEY)
        except ValueError:
            self.lang2_hotkey = _parse_hotkey(DEFAULT_LANG2_HOTKEY)
        self.lang1_code = data.get("lang1_code") or DEFAULT_LANG1_CODE
        self.lang2_code = data.get("lang2_code") or DEFAULT_LANG2_CODE

        self.hotkey_down = {"optimize": False, "undo": False, "lang1": False, "lang2": False}
        self.tap_state = {"optimize": (0, 0.0), "undo": (0, 0.0), "lang1": (0, 0.0), "lang2": (0, 0.0)}

    @objc.python_method
    def _update_hotkey_tooltips(self) -> None:
        if hasattr(self, "optimize_button"):
            self.optimize_button.setToolTip_(
                self._status_tooltip(self._ready_status()),
            )
        if hasattr(self, "undo_button"):
            self.undo_button.setToolTip_(f"Undo: {self.undo_hotkey.raw}")

    @objc.python_method
    def _needs_key_event_tap(self) -> bool:
        return (
            self.optimize_hotkey.kind == "key"
            or self.undo_hotkey.kind == "key"
            or self.lang1_hotkey.kind == "key"
            or self.lang2_hotkey.kind == "key"
        )

    @objc.python_method
    def _sync_key_event_tap(self) -> None:
        if self._needs_key_event_tap():
            self._install_key_event_tap(show_notice=True)
        else:
            self._remove_key_event_tap()

    @objc.python_method
    def _remove_key_event_tap(self) -> None:
        if self.key_event_tap is None:
            return
        try:
            Quartz.CGEventTapEnable(self.key_event_tap, False)
            if self.key_event_source is not None:
                Quartz.CFRunLoopRemoveSource(
                    Quartz.CFRunLoopGetCurrent(),
                    self.key_event_source,
                    Quartz.kCFRunLoopCommonModes,
                )
        except Exception:
            pass
        self.key_event_tap = None
        self.key_event_source = None
        self.key_event_callback = None
        self.needs_input_monitoring = False

    @objc.python_method
    def _install_key_event_tap(self, show_notice: bool = False) -> None:
        if not self._needs_key_event_tap():
            self._remove_key_event_tap()
            return
        if self.key_event_tap is not None:
            return

        self.last_key_tap_attempt = time.monotonic()
        event_mask = 1 << Quartz.kCGEventKeyDown

        def key_event_callback(proxy, event_type, event, refcon):
            if event_type in (
                Quartz.kCGEventTapDisabledByTimeout,
                Quartz.kCGEventTapDisabledByUserInput,
            ):
                if self.key_event_tap is not None:
                    Quartz.CGEventTapEnable(self.key_event_tap, True)
                return event

            action = self._key_hotkey_action(event_type, event)
            if action == "optimize":
                AppHelper.callAfter(self._start_optimize)
                return None
            if action == "undo":
                AppHelper.callAfter(self._start_undo)
                return None
            if action == "lang1":
                AppHelper.callAfter(self._start_optimize, self.lang1_code)
                return None
            if action == "lang2":
                AppHelper.callAfter(self._start_optimize, self.lang2_code)
                return None

            return event

        self.key_event_callback = key_event_callback
        self.key_event_tap = Quartz.CGEventTapCreate(
            Quartz.kCGHIDEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            event_mask,
            self.key_event_callback,
            None,
        )
        if self.key_event_tap is None:
            if AXIsProcessTrusted():
                self.needs_input_monitoring = True
                self._set_status("This hotkey needs Input Monitoring permission.")
                if show_notice:
                    self._show_permission_notice(
                        "input-monitoring",
                        "Hotkey Needs Input Monitoring",
                        "Open macOS Input Monitoring settings and turn on KnowSayin, or change the hotkey back to option+shift. The default option+shift hotkey does not need Input Monitoring.",
                    )
            else:
                self.needs_accessibility = True
                self.needs_input_monitoring = False
            return

        self.needs_input_monitoring = False
        self.key_event_source = Quartz.CFMachPortCreateRunLoopSource(
            None,
            self.key_event_tap,
            0,
        )
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(),
            self.key_event_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(self.key_event_tap, True)

    def checkPermissions_(self, timer) -> None:
        had_warning = self.needs_accessibility or self.needs_input_monitoring
        if self.needs_accessibility and AXIsProcessTrusted():
            self.needs_accessibility = False

        if self._needs_key_event_tap() and self.key_event_tap is None:
            if time.monotonic() - self.last_key_tap_attempt >= 5.0:
                self._install_key_event_tap(show_notice=False)
        elif not self._needs_key_event_tap():
            self.needs_input_monitoring = False

        has_warning = self.needs_accessibility or self.needs_input_monitoring
        self._refresh_connection_indicator()
        if had_warning and not has_warning and not self.busy:
            self._set_status(self._ready_status())

    def refreshCloudStatus_(self, timer) -> None:
        self._refresh_cloud_quota_async()

    def refreshCreditSnackCountdown_(self, timer) -> None:
        self._refresh_credit_snack_countdown()

    @objc.python_method
    def _key_hotkey_action(self, event_type, event) -> str | None:
        if self._settings_visible():
            return None
        if event_type != Quartz.kCGEventKeyDown:
            return None
        for action, hotkey in (
            ("optimize", self.optimize_hotkey),
            ("undo", self.undo_hotkey),
            ("lang1", self.lang1_hotkey),
            ("lang2", self.lang2_hotkey),
        ):
            if hotkey.kind == "key" and self._matches_key_hotkey(event, hotkey):
                return action
        return None

    @objc.python_method
    def _matches_key_hotkey(self, event, hotkey: HotkeySpec) -> bool:
        keycode = Quartz.CGEventGetIntegerValueField(
            event,
            Quartz.kCGKeyboardEventKeycode,
        )
        if hotkey.keycode is None or keycode != hotkey.keycode:
            return False

        flags = int(Quartz.CGEventGetFlags(event))
        active = _active_modifier_names(flags, quartz=True)
        return active == hotkey.modifiers

    @objc.python_method
    def _handle_flags_changed(self, event) -> None:
        flags = int(event.modifierFlags())
        if self._settings_visible():
            self.previous_modifier_flags = flags
            return
        for action, hotkey in (
            ("optimize", self.optimize_hotkey),
            ("undo", self.undo_hotkey),
            ("lang1", self.lang1_hotkey),
            ("lang2", self.lang2_hotkey),
        ):
            if hotkey.kind == "modifier":
                self._handle_modifier_combo(action, hotkey, flags)
            elif hotkey.kind == "tap":
                self._handle_tap_hotkey(action, hotkey, flags)
        self.previous_modifier_flags = flags

    @objc.python_method
    def _handle_modifier_combo(self, action: str, hotkey: HotkeySpec, flags: int) -> None:
        active = _active_modifier_names(flags, quartz=False) == hotkey.modifiers
        if active and not self.hotkey_down.get(action, False):
            self.hotkey_down[action] = True
            AppHelper.callAfter(self._run_hotkey_action, action)
        elif not active:
            self.hotkey_down[action] = False

    @objc.python_method
    def _handle_tap_hotkey(self, action: str, hotkey: HotkeySpec, flags: int) -> None:
        if hotkey.tap_modifier is None:
            return
        mask = _modifier_mask(hotkey.tap_modifier, quartz=False)
        active_modifiers = _active_modifier_names(flags, quartz=False)
        was_down = bool(self.previous_modifier_flags & mask)
        is_down = bool(flags & mask)
        if not is_down or was_down or active_modifiers != frozenset({hotkey.tap_modifier}):
            return

        now = time.monotonic()
        count, last_time = self.tap_state.get(action, (0, 0.0))
        count = count + 1 if now - last_time <= 0.55 else 1
        if count >= hotkey.tap_count:
            self.tap_state[action] = (0, 0.0)
            AppHelper.callAfter(self._run_hotkey_action, action)
            return
        self.tap_state[action] = (count, now)

    @objc.python_method
    def _run_hotkey_action(self, action: str) -> None:
        if action == "optimize":
            self._start_optimize()
        elif action == "undo":
            self._start_undo()
        elif action == "lang1":
            self._start_optimize(self.lang1_code)
        elif action == "lang2":
            self._start_optimize(self.lang2_code)

    @objc.python_method
    def _refresh_cloud_quota_async(self) -> None:
        try:
            model_config = get_active_model_config()
        except Exception:
            self.cloud_available = False
            self.quota_remaining = None
            self.quota_daily_limit = None
            self._refresh_quota_label()
            self._refresh_connection_indicator()
            return

        if not model_config.is_cloud:
            self.cloud_available = False
            self.quota_refreshing = False
            self.quota_remaining = None
            self.quota_daily_limit = None
            self._refresh_quota_label()
            self._refresh_connection_indicator()
            return

        if self.quota_refreshing:
            return

        self.quota_refreshing = True
        self._refresh_quota_label()
        threading.Thread(
            target=self._cloud_quota_worker,
            args=(model_config.base_url,),
            daemon=True,
        ).start()

    @objc.python_method
    def _cloud_quota_worker(self, base_url: str) -> None:
        try:
            from .cloud_client import get_cloud_usage

            usage = get_cloud_usage(base_url)
            AppHelper.callAfter(self._finish_cloud_quota, usage)
        except Exception as exc:
            AppHelper.callAfter(self._fail_cloud_quota, str(exc))

    @objc.python_method
    def _finish_cloud_quota(self, usage: dict) -> None:
        self.quota_refreshing = False
        self.cloud_available = True
        self.quota_remaining = _int_or_none(usage.get("remaining"))
        self.quota_daily_limit = _int_or_none(usage.get("quotaLimit") or usage.get("dailyLimit"))
        self.quota_refill_at = str(usage.get("refillAt") or usage.get("resetAt") or "")
        self.machine_code = str(usage.get("deviceCode") or self.machine_code or "").strip().upper()
        self.extra_url = str(usage.get("extraUrl") or self.extra_url or "https://knowsayin.com").strip()
        self.cloud_plan = str(usage.get("plan") or self.cloud_plan or "free").strip().lower()
        self._refresh_quota_label()
        self._reset_optimize_title()
        self._refresh_connection_indicator()

    @objc.python_method
    def _fail_cloud_quota(self, message: str) -> None:
        self.quota_refreshing = False
        self.cloud_available = False
        self.quota_remaining = None
        self.quota_daily_limit = None
        self.quota_refill_at = ""
        self._refresh_quota_label(message)
        self._refresh_connection_indicator()

    @objc.python_method
    def _refresh_quota_label(self, error: str | None = None) -> None:
        if not hasattr(self, "quota_button"):
            return

        try:
            model_config = get_active_model_config()
        except Exception:
            self._set_button_title(self.quota_button, "--/--", primary=False)
            return
        show_quota = model_config.is_cloud
        self.quota_button.setHidden_(not show_quota)
        if not show_quota:
            return

        if self._quota_exhausted():
            text = f"0/{self.quota_daily_limit or 20}"
            tooltip = f"Quota is empty. Click Get extra for a free refill. Machine code: {self.machine_code}."
        elif self.quota_remaining is not None and self.quota_daily_limit is not None:
            text = f"{self.quota_remaining}/{self.quota_daily_limit}"
            tooltip = f"Cloud quota: {self.quota_remaining} of {self.quota_daily_limit}. Refills 1 every 5 minutes."
        elif self.quota_refreshing:
            text = "..."
            tooltip = "Loading cloud quota..."
        else:
            text = "--/--"
            tooltip = f"Cloud quota unavailable: {error}" if error else "Cloud quota unavailable"

        self._set_button_title(self.quota_button, text, primary=False)
        self.quota_button.setToolTip_(tooltip)
        if hasattr(self, "settings_quota_label"):
            self.settings_quota_label.setStringValue_(self._quota_text())
        if hasattr(self, "optimize_button"):
            self.optimize_button.setToolTip_(self._status_tooltip(getattr(self, "status_message", "")))

    @objc.python_method
    def _quota_exhausted(self) -> bool:
        return (
            self.quota_remaining is not None
            and self.quota_remaining <= 0
            and bool(self.machine_code)
        )

    @objc.python_method
    def _status_tooltip(self, message: str) -> str:
        cloud = "Connected" if self.cloud_available else "Offline or checking"
        permission = "Authorized" if self._has_required_permissions() else "Needs permission"
        parts = [message, cloud, permission, f"Hotkey: {self.optimize_hotkey.raw}"]
        if self._quota_exhausted():
            parts.append(f"Quota empty. Machine code: {self.machine_code}")
            parts.append("Click Get extra for a free refill")
        if self.quota_remaining is not None and self.quota_daily_limit is not None:
            parts.append(f"Quota: {self.quota_remaining}/{self.quota_daily_limit}")
        return " | ".join(part for part in parts if part)

    @objc.python_method
    def _has_required_permissions(self) -> bool:
        if not AXIsProcessTrusted():
            return False
        if self.needs_input_monitoring:
            return False
        return True

    @objc.python_method
    def _activate_target_app(self) -> None:
        if self.target_app is None:
            raise RuntimeError("No target app yet. Click the text field you want to rewrite first.")
        if self.target_app.isTerminated():
            raise RuntimeError("The target app closed. Click the target text field again.")

        self.target_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.25)

    @objc.python_method
    def _ready_status(self) -> str:
        target = f"Target: {self.target_name}" if self.target_name else "Click a target text field first"
        model_config = get_active_model_config()
        if model_config.is_cloud:
            return f"Ready: KnowSayin Cloud | {target}"
        if model_config.llm_enabled:
            return f"Ready: {model_config.provider_name} / {model_config.model} | {target}"
        return f"Ready: no model configured; using local cleanup | {target}"

    @objc.python_method
    def _build_window(self) -> NSPanel:
        width = 264
        height = 42
        screen = NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + screen.size.width - width - 24
        y = screen.origin.y + screen.size.height - height - 54

        style = _appkit_constant("NSWindowStyleMaskBorderless", "NSBorderlessWindowMask")
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setFloatingPanel_(True)
        window.setLevel_(_appkit_constant("NSFloatingWindowLevel", "NSFloatingWindowLevel"))
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHidesOnDeactivate_(False)
        window.setMovableByWindowBackground_(True)
        window.setHasShadow_(True)
        window.setDelegate_(self)

        behavior = _appkit_constant(
            "NSWindowCollectionBehaviorCanJoinAllSpaces",
            "NSWindowCollectionBehaviorCanJoinAllSpaces",
        ) | _appkit_constant(
            "NSWindowCollectionBehaviorFullScreenAuxiliary",
            "NSWindowCollectionBehaviorFullScreenAuxiliary",
        )
        window.setCollectionBehavior_(behavior)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.clearColor().CGColor())

        self.chrome = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        self.chrome.setMaterial_(
            _appkit_constant("NSVisualEffectMaterialHUDWindow", "NSVisualEffectMaterialPopover"),
        )
        self.chrome.setBlendingMode_(
            _appkit_constant(
                "NSVisualEffectBlendingModeBehindWindow",
                "NSVisualEffectBlendingModeBehindWindow",
            ),
        )
        self.chrome.setState_(
            _appkit_constant("NSVisualEffectStateActive", "NSVisualEffectStateActive"),
        )
        self.chrome.setWantsLayer_(True)
        self.chrome.layer().setCornerRadius_(21)
        self.chrome.layer().setMasksToBounds_(True)
        content.addSubview_(self.chrome)

        self.quota_button = self._button("--/--", "quotaButton:", 8, 6, 62)
        self._style_floating_button(self.quota_button, primary=False)
        self.quota_button.setToolTip_("Cloud quota")
        self.chrome.addSubview_(self.quota_button)

        self.hide_button = self._button("-", "hideFloatingWindow:", 76, 6, 28)
        self._style_floating_button(self.hide_button, primary=False)
        self.hide_button.setToolTip_("Hide floating window")
        self.chrome.addSubview_(self.hide_button)

        self.undo_button = self._button("Undo", "undo:", 110, 6, 42)
        self._style_floating_button(self.undo_button, primary=False)
        self.undo_button.setToolTip_(f"Undo: {self.undo_hotkey.raw}")
        self.undo_button.setEnabled_(False)
        self.chrome.addSubview_(self.undo_button)

        self.optimize_button = self._button("Optimize", "optimize:", 158, 6, 98)
        self._style_floating_button(self.optimize_button, primary=True)
        self.optimize_button.setToolTip_(self._status_tooltip(self._ready_status()))
        self.chrome.addSubview_(self.optimize_button)

        self.buttons = [
            self.quota_button,
            self.hide_button,
            self.optimize_button,
            self.undo_button,
        ]
        self.status_message = self._ready_status()
        self._refresh_quota_label()
        self._refresh_connection_indicator()

        return window

    @objc.python_method
    def _button(self, title: str, action: str, x: int, y: int, width: int) -> NSButton:
        button = NSButton.buttonWithTitle_target_action_(title, self, action)
        button.setFrame_(NSMakeRect(x, y, width, 30))
        button.setBezelStyle_(NSBezelStyleRounded)
        return button

    @objc.python_method
    def _style_floating_button(self, button: NSButton, primary: bool) -> None:
        button.setBordered_(False)
        button.setWantsLayer_(True)
        button.layer().setCornerRadius_(15)
        is_hide = hasattr(self, "hide_button") and button is self.hide_button
        if primary:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.93, 0.96, 1.0, 0.22)
        elif is_hide:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.72, 0.24, 0.86)
        else:
            color = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.12)
        button.layer().setBackgroundColor_(color.CGColor())
        self._set_button_title(button, str(button.title()), primary=primary)

    @objc.python_method
    def _set_button_title(self, button: NSButton, title: str, primary: bool) -> None:
        import AppKit

        is_quota = hasattr(self, "quota_button") and button is self.quota_button
        is_hide = hasattr(self, "hide_button") and button is self.hide_button
        if is_quota and hasattr(NSFont, "monospacedDigitSystemFontOfSize_weight_"):
            font = NSFont.monospacedDigitSystemFontOfSize_weight_(10, 0.38)
        elif is_quota:
            font = NSFont.boldSystemFontOfSize_(10)
        elif is_hide:
            font = NSFont.boldSystemFontOfSize_(15)
        elif primary:
            font = NSFont.systemFontOfSize_weight_(13, 0.38)
        else:
            font = NSFont.boldSystemFontOfSize_(13)
        if is_hide:
            color = NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.7)
        elif primary:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.94, 0.98, 1.0, 1.0)
        else:
            color = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.78)
        attrs = {
            AppKit.NSFontAttributeName: font,
            AppKit.NSForegroundColorAttributeName: color,
        }
        button.setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(title, attrs),
        )

    @objc.python_method
    def _refresh_connection_indicator(self) -> None:
        if not hasattr(self, "optimize_button"):
            return
        if self._quota_exhausted():
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.16, 0.43, 0.86, 0.96)
        elif self._has_required_permissions() and self.cloud_available:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.14, 0.64, 0.36, 0.96)
        else:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.82, 0.18, 0.18, 0.96)
        self.optimize_button.layer().setBackgroundColor_(color.CGColor())

    @objc.python_method
    def _show_settings_window(self) -> None:
        if hasattr(self, "settings_window") and self.settings_window:
            self.settings_window.makeKeyAndOrderFront_(self)
            self._load_settings_into_fields()
            return

        width = 660
        height = 490
        screen = NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + screen.size.width - width - 48
        y = screen.origin.y + screen.size.height - height - 70

        style = (
            _appkit_constant("NSWindowStyleMaskTitled", "NSTitledWindowMask")
            | _appkit_constant("NSWindowStyleMaskClosable", "NSClosableWindowMask")
            | _appkit_constant("NSWindowStyleMaskUtilityWindow", "NSUtilityWindowMask")
        )
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_(_localized("KnowSayin Settings", "KnowSayin 设置"))
        window.setFloatingPanel_(True)
        window.setHidesOnDeactivate_(False)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

        self._label(content, _localized("Quota refill", "额度回血"), 20, 432, 100, 18)
        self.settings_quota_label = self._value_label(content, self._quota_text(), 132, 432, 238, 18)

        self._build_credit_snack_card(content)

        # Optimize Row
        self._label(content, "Optimize", 20, 386, 100, 18)
        self.optimize_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 380, 238, 26),
        )
        self.optimize_hotkey_field.setPlaceholderString_(_localized("Press shortcut", "按下快捷键"))
        self.optimize_hotkey_field.setDelegate_(self)
        content.addSubview_(self.optimize_hotkey_field)
        self._label(content, _localized("Click field, then press keys", "点输入框后直接按快捷键"), 132, 360, 238, 18)

        # Undo Row
        self._label(content, "Undo", 20, 332, 100, 18)
        self.undo_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 326, 238, 26),
        )
        self.undo_hotkey_field.setPlaceholderString_(_localized("Press shortcut", "按下快捷键"))
        self.undo_hotkey_field.setDelegate_(self)
        content.addSubview_(self.undo_hotkey_field)
        self._label(content, _localized("Tap Option three times for option*3", "连续按三次 Option 可设为 option*3"), 132, 306, 250, 18)

        # Language 1 Row
        self._label(content, _localized("Language 1", "语言 1"), 20, 266, 100, 18)
        self.lang1_pop_up = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 260, 110, 26),
            False,
        )
        for code, label in SUPPORTED_LANGUAGES:
            self.lang1_pop_up.addItemWithTitle_(label)
        content.addSubview_(self.lang1_pop_up)

        self.lang1_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(252, 260, 118, 26),
        )
        self.lang1_hotkey_field.setPlaceholderString_(_localized("Press shortcut", "按下快捷键"))
        self.lang1_hotkey_field.setDelegate_(self)
        content.addSubview_(self.lang1_hotkey_field)
        self._label(content, _localized("e.g. Option + 1 for Chinese", "例如 Option + 1 整理为中文"), 132, 240, 238, 18)

        # Language 2 Row
        self._label(content, _localized("Language 2", "语言 2"), 20, 200, 100, 18)
        self.lang2_pop_up = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 194, 110, 26),
            False,
        )
        for code, label in SUPPORTED_LANGUAGES:
            self.lang2_pop_up.addItemWithTitle_(label)
        content.addSubview_(self.lang2_pop_up)

        self.lang2_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(252, 194, 118, 26),
        )
        self.lang2_hotkey_field.setPlaceholderString_(_localized("Press shortcut", "按下快捷键"))
        self.lang2_hotkey_field.setDelegate_(self)
        content.addSubview_(self.lang2_hotkey_field)
        self._label(content, _localized("e.g. Option + 2 for English", "例如 Option + 2 整理为英文"), 132, 174, 238, 18)

        # Share Row
        self._label(content, _localized("Share", "分享"), 20, 126, 100, 18)
        share_button = self._button(_localized("Share KnowSayin", "分享 KnowSayin"), "openShare:", 132, 120, 170)
        content.addSubview_(share_button)
        self._label(content, _localized("Copy install messages for friends", "复制给朋友的安装分享内容"), 132, 100, 250, 18)

        # Action Buttons
        self.save_settings_button = self._button(_localized("Save", "保存"), "saveSettings:", 132, 48, 90)
        cancel_button = self._button(_localized("Cancel", "取消"), "cancelSettings:", 232, 48, 90)
        content.addSubview_(self.save_settings_button)
        content.addSubview_(cancel_button)

        self.settings_status = NSTextField.labelWithString_(
            _localized("Click a shortcut field, then press the shortcut.", "点快捷键输入框，然后直接按你要设置的快捷键。"),
        )
        self.settings_status.setFrame_(NSMakeRect(20, 8, 620, 26))
        self.settings_status.setFont_(NSFont.systemFontOfSize_(12))
        self.settings_status.setTextColor_(NSColor.secondaryLabelColor())
        self.settings_status.setLineBreakMode_(0)
        content.addSubview_(self.settings_status)

        self.settings_window = window
        self._install_settings_hotkey_monitor()
        self._load_settings_into_fields()
        window.makeKeyAndOrderFront_(self)

    @objc.python_method
    def _show_share_window(self) -> None:
        if hasattr(self, "share_window") and self.share_window:
            self.share_window.makeKeyAndOrderFront_(self)
            if hasattr(self, "share_status_label"):
                self.share_status_label.setStringValue_(_localized("Choose what to copy.", "选择要复制的分享内容。"))
            return

        width = 540
        height = 270
        screen = NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + screen.size.width - width - 64
        y = screen.origin.y + screen.size.height - height - 94

        style = (
            _appkit_constant("NSWindowStyleMaskTitled", "NSTitledWindowMask")
            | _appkit_constant("NSWindowStyleMaskClosable", "NSClosableWindowMask")
            | _appkit_constant("NSWindowStyleMaskUtilityWindow", "NSUtilityWindowMask")
        )
        window = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, width, height),
            style,
            NSBackingStoreBuffered,
            False,
        )
        window.setTitle_(_localized("Share KnowSayin", "分享 KnowSayin"))
        window.setFloatingPanel_(True)
        window.setHidesOnDeactivate_(False)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

        intro = _localized(
            "Copy a short message for the person you want to share with.",
            "给朋友复制一段简短的分享内容。",
        )
        self._value_label(content, intro, 20, 218, 500, 18)

        self._share_row(
            content,
            166,
            _localized("Website link", "网站链接"),
            _localized("Best for most friends.", "最适合普通朋友。"),
            _localized("Copy Website", "复制网站链接"),
            "copyShareWebsite:",
        )
        self._share_row(
            content,
            116,
            _localized("Terminal command", "Terminal 命令"),
            _localized("For Mac users comfortable with Terminal.", "适合愿意打开 Terminal 的 Mac 用户。"),
            _localized("Copy Terminal", "复制 Terminal"),
            "copyShareTerminal:",
        )
        self._share_row(
            content,
            66,
            _localized("AI Agent prompt", "AI Agent 提示词"),
            _localized("For Codex, Claude Code, Cursor Agent, or similar tools.", "适合 Codex、Claude Code、Cursor Agent 等工具。"),
            _localized("Copy Prompt", "复制提示词"),
            "copyShareAgent:",
        )

        close_button = self._button(_localized("Close", "关闭"), "closeShare:", 410, 18, 90)
        content.addSubview_(close_button)

        self.share_status_label = NSTextField.labelWithString_(_localized("Choose what to copy.", "选择要复制的分享内容。"))
        self.share_status_label.setFrame_(NSMakeRect(20, 18, 370, 26))
        self.share_status_label.setFont_(NSFont.systemFontOfSize_(12))
        self.share_status_label.setTextColor_(NSColor.secondaryLabelColor())
        self.share_status_label.setLineBreakMode_(0)
        content.addSubview_(self.share_status_label)

        self.share_window = window
        window.makeKeyAndOrderFront_(self)

    @objc.python_method
    def _share_row(
        self,
        content,
        y: int,
        title: str,
        detail: str,
        button_title: str,
        action: str,
    ) -> None:
        self._value_label(content, title, 20, y + 17, 170, 18)
        self._label(content, detail, 20, y - 2, 330, 18)
        button = self._button(button_title, action, 370, y + 4, 130)
        content.addSubview_(button)

    @objc.python_method
    def _build_credit_snack_card(self, content) -> None:
        card = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(392, 310, 248, 144))
        card.setMaterial_(_appkit_constant("NSVisualEffectMaterialSidebar", "NSVisualEffectMaterialPopover"))
        card.setBlendingMode_(_appkit_constant("NSVisualEffectBlendingModeWithinWindow", "NSVisualEffectBlendingModeBehindWindow"))
        card.setState_(_appkit_constant("NSVisualEffectStateActive", "NSVisualEffectStateActive"))
        card.setWantsLayer_(True)
        card.layer().setCornerRadius_(8)
        card.layer().setBorderWidth_(1)
        card.layer().setBorderColor_(NSColor.separatorColor().CGColor())
        content.addSubview_(card)

        self.credit_snack_title = self._value_label(
            content,
            _localized("Quick credit", "夸夸补给站"),
            406,
            424,
            220,
            18,
        )
        self.credit_snack_question_label = self._value_label(content, "", 406, 388, 220, 32)
        self.credit_snack_question_label.setLineBreakMode_(0)
        self.credit_snack_first_button = self._button("", "answerCreditSnackFirst:", 406, 354, 102)
        self.credit_snack_second_button = self._button("", "answerCreditSnackSecond:", 520, 354, 102)
        content.addSubview_(self.credit_snack_first_button)
        content.addSubview_(self.credit_snack_second_button)
        self.credit_answer_buttons = [self.credit_snack_first_button, self.credit_snack_second_button]

        self.credit_snack_status = NSTextField.labelWithString_(
            _localized(
                f"Answer for {CREDIT_GAME_DELTA} credits.",
                f"答一题赢 {CREDIT_GAME_DELTA} 个 credits。",
            ),
        )
        self.credit_snack_status.setFrame_(NSMakeRect(406, 336, 220, 14))
        self.credit_snack_status.setFont_(NSFont.systemFontOfSize_(11))
        self.credit_snack_status.setTextColor_(NSColor.secondaryLabelColor())
        self.credit_snack_status.setLineBreakMode_(0)
        content.addSubview_(self.credit_snack_status)
        self.credit_snack_countdown = NSTextField.labelWithString_("")
        self.credit_snack_countdown.setFrame_(NSMakeRect(406, 318, 220, 14))
        if hasattr(NSFont, "monospacedDigitSystemFontOfSize_weight_"):
            countdown_font = NSFont.monospacedDigitSystemFontOfSize_weight_(11, 0.34)
        else:
            countdown_font = NSFont.systemFontOfSize_(11)
        self.credit_snack_countdown.setFont_(countdown_font)
        self.credit_snack_countdown.setTextColor_(NSColor.secondaryLabelColor())
        self.credit_snack_countdown.setLineBreakMode_(0)
        content.addSubview_(self.credit_snack_countdown)
        self._choose_credit_snack_question()
        self._refresh_credit_snack_countdown()

    @objc.python_method
    def _choose_credit_snack_question(self) -> None:
        self.credit_question = random_credit_question()
        self._refresh_credit_snack_labels()

    @objc.python_method
    def _refresh_credit_snack_labels(self) -> None:
        if not hasattr(self, "credit_snack_question_label"):
            return
        question = self.credit_question or random_credit_question()
        self.credit_question = question
        self.credit_snack_question_label.setStringValue_(_credit_question_text(question))
        self.credit_snack_first_button.setTitle_(_credit_option_text(question.options[0]))
        self.credit_snack_second_button.setTitle_(_credit_option_text(question.options[1]))
        self._set_credit_snack_enabled(not self.credit_game_busy)

    @objc.python_method
    def _set_credit_snack_enabled(self, enabled: bool) -> None:
        if not hasattr(self, "credit_answer_buttons"):
            return
        for button in self.credit_answer_buttons:
            button.setEnabled_(enabled and not self._credit_snack_is_cooling_down())

    @objc.python_method
    def _credit_snack_is_cooling_down(self) -> bool:
        return _seconds_until(self.credit_game_next_play_at) > 0

    @objc.python_method
    def _refresh_credit_snack_countdown(self) -> None:
        if not hasattr(self, "credit_snack_countdown"):
            return

        next_play_seconds = _seconds_until(self.credit_game_next_play_at)
        reset_seconds = _seconds_until(self.credit_game_reset_at)
        if next_play_seconds > 0:
            self.credit_snack_countdown.setStringValue_(
                _localized(
                    f"Refill in {_format_countdown(next_play_seconds)}",
                    f"{_format_countdown(next_play_seconds)} 后回血",
                ),
            )
            self._set_credit_snack_enabled(False)
            return

        if self.credit_game_next_play_at and next_play_seconds <= 0:
            self.credit_game_next_play_at = ""
            self.credit_game_remaining_plays = self.credit_game_limit
            if not self.credit_game_busy:
                self._choose_credit_snack_question()

        if reset_seconds > 0 and self.credit_game_remaining_plays is not None:
            self.credit_snack_countdown.setStringValue_(
                _localized(
                    f"{self.credit_game_remaining_plays}/{self.credit_game_limit} left · reset {_format_countdown(reset_seconds)}",
                    f"还可答 {self.credit_game_remaining_plays}/{self.credit_game_limit} · {_format_countdown(reset_seconds)} 重置",
                ),
            )
            self._set_credit_snack_enabled(not self.credit_game_busy)
            return

        if self.credit_game_reset_at and reset_seconds <= 0:
            self.credit_game_reset_at = ""
            self.credit_game_remaining_plays = self.credit_game_limit

        self.credit_snack_countdown.setStringValue_(
            _localized(
                f"{self.credit_game_limit} questions/min · 1 min refill",
                f"每分钟 {self.credit_game_limit} 题 · 1 分钟回血",
            ),
        )
        self._set_credit_snack_enabled(not self.credit_game_busy)

    @objc.python_method
    def _submit_credit_snack_answer(self, option_index: int) -> None:
        if self.credit_game_busy:
            return
        question = self.credit_question
        if question is None:
            self._choose_credit_snack_question()
            question = self.credit_question
        if question is None or option_index < 0 or option_index >= len(question.options):
            return
        try:
            model_config = get_active_model_config()
        except Exception as exc:
            self.credit_snack_status.setStringValue_(_localized(f"Cloud unavailable: {exc}", "云端暂不可用。"))
            return
        if not model_config.is_cloud:
            self.credit_snack_status.setStringValue_(_localized("Quick credit needs KnowSayin Cloud.", "夸夸补给需要 KnowSayin Cloud。"))
            return

        answer = question.options[option_index].value
        self.credit_game_busy = True
        self._set_credit_snack_enabled(False)
        self.credit_snack_status.setStringValue_(_localized("Checking...", "正在判题..."))
        threading.Thread(
            target=self._credit_snack_worker,
            args=(model_config.base_url, question.id, answer),
            daemon=True,
        ).start()

    @objc.python_method
    def _credit_snack_worker(self, base_url: str, question_id: str, answer: str) -> None:
        try:
            from .cloud_client import submit_credit_game

            result = submit_credit_game(question_id, answer, base_url)
            AppHelper.callAfter(self._finish_credit_snack, result)
        except Exception as exc:
            payload = getattr(exc, "payload", None)
            AppHelper.callAfter(self._fail_credit_snack, str(exc), payload if isinstance(payload, dict) else {})

    @objc.python_method
    def _finish_credit_snack(self, result: dict) -> None:
        self.credit_game_busy = False
        self._apply_quota_payload(result)
        self._choose_credit_snack_question()
        correct = bool(result.get("correct"))
        remaining = _int_or_none(result.get("remaining"))
        quota_limit = _int_or_none(result.get("quotaLimit") or result.get("dailyLimit"))
        quota_text = f" {remaining}/{quota_limit}" if remaining is not None and quota_limit is not None else ""
        if correct:
            message = _localized(
                f"Correct. +{CREDIT_GAME_DELTA} credits.{quota_text}",
                f"答对了，+{CREDIT_GAME_DELTA} credits。{quota_text}",
            )
        else:
            message = _localized(
                f"Nope. -{CREDIT_GAME_DELTA} credits.{quota_text}",
                f"答错了，-{CREDIT_GAME_DELTA} credits。{quota_text}",
            )
        self.credit_snack_status.setStringValue_(message)
        self._refresh_credit_snack_countdown()
        self._set_credit_snack_enabled(True)

    @objc.python_method
    def _fail_credit_snack(self, message: str, payload: dict) -> None:
        self.credit_game_busy = False
        self._apply_quota_payload(payload)
        remaining_seconds = _seconds_until(str(payload.get("nextPlayAt") or ""))
        if str(payload.get("error") or "") == "CREDIT_GAME_COOLDOWN" and remaining_seconds > 0:
            text = _localized(
                f"Refill in {_format_countdown(remaining_seconds)}.",
                f"{_format_countdown(remaining_seconds)} 后回血。",
            )
        else:
            text = _localized(f"Quick credit failed: {message}", f"夸夸补给失败：{message}")
        self.credit_snack_status.setStringValue_(text)
        self._refresh_credit_snack_countdown()
        self._set_credit_snack_enabled(True)

    @objc.python_method
    def _apply_quota_payload(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        remaining = _int_or_none(payload.get("remaining"))
        quota_limit = _int_or_none(payload.get("quotaLimit") or payload.get("dailyLimit"))
        if remaining is not None:
            self.quota_remaining = remaining
        if quota_limit is not None:
            self.quota_daily_limit = quota_limit
        self.quota_refill_at = str(payload.get("refillAt") or payload.get("resetAt") or self.quota_refill_at or "")
        self.credit_game_next_play_at = str(payload.get("nextPlayAt") or self.credit_game_next_play_at or "")
        self.credit_game_reset_at = str(payload.get("creditGameResetAt") or self.credit_game_reset_at or "")
        remaining_plays = _int_or_none(payload.get("creditGameRemainingPlays"))
        if remaining_plays is not None:
            self.credit_game_remaining_plays = remaining_plays
        limit = _int_or_none(payload.get("creditGameLimit"))
        if limit is not None:
            self.credit_game_limit = max(limit, 1)
        window_seconds = _int_or_none(payload.get("creditGameWindowSeconds") or payload.get("creditGameCooldownSeconds"))
        if window_seconds is not None:
            self.credit_game_window_seconds = max(window_seconds, 0)
        self.machine_code = str(payload.get("deviceCode") or self.machine_code or "").strip().upper()
        self.extra_url = str(payload.get("extraUrl") or self.extra_url or "https://knowsayin.com").strip()
        self.cloud_plan = str(payload.get("plan") or self.cloud_plan or "free").strip().lower()
        if remaining is not None and quota_limit is not None:
            self.cloud_available = True
        self._refresh_quota_label()
        self._reset_optimize_title()
        self._refresh_connection_indicator()
        self._refresh_credit_snack_countdown()

    @objc.python_method
    def _copy_share_text(self, kind: str) -> None:
        text = _share_text(kind)
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)
        label = {
            "website": _localized("website link", "网站链接"),
            "terminal": _localized("Terminal command", "Terminal 命令"),
            "agent": _localized("AI Agent prompt", "AI Agent 提示词"),
        }.get(kind, _localized("share text", "分享内容"))
        message = _localized(f"Copied {label}.", f"已复制{label}。")
        if hasattr(self, "share_status_label"):
            self.share_status_label.setStringValue_(message)
        if hasattr(self, "settings_status"):
            self.settings_status.setStringValue_(message)

    @objc.python_method
    def _load_settings_into_fields(self) -> None:
        data = load_model_settings()
        self.optimize_hotkey_field.setStringValue_(data["optimize_hotkey"] or DEFAULT_OPTIMIZE_HOTKEY)
        self.undo_hotkey_field.setStringValue_(data["undo_hotkey"] or DEFAULT_UNDO_HOTKEY)
        
        # Load language hotkeys
        self.lang1_hotkey_field.setStringValue_(data["lang1_hotkey"] or DEFAULT_LANG1_HOTKEY)
        self.lang2_hotkey_field.setStringValue_(data["lang2_hotkey"] or DEFAULT_LANG2_HOTKEY)

        # Select corresponding dropdown items
        loaded_lang1 = data.get("lang1_code") or DEFAULT_LANG1_CODE
        loaded_lang2 = data.get("lang2_code") or DEFAULT_LANG2_CODE

        lang1_idx = 0
        for idx, (code, label) in enumerate(SUPPORTED_LANGUAGES):
            if code == loaded_lang1:
                lang1_idx = idx
                break
        self.lang1_pop_up.selectItemAtIndex_(lang1_idx)

        lang2_idx = 0
        for idx, (code, label) in enumerate(SUPPORTED_LANGUAGES):
            if code == loaded_lang2:
                lang2_idx = idx
                break
        self.lang2_pop_up.selectItemAtIndex_(lang2_idx)

        self.settings_status.setStringValue_(
            _localized("Click a shortcut field, then press the shortcut.", "点快捷键输入框，然后直接按你要设置的快捷键。"),
        )
        if hasattr(self, "settings_quota_label"):
            self.settings_quota_label.setStringValue_(self._quota_text())
        if hasattr(self, "credit_snack_question_label") and not self.credit_game_busy:
            self._choose_credit_snack_question()
            self.credit_snack_status.setStringValue_(
                _localized(
                    f"Answer for {CREDIT_GAME_DELTA} credits.",
                    f"答一题赢 {CREDIT_GAME_DELTA} 个 credits。",
                ),
            )
            self._refresh_credit_snack_countdown()
        self._refresh_cloud_quota_async()

    @objc.python_method
    def _validate_settings_fields(self, success_message: str | None = None) -> bool:
        optimize_hotkey = str(self.optimize_hotkey_field.stringValue()).strip() or DEFAULT_OPTIMIZE_HOTKEY
        undo_hotkey = str(self.undo_hotkey_field.stringValue()).strip() or DEFAULT_UNDO_HOTKEY
        lang1_hotkey = str(self.lang1_hotkey_field.stringValue()).strip() or DEFAULT_LANG1_HOTKEY
        lang2_hotkey = str(self.lang2_hotkey_field.stringValue()).strip() or DEFAULT_LANG2_HOTKEY

        try:
            optimize_spec = _parse_hotkey(optimize_hotkey)
            undo_spec = _parse_hotkey(undo_hotkey)
            lang1_spec = _parse_hotkey(lang1_hotkey)
            lang2_spec = _parse_hotkey(lang2_hotkey)
        except ValueError as exc:
            self.settings_status.setStringValue_(
                _localized(f"Shortcut error: {exc}", f"快捷键错误：{exc}"),
            )
            return False

        # Check duplicate hotkeys
        specs = [optimize_spec, undo_spec, lang1_spec, lang2_spec]
        labels = [
            _localized("Optimize", "Optimize"),
            _localized("Undo", "Undo"),
            _localized("Language 1", "语言 1"),
            _localized("Language 2", "语言 2"),
        ]
        for i in range(len(specs)):
            for j in range(i + 1, len(specs)):
                if _same_hotkey(specs[i], specs[j]):
                    self.settings_status.setStringValue_(
                        _localized(
                            f"{labels[i]} and {labels[j]} cannot use the same shortcut.",
                            f"{labels[i]} 和 {labels[j]} 不能使用同一个快捷键。",
                        )
                    )
                    return False

        if success_message:
            self.settings_status.setStringValue_(success_message)
        return True

    @objc.python_method
    def _label(self, content, text: str, x: int, y: int, width: int, height: int) -> None:
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(12))
        label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(label)

    @objc.python_method
    def _value_label(self, content, text: str, x: int, y: int, width: int, height: int):
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(12))
        label.setTextColor_(NSColor.labelColor())
        content.addSubview_(label)
        return label

    @objc.python_method
    def _quota_text(self) -> str:
        next_refill = _format_refill_time(self.quota_refill_at)
        if self._quota_exhausted():
            if next_refill:
                return _localized(
                    f"0/{self.quota_daily_limit or 20} available; next refill {next_refill}",
                    f"0/{self.quota_daily_limit or 20} 可用；下次回血 {next_refill}",
                )
            return _localized(
                f"0/{self.quota_daily_limit or 20} available; click Get extra for a free refill",
                f"0/{self.quota_daily_limit or 20} 可用；点击 Get extra 免费回血",
            )
        if self.quota_remaining is not None and self.quota_daily_limit is not None:
            if next_refill:
                return _localized(
                    f"{self.quota_remaining}/{self.quota_daily_limit} available; next refill {next_refill}",
                    f"{self.quota_remaining}/{self.quota_daily_limit} 可用；下次回血 {next_refill}",
                )
            if self.quota_remaining >= self.quota_daily_limit:
                return _localized(
                    f"{self.quota_remaining}/{self.quota_daily_limit} available; full",
                    f"{self.quota_remaining}/{self.quota_daily_limit} 可用；已满",
                )
            return _localized(
                f"{self.quota_remaining}/{self.quota_daily_limit} available; refills 1 every 5 minutes",
                f"{self.quota_remaining}/{self.quota_daily_limit} 可用；每 5 分钟回 1 次",
            )
        if self.quota_refreshing:
            return _localized("Loading...", "正在加载...")
        return _localized("Unavailable", "暂不可用")


MODIFIER_ORDER = ("control", "option", "shift", "command")


KEY_CODES: dict[str, int] = {
    "space": 49,
    "return": 36,
    "enter": 36,
    "tab": 48,
    "escape": 53,
    "esc": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "delete": 51,
    "backspace": 51,
    "`": 50,
    "[": 33,
    "]": 30,
    "\\": 42,
    ";": 41,
    "'": 39,
    ",": 43,
    ".": 47,
    "/": 44,
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "=": 24,
    "9": 25,
    "7": 26,
    "-": 27,
    "8": 28,
    "0": 29,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
}

KEY_NAMES_BY_CODE: dict[int, str] = {}
for _key_name, _key_code in KEY_CODES.items():
    KEY_NAMES_BY_CODE.setdefault(_key_code, _key_name)

MODIFIER_ALIASES = {
    "option": "option",
    "opt": "option",
    "alt": "option",
    "alternate": "option",
    "⌥": "option",
    "shift": "shift",
    "⇧": "shift",
    "command": "command",
    "cmd": "command",
    "⌘": "command",
    "control": "control",
    "ctrl": "control",
    "ctl": "control",
    "⌃": "control",
}


def _parse_hotkey(value: str) -> HotkeySpec:
    raw = value.strip()
    normalized = _normalize_hotkey_text(raw)
    if not normalized:
        raise ValueError("Hotkey cannot be empty.")

    tap = _parse_tap_hotkey(raw, normalized)
    if tap:
        return tap

    parts = [part for part in normalized.split("+") if part]
    if not parts:
        raise ValueError(f"Could not understand `{raw}`.")

    modifiers: list[str] = []
    key: str | None = None
    for part in parts:
        modifier = MODIFIER_ALIASES.get(part)
        if modifier:
            modifiers.append(modifier)
            continue
        key = part

    if not modifiers:
        raise ValueError("Use at least one modifier, such as option or shift.")

    modifier_set = frozenset(modifiers)
    if key is None:
        return HotkeySpec(raw=raw, kind="modifier", modifiers=modifier_set)

    keycode = KEY_CODES.get(key)
    if keycode is None:
        raise ValueError(f"The key `{key}` is not supported yet.")
    return HotkeySpec(raw=raw, kind="key", modifiers=modifier_set, keycode=keycode)


def _same_hotkey(first: HotkeySpec, second: HotkeySpec) -> bool:
    return (
        first.kind == second.kind
        and first.modifiers == second.modifiers
        and first.keycode == second.keycode
        and first.tap_modifier == second.tap_modifier
        and first.tap_count == second.tap_count
    )


def _parse_tap_hotkey(raw: str, normalized: str) -> HotkeySpec | None:
    compact = normalized.replace("+", "").replace(" ", "")
    compact = compact.replace("三下", "x3").replace("三次", "x3")
    compact = compact.replace("triple", "x3").replace("times", "x")
    for alias, modifier in MODIFIER_ALIASES.items():
        if compact in {f"{alias}x3", f"{alias}*3", f"3x{alias}", f"x3{alias}"}:
            return HotkeySpec(
                raw=raw,
                kind="tap",
                modifiers=frozenset(),
                tap_modifier=modifier,
                tap_count=3,
            )
    return None


def _normalize_hotkey_text(value: str) -> str:
    text = value.strip().lower()
    replacements = {
        "＋": "+",
        "加": "+",
        " ": "",
        "\t": "",
        "×": "x",
        "＊": "*",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _preferred_language() -> str:
    try:
        languages = list(NSLocale.preferredLanguages())
    except Exception:
        languages = []
    first = str(languages[0] if languages else "").lower()
    return "zh" if first.startswith("zh") else "en"


def _localized(en: str, zh: str) -> str:
    return zh if _preferred_language() == "zh" else en


def _share_text(kind: str) -> str:
    lang = _preferred_language()
    if kind == "terminal":
        if lang == "zh":
            return "\n".join(
                [
                    "在 Mac 的 Terminal 里运行这一行安装 KnowSayin：",
                    "",
                    SHARE_INSTALL_COMMAND,
                    "",
                    "不需要 GitHub 账号。",
                ],
            )
        return "\n".join(
            [
                "Install KnowSayin on macOS from Terminal:",
                "",
                SHARE_INSTALL_COMMAND,
                "",
                "No GitHub account is required.",
            ],
        )

    if kind == "agent":
        if lang == "zh":
            return "\n".join(
                [
                    "请帮我在这台 Mac 上安装 KnowSayin。",
                    f"打开 {SHARE_DOWNLOAD_URL}，或在 Terminal 运行：",
                    SHARE_INSTALL_COMMAND,
                    f"安装到 {APP_BUNDLE_PATH} 后打开它，并帮我启用 macOS Accessibility 权限。",
                    "不要保存、打印或记录我的私密 prompts、API keys、tokens、录音或 transcripts。",
                ],
            )
        return "\n".join(
            [
                "Please install KnowSayin on this Mac.",
                f"Go to {SHARE_DOWNLOAD_URL}, or run this in Terminal:",
                SHARE_INSTALL_COMMAND,
                f"Install it to {APP_BUNDLE_PATH}, open it, and help me enable macOS Accessibility permission if needed.",
                "Do not store or print private prompts, API keys, tokens, recordings, or transcripts.",
            ],
        )

    if lang == "zh":
        return "\n".join(
            [
                f"我在用 KnowSayin：{SHARE_DOWNLOAD_URL}",
                "它可以把口述、随手写的想法整理成清楚的 AI prompt。",
            ],
        )
    return "\n".join(
        [
            f"Try KnowSayin: {SHARE_DOWNLOAD_URL}",
            "It cleans up rough dictated notes into clear AI prompts.",
        ],
    )


def _credit_question_text(question: CreditQuestion) -> str:
    return question.zh if _preferred_language() == "zh" else question.en


def _credit_option_text(option) -> str:
    return option.zh if _preferred_language() == "zh" else option.en


def _format_hotkey(modifiers: frozenset[str], key: str | None = None) -> str:
    parts = [name for name in MODIFIER_ORDER if name in modifiers]
    if key:
        parts.append(key)
    return "+".join(parts)


def _hotkey_action_label(action: str) -> str:
    if action == "optimize":
        return "Optimize"
    elif action == "undo":
        return "Undo"
    elif action == "lang1":
        return _localized("Language 1", "语言 1")
    elif action == "lang2":
        return _localized("Language 2", "语言 2")
    return action


def _format_refill_time(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if _preferred_language() == "zh":
        return parsed.astimezone().strftime("%H:%M")
    return parsed.astimezone().strftime("%-I:%M %p")


def _seconds_until(value: str) -> int:
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    now = datetime.now(parsed.tzinfo) if parsed.tzinfo else datetime.now()
    return max(int((parsed - now).total_seconds() + 0.999), 0)


def _format_countdown(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    minutes, remaining_seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{remaining_seconds:02d}"


def _active_modifier_names(flags: int, quartz: bool) -> frozenset[str]:
    return frozenset(
        name
        for name in ("option", "shift", "command", "control")
        if flags & _modifier_mask(name, quartz)
    )


def _modifier_mask(name: str, quartz: bool) -> int:
    if quartz:
        masks = {
            "option": int(Quartz.kCGEventFlagMaskAlternate),
            "shift": int(Quartz.kCGEventFlagMaskShift),
            "command": int(Quartz.kCGEventFlagMaskCommand),
            "control": int(Quartz.kCGEventFlagMaskControl),
        }
        return masks[name]

    masks = {
        "option": _appkit_constant("NSEventModifierFlagOption", "NSAlternateKeyMask"),
        "shift": _appkit_constant("NSEventModifierFlagShift", "NSShiftKeyMask"),
        "command": _appkit_constant("NSEventModifierFlagCommand", "NSCommandKeyMask"),
        "control": _appkit_constant("NSEventModifierFlagControl", "NSControlKeyMask"),
    }
    return masks[name]


def _appkit_constant(primary: str, fallback: str) -> int:
    import AppKit

    if hasattr(AppKit, primary):
        return int(getattr(AppKit, primary))
    return int(getattr(AppKit, fallback))


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _install_edit_menu(app) -> None:
    main_menu = NSMenu.alloc().initWithTitle_("")

    app_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        APP_NAME,
        None,
        "",
    )
    main_menu.addItem_(app_menu_item)
    app_menu = NSMenu.alloc().initWithTitle_(APP_NAME)
    app_menu_item.setSubmenu_(app_menu)
    app_menu.addItemWithTitle_action_keyEquivalent_("Quit KnowSayin", "terminate:", "q")

    edit_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Edit",
        None,
        "",
    )
    main_menu.addItem_(edit_menu_item)
    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    edit_menu_item.setSubmenu_(edit_menu)

    for title, action, key in (
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        ("Select All", "selectAll:", "a"),
    ):
        edit_menu.addItemWithTitle_action_keyEquivalent_(title, action, key)

    app.setMainMenu_(main_menu)


def main() -> None:
    app = NSApplication.sharedApplication()
    _install_edit_menu(app)
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = JustSayingApp.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
