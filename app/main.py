from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import objc
import Quartz
from ApplicationServices import AXIsProcessTrusted
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
    NSScreen,
    NSStatusBar,
    NSTextField,
    NSVisualEffectView,
    NSWorkspace,
    NSEvent,
)
from Foundation import NSAttributedString, NSObject, NSTimer
from PyObjCTools import AppHelper

from .model_config import (
    APP_NAME,
    APP_VERSION,
    ENV_PATH,
    DEFAULT_CLOUD_API_BASE_URL,
    DEFAULT_OPTIMIZE_HOTKEY,
    DEFAULT_UNDO_HOTKEY,
    get_active_model_config,
    load_model_settings,
    save_desktop_settings,
)
from .optimizer import optimize_prompt
from .paste import CapturedText, capture_focused_text, replace_captured_text


@dataclass(frozen=True)
class HotkeySpec:
    raw: str
    kind: str
    modifiers: frozenset[str]
    keycode: int | None = None
    tap_modifier: str | None = None
    tap_count: int = 0


class JustSayingApp(NSObject):
    def applicationDidFinishLaunching_(self, notification) -> None:
        self.busy = False
        self.own_pid = os.getpid()
        self.target_app = None
        self.target_pid = None
        self.target_name = None
        self.last_original: str | None = None
        self.last_capture: CapturedText | None = None
        self.hotkey_down: dict[str, bool] = {"optimize": False, "undo": False}
        self.previous_modifier_flags = 0
        self.tap_state: dict[str, tuple[int, float]] = {"optimize": (0, 0.0), "undo": (0, 0.0)}
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
        self.upgrade_url = "https://knowsayin.com"
        self.cloud_plan = "free"
        self.quota_refreshing = False
        self.cloud_available = False
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
        if self._quota_exhausted():
            self._copy_machine_code()
        else:
            self._show_settings_window()

    def undo_(self, sender) -> None:
        self._start_undo()

    def hideFloatingWindow_(self, sender) -> None:
        self._hide_floating_window()

    def showFloatingWindow_(self, sender) -> None:
        self._show_floating_window()

    def openPermissions_(self, sender) -> None:
        self._open_permission_settings("accessibility")

    def openSettings_(self, sender) -> None:
        self._show_settings_window()

    def checkUpdate_(self, sender) -> None:
        self._set_status("Checking for KnowSayin updates...")
        threading.Thread(target=self._check_update_worker, daemon=True).start()

    def saveSettings_(self, sender) -> None:
        optimize_hotkey = str(self.optimize_hotkey_field.stringValue()).strip()
        undo_hotkey = str(self.undo_hotkey_field.stringValue()).strip()

        try:
            optimize_spec = _parse_hotkey(optimize_hotkey or DEFAULT_OPTIMIZE_HOTKEY)
            undo_spec = _parse_hotkey(undo_hotkey or DEFAULT_UNDO_HOTKEY)
        except ValueError as exc:
            self.settings_status.setStringValue_(f"Hotkey format error: {exc}")
            return
        if _same_hotkey(optimize_spec, undo_spec):
            self.settings_status.setStringValue_("Optimize and undo cannot use the same hotkey.")
            return

        try:
            save_desktop_settings(
                optimize_hotkey or DEFAULT_OPTIMIZE_HOTKEY,
                undo_hotkey or DEFAULT_UNDO_HOTKEY,
            )
        except Exception as exc:
            self.settings_status.setStringValue_(f"Save failed: {exc}")
            return

        self._reload_hotkeys_from_settings()
        self._sync_key_event_tap()
        self._update_hotkey_tooltips()
        self.settings_status.setStringValue_(f"Saved to {ENV_PATH}.")
        self._set_status(self._ready_status())
        self._refresh_cloud_quota_async()
        self.settings_window.orderOut_(self)

    def cancelSettings_(self, sender) -> None:
        self.settings_window.orderOut_(self)

    @objc.python_method
    def _start_optimize(self) -> None:
        if self.busy:
            return
        if self._quota_exhausted():
            self._open_upgrade_page()
            return
        if not AXIsProcessTrusted():
            self._request_accessibility_permission(show_help=True)
            return

        self._set_status("Reading the focused text field...")
        self._set_busy(True)
        self._set_button_title(self.optimize_button, "...", primary=True)
        threading.Thread(target=self._optimize_worker, daemon=True).start()

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
    def _optimize_worker(self) -> None:
        try:
            time.sleep(0.12)
            self._activate_target_app()
            captured = capture_focused_text(self.target_pid)
            original = captured.text.strip()
            if not original:
                raise RuntimeError("The focused text field is empty.")

            AppHelper.callAfter(self._set_status, "Optimizing text...")
            cleaned = optimize_prompt(original, "medium").strip()
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
            title = "Website" if self._quota_exhausted() else "Optimize"
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
            self._show_permission_notice(
                "accessibility",
                "KnowSayin Needs Accessibility Permission",
                "Open macOS Accessibility settings and turn on KnowSayin. If it is already on but this message remains, remove and re-add /Applications/KnowSayin.app, then quit and reopen the app.",
            )
        return False

    @objc.python_method
    def _open_permission_settings(self, kind: str = "accessibility") -> None:
        import subprocess

        urls = []
        if kind in {"all", "accessibility"}:
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        if kind in {"all", "input"}:
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent")
        if not urls:
            urls.append("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        for url in urls:
            subprocess.run(["open", url], check=False)

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
                alert.addButtonWithTitle_("Open Accessibility Settings")
            alert.addButtonWithTitle_("OK")
            response = alert.runModal()
            if int(response) == 1000:
                self._open_permission_settings("input" if key == "input-monitoring" else "accessibility")
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
    def _open_upgrade_page(self) -> None:
        import subprocess
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        url = self.upgrade_url or "https://knowsayin.com"
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
        self.hotkey_down = {"optimize": False, "undo": False}
        self.tap_state = {"optimize": (0, 0.0), "undo": (0, 0.0)}

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
        return self.optimize_hotkey.kind == "key" or self.undo_hotkey.kind == "key"

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
            self.needs_input_monitoring = True
            self._set_status("This hotkey needs Input Monitoring permission.")
            if show_notice:
                self._show_permission_notice(
                    "input-monitoring",
                    "Hotkey Needs Input Monitoring",
                    "Open macOS Input Monitoring settings and turn on KnowSayin, or change the hotkey back to option+shift. The default option+shift hotkey does not need Input Monitoring.",
                )
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

    @objc.python_method
    def _key_hotkey_action(self, event_type, event) -> str | None:
        if event_type != Quartz.kCGEventKeyDown:
            return None
        for action, hotkey in (
            ("optimize", self.optimize_hotkey),
            ("undo", self.undo_hotkey),
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
        for action, hotkey in (
            ("optimize", self.optimize_hotkey),
            ("undo", self.undo_hotkey),
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
        self.upgrade_url = str(usage.get("upgradeUrl") or self.upgrade_url or "https://knowsayin.com").strip()
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
            text = self.machine_code
            tooltip = f"Machine code: {self.machine_code}. Click to copy."
        elif self.cloud_plan == "paid":
            text = "Active"
            tooltip = "KnowSayin is activated on this device."
        elif self.quota_remaining is not None and self.quota_daily_limit is not None:
            text = f"{self.quota_remaining}/{self.quota_daily_limit}"
            tooltip = f"Cloud quota: {self.quota_remaining} of {self.quota_daily_limit}. Refills 1 every 10 minutes."
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
            self.cloud_plan != "paid"
            and self.quota_remaining is not None
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
            parts.append("Click Website to upgrade")
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
        width = 230
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

        self.quota_button = self._button("--/--", "quotaButton:", 8, 6, 70)
        self._style_floating_button(self.quota_button, primary=False)
        self.quota_button.setToolTip_("Cloud quota")
        self.chrome.addSubview_(self.quota_button)

        self.optimize_button = self._button("Optimize", "optimize:", 84, 6, 84)
        self._style_floating_button(self.optimize_button, primary=True)
        self.optimize_button.setToolTip_(self._status_tooltip(self._ready_status()))
        self.chrome.addSubview_(self.optimize_button)

        self.undo_button = self._button("Undo", "undo:", 174, 6, 48)
        self._style_floating_button(self.undo_button, primary=False)
        self.undo_button.setToolTip_(f"Undo: {self.undo_hotkey.raw}")
        self.undo_button.setEnabled_(False)
        self.chrome.addSubview_(self.undo_button)

        self.buttons = [
            self.quota_button,
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
        if primary:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.93, 0.96, 1.0, 0.22)
        else:
            color = NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.12)
        button.layer().setBackgroundColor_(color.CGColor())
        self._set_button_title(button, str(button.title()), primary=primary)

    @objc.python_method
    def _set_button_title(self, button: NSButton, title: str, primary: bool) -> None:
        import AppKit

        is_quota = hasattr(self, "quota_button") and button is self.quota_button
        if is_quota and hasattr(NSFont, "monospacedDigitSystemFontOfSize_weight_"):
            font = NSFont.monospacedDigitSystemFontOfSize_weight_(11, 0.38)
        elif is_quota:
            font = NSFont.boldSystemFontOfSize_(11)
        elif primary:
            font = NSFont.systemFontOfSize_weight_(13, 0.38)
        else:
            font = NSFont.boldSystemFontOfSize_(13)
        color = (
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.94, 0.98, 1.0, 1.0)
            if primary
            else NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.78)
        )
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

        width = 560
        height = 330
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
        window.setTitle_("KnowSayin Settings")
        window.setFloatingPanel_(True)
        window.setHidesOnDeactivate_(False)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

        self._label(content, "Cloud Service", 20, 270, 100, 18)
        self._value_label(content, "KnowSayin Cloud", 132, 270, 388, 18)

        self._label(content, "Endpoint", 20, 236, 100, 18)
        self._value_label(content, DEFAULT_CLOUD_API_BASE_URL, 132, 236, 388, 18)

        self._label(content, "Quota", 20, 202, 100, 18)
        self.settings_quota_label = self._value_label(content, self._quota_text(), 132, 202, 388, 18)

        self._label(content, "Optimize Hotkey", 20, 160, 100, 18)
        self.optimize_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 154, 170, 26),
        )
        self.optimize_hotkey_field.setPlaceholderString_(DEFAULT_OPTIMIZE_HOTKEY)
        content.addSubview_(self.optimize_hotkey_field)
        self._label(content, "Example: option+shift / option+space", 314, 159, 220, 18)

        self._label(content, "Undo Hotkey", 20, 124, 100, 18)
        self.undo_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 118, 170, 26),
        )
        self.undo_hotkey_field.setPlaceholderString_(DEFAULT_UNDO_HOTKEY)
        content.addSubview_(self.undo_hotkey_field)
        self._label(content, "Example: option*3 / command+z", 314, 123, 220, 18)

        self.save_settings_button = self._button("Save", "saveSettings:", 132, 66, 90)
        cancel_button = self._button("Cancel", "cancelSettings:", 232, 66, 90)
        content.addSubview_(self.save_settings_button)
        content.addSubview_(cancel_button)

        self.settings_status = NSTextField.labelWithString_(f"Settings are saved to {ENV_PATH}.")
        self.settings_status.setFrame_(NSMakeRect(20, 20, 520, 32))
        self.settings_status.setFont_(NSFont.systemFontOfSize_(12))
        self.settings_status.setTextColor_(NSColor.secondaryLabelColor())
        self.settings_status.setLineBreakMode_(0)
        content.addSubview_(self.settings_status)

        self.settings_window = window
        self._load_settings_into_fields()
        window.makeKeyAndOrderFront_(self)

    @objc.python_method
    def _load_settings_into_fields(self) -> None:
        data = load_model_settings()
        self.optimize_hotkey_field.setStringValue_(data["optimize_hotkey"] or DEFAULT_OPTIMIZE_HOTKEY)
        self.undo_hotkey_field.setStringValue_(data["undo_hotkey"] or DEFAULT_UNDO_HOTKEY)
        self.settings_status.setStringValue_(f"Settings are saved to {ENV_PATH}.")
        if hasattr(self, "settings_quota_label"):
            self.settings_quota_label.setStringValue_(self._quota_text())
        self._refresh_cloud_quota_async()

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
        if self._quota_exhausted():
            return f"Machine code: {self.machine_code}"
        if self.cloud_plan == "paid":
            return "Activated"
        if self.quota_remaining is not None and self.quota_daily_limit is not None:
            return f"{self.quota_remaining}/{self.quota_daily_limit} available; refills 1 every 10 minutes"
        if self.quota_refreshing:
            return "Loading..."
        return "Unavailable"


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
