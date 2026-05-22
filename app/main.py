from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import objc
import pyperclip
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
    NSPopUpButton,
    NSScrollView,
    NSScreen,
    NSSecureTextField,
    NSStatusBar,
    NSTextField,
    NSTextView,
    NSView,
    NSVisualEffectView,
    NSWorkspace,
    NSEvent,
)
from Foundation import NSAttributedString, NSObject, NSTimer
from PyObjCTools import AppHelper

from .model_config import (
    ENV_PATH,
    DEFAULT_OPTIMIZE_HOTKEY,
    DEFAULT_OPTIMIZE_PROMPT,
    DEFAULT_UNDO_HOTKEY,
    get_active_model_config,
    list_remote_models,
    load_api_key,
    load_model_settings,
    provider_by_id,
    provider_by_name,
    provider_names,
    save_model_settings,
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
        self.collapsed = False
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
        self.window.orderFrontRegardless()

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
        self.target_name = front_app.localizedName() or "目标 App"
        if not self.busy:
            self._set_status(self._ready_status())

    def optimize_(self, sender) -> None:
        self._start_optimize()

    def undo_(self, sender) -> None:
        self._start_undo()

    def toggleCollapse_(self, sender) -> None:
        self.hideFloatingWindow_(sender)

    def hideFloatingWindow_(self, sender) -> None:
        self._hide_floating_window()

    def showFloatingWindow_(self, sender) -> None:
        self._show_floating_window()

    def openPermissions_(self, sender) -> None:
        self._open_permission_settings()

    def openSettings_(self, sender) -> None:
        self._show_settings_window()

    def settingsProviderChanged_(self, sender) -> None:
        provider = provider_by_name(str(self.provider_popup.titleOfSelectedItem()))
        self.base_url_field.setStringValue_(provider.base_url)
        self.model_field.setStringValue_(provider.default_model)
        self.model_popup.removeAllItems()
        self.settings_status.setStringValue_("切换 provider 后，填写 API key 并寻找模型。")

    def settingsModelChanged_(self, sender) -> None:
        selected = self.model_popup.titleOfSelectedItem()
        if selected:
            self.model_field.setStringValue_(str(selected))

    def pasteApiKey_(self, sender) -> None:
        try:
            text = pyperclip.paste().strip()
        except Exception as exc:
            self.settings_status.setStringValue_(f"读取剪贴板失败：{exc}")
            return
        if not text:
            self.settings_status.setStringValue_("剪贴板里没有可粘贴的文本。")
            return
        self.api_key_field.setStringValue_(text)
        self.settings_status.setStringValue_("已从剪贴板填入 API key。")

    def findModels_(self, sender) -> None:
        if getattr(self, "settings_busy", False):
            return

        provider = provider_by_name(str(self.provider_popup.titleOfSelectedItem()))
        base_url = str(self.base_url_field.stringValue()).strip()
        api_key = str(self.api_key_field.stringValue()).strip() or load_api_key(
            provider.provider_id,
        )

        self.settings_busy = True
        self.find_models_button.setEnabled_(False)
        self.save_settings_button.setEnabled_(False)
        self.settings_status.setStringValue_("正在寻找模型...")
        threading.Thread(
            target=self._find_models_worker,
            args=(base_url, api_key),
            daemon=True,
        ).start()

    def saveSettings_(self, sender) -> None:
        provider = provider_by_name(str(self.provider_popup.titleOfSelectedItem()))
        base_url = str(self.base_url_field.stringValue()).strip()
        model = str(self.model_field.stringValue()).strip()
        api_key = str(self.api_key_field.stringValue()).strip()
        optimize_prompt_text = str(self.prompt_text_view.string()).strip()
        optimize_hotkey = str(self.optimize_hotkey_field.stringValue()).strip()
        undo_hotkey = str(self.undo_hotkey_field.stringValue()).strip()

        if not base_url:
            self.settings_status.setStringValue_("请填写 Base URL。")
            return
        if not model:
            self.settings_status.setStringValue_("请填写或选择模型。")
            return
        try:
            optimize_spec = _parse_hotkey(optimize_hotkey or DEFAULT_OPTIMIZE_HOTKEY)
            undo_spec = _parse_hotkey(undo_hotkey or DEFAULT_UNDO_HOTKEY)
        except ValueError as exc:
            self.settings_status.setStringValue_(f"快捷键格式错误：{exc}")
            return
        if _same_hotkey(optimize_spec, undo_spec):
            self.settings_status.setStringValue_("优化和还原不能使用同一个快捷键。")
            return

        try:
            save_model_settings(
                provider.provider_id,
                base_url,
                model,
                api_key,
                optimize_prompt_text or DEFAULT_OPTIMIZE_PROMPT,
                optimize_hotkey or DEFAULT_OPTIMIZE_HOTKEY,
                undo_hotkey or DEFAULT_UNDO_HOTKEY,
            )
        except Exception as exc:
            self.settings_status.setStringValue_(f"保存失败：{exc}")
            return

        self._reload_hotkeys_from_settings()
        self._sync_key_event_tap()
        self._update_hotkey_tooltips()
        self.settings_status.setStringValue_(f"已保存到 {ENV_PATH}。")
        self._set_status(self._ready_status())
        self.settings_window.orderOut_(self)

    def cancelSettings_(self, sender) -> None:
        self.settings_window.orderOut_(self)

    @objc.python_method
    def _start_optimize(self) -> None:
        if self.busy:
            return
        if not AXIsProcessTrusted():
            self._request_accessibility_permission(show_help=True)
            return

        self._set_status("正在读取当前输入框...")
        self._set_busy(True)
        self._set_button_title(self.optimize_button, "...", primary=True)
        threading.Thread(target=self._optimize_worker, daemon=True).start()

    @objc.python_method
    def _start_undo(self) -> None:
        if self.busy:
            return
        if not self.last_original or self.last_capture is None:
            self._set_status("没有可撤销的优化。")
            if hasattr(self, "undo_button"):
                self._set_button_title(self.undo_button, "无", primary=False)
                self._reset_title_later()
            return

        self._set_status("正在恢复上一次优化前的文本...")
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
                raise RuntimeError("当前输入框是空的。")

            AppHelper.callAfter(self._set_status, "正在优化文字...")
            cleaned = optimize_prompt(original, "medium").strip()
            if not cleaned:
                raise RuntimeError("优化结果为空，没有替换。")

            self._activate_target_app()
            replace_captured_text(captured, cleaned)
            self.last_original = original
            self.last_capture = captured
            AppHelper.callAfter(self._finish, f"已替换（{captured.method}）。")
        except Exception as exc:
            AppHelper.callAfter(self._fail, str(exc))

    @objc.python_method
    def _restore_worker(self) -> None:
        try:
            self._activate_target_app()
            if self.last_capture is None:
                raise RuntimeError("没有可恢复的原文。")
            replace_captured_text(self.last_capture, self.last_original or "")
            AppHelper.callAfter(self._finish_undo, "已恢复原文。")
        except Exception as exc:
            AppHelper.callAfter(self._fail, str(exc))

    @objc.python_method
    def _finish(self, message: str) -> None:
        self._set_status(message)
        self._set_busy(False)
        self._set_button_title(self.optimize_button, "完成", primary=True)
        self._reset_title_later()

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
        self._set_status(f"失败：{message}")
        self._set_busy(False)
        self._set_button_title(self.optimize_button, "失败", primary=True)
        self._reset_title_later()

    @objc.python_method
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        for button in self.buttons:
            button.setEnabled_(not busy)
        if hasattr(self, "undo_button"):
            self.undo_button.setEnabled_((not busy) and bool(self.last_original))

    @objc.python_method
    def _set_status(self, message: str) -> None:
        self.status_message = message
        if hasattr(self, "optimize_button"):
            self.optimize_button.setToolTip_(f"{message} | 快捷键：{self.optimize_hotkey.raw}")
        if hasattr(self, "status_dot"):
            self._refresh_status_dot()

    @objc.python_method
    def _reset_title_later(self) -> None:
        threading.Timer(1.1, lambda: AppHelper.callAfter(self._reset_optimize_title)).start()

    @objc.python_method
    def _reset_optimize_title(self) -> None:
        if self.busy:
            return
        if hasattr(self, "optimize_button"):
            self._set_button_title(self.optimize_button, "优化", primary=True)
        if hasattr(self, "undo_button"):
            self._set_button_title(self.undo_button, "撤", primary=False)
            self.undo_button.setEnabled_(bool(self.last_original))
        if hasattr(self, "collapse_button"):
            self._set_button_title(self.collapse_button, "-", primary=False)

    @objc.python_method
    def _install_status_item(self) -> None:
        length = _appkit_constant("NSVariableStatusItemLength", "NSVariableStatusItemLength")
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(length)
        button = self.status_item.button()
        if button is not None:
            button.setTitle_("JS")
            button.setToolTip_("Just Saying")

        menu = NSMenu.alloc().initWithTitle_("Just Saying")
        for title, action in (
            ("显示浮窗", "showFloatingWindow:"),
            ("设置", "openSettings:"),
            ("打开授权设置", "openPermissions:"),
        ):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            menu.addItem_(item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("退出", "terminate:", "q")
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
        if self.collapsed:
            self._set_collapsed(False)
        self.window.orderFrontRegardless()
        self._set_status(self._ready_status())

    @objc.python_method
    def _request_accessibility_permission(self, show_help: bool = False) -> bool:
        if AXIsProcessTrusted():
            self.needs_accessibility = False
            self._refresh_status_dot()
            return True

        self.needs_accessibility = True
        self._set_status("需要 macOS Accessibility 授权。")
        if show_help:
            self._show_permission_notice(
                "accessibility",
                "Just Saying 需要一次授权",
                "请在 macOS Accessibility / 辅助功能 里打开 Just Saying。若开关已经打开但仍提示授权，通常是旧构建残留；请重新添加 /Applications/Just Saying.app，授权后完全退出并重新打开。",
            )
        return False

    @objc.python_method
    def _open_permission_settings(self, kind: str = "all") -> None:
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
            alert.addButtonWithTitle_("知道了")
            alert.runModal()
        except Exception:
            pass

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
                self._ready_status() + f" | 快捷键：{self.optimize_hotkey.raw}",
            )
        if hasattr(self, "undo_button"):
            self.undo_button.setToolTip_(f"Undo：{self.undo_hotkey.raw}")

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
            self._set_status("普通按键快捷键需要 Input Monitoring 授权。")
            if show_notice:
                self._show_permission_notice(
                    "input-monitoring",
                    "快捷键需要输入监听权限",
                    "请在 macOS Input Monitoring / 输入监听 里打开 Just Saying；也可以把快捷键改回 option+shift 来避免这个权限。",
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
        self._refresh_status_dot()
        if had_warning and not has_warning and not self.busy:
            self._set_status(self._ready_status())

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
    def _set_collapsed(self, collapsed: bool) -> None:
        if not hasattr(self, "window") or not hasattr(self, "chrome"):
            return
        if self.collapsed == collapsed:
            return

        self.collapsed = collapsed
        width = 54 if collapsed else 188
        height = 38 if collapsed else 48
        frame = self.window.frame()
        right = frame.origin.x + frame.size.width
        top = frame.origin.y + frame.size.height
        new_frame = NSMakeRect(right - width, top - height, width, height)
        self.window.setFrame_display_animate_(new_frame, True, True)
        self.chrome.setFrame_(NSMakeRect(0, 0, width, height))
        self.chrome.layer().setCornerRadius_(height / 2)

        self.optimize_button.setHidden_(collapsed)
        self.undo_button.setHidden_(collapsed)
        self.settings_button.setHidden_(collapsed)

        if collapsed:
            self.status_dot.setFrame_(NSMakeRect(11, 16, 7, 7))
            self.collapse_button.setFrame_(NSMakeRect(23, 4, 24, 30))
            self._set_button_title(self.collapse_button, "+", primary=False)
            self.collapse_button.setToolTip_("展开浮窗")
            return

        self.status_dot.setFrame_(NSMakeRect(13, 21, 7, 7))
        self.optimize_button.setFrame_(NSMakeRect(24, 8, 72, 30))
        self.undo_button.setFrame_(NSMakeRect(100, 8, 24, 30))
        self.settings_button.setFrame_(NSMakeRect(128, 8, 24, 30))
        self.collapse_button.setFrame_(NSMakeRect(156, 8, 24, 30))
        self._set_button_title(self.collapse_button, "-", primary=False)
        self.collapse_button.setToolTip_("缩小浮窗")

    @objc.python_method
    def _find_models_worker(self, base_url: str, api_key: str) -> None:
        try:
            models = list_remote_models(base_url, api_key)
            AppHelper.callAfter(self._finish_find_models, models)
        except Exception as exc:
            AppHelper.callAfter(self._fail_find_models, str(exc))

    @objc.python_method
    def _finish_find_models(self, models: list[str]) -> None:
        self.model_popup.removeAllItems()
        self.model_popup.addItemsWithTitles_(models)
        if models:
            current_model = str(self.model_field.stringValue()).strip()
            if current_model in models:
                self.model_popup.selectItemWithTitle_(current_model)
            else:
                self.model_popup.selectItemAtIndex_(0)
                self.model_field.setStringValue_(models[0])
        self.settings_status.setStringValue_(f"找到 {len(models)} 个模型。")
        self._set_settings_busy(False)

    @objc.python_method
    def _fail_find_models(self, message: str) -> None:
        self.settings_status.setStringValue_(message)
        self._set_settings_busy(False)

    @objc.python_method
    def _set_settings_busy(self, busy: bool) -> None:
        self.settings_busy = busy
        self.find_models_button.setEnabled_(not busy)
        self.save_settings_button.setEnabled_(not busy)

    @objc.python_method
    def _activate_target_app(self) -> None:
        if self.target_app is None:
            raise RuntimeError("还没有目标 App。先点一下要改写的对话框。")
        if self.target_app.isTerminated():
            raise RuntimeError("目标 App 已关闭。先重新点一下要改写的对话框。")

        self.target_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.25)

    @objc.python_method
    def _ready_status(self) -> str:
        target = f"目标：{self.target_name}" if self.target_name else "先点目标输入框"
        model_config = get_active_model_config()
        if model_config.llm_enabled:
            return f"就绪：{model_config.provider_name} / {model_config.model} | {target}"
        return f"就绪：未配置模型，使用本地基础清洗 | {target}"

    @objc.python_method
    def _build_window(self) -> NSPanel:
        width = 188
        height = 48
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
        self.chrome.layer().setCornerRadius_(24)
        self.chrome.layer().setMasksToBounds_(True)
        content.addSubview_(self.chrome)

        self.status_dot = NSView.alloc().initWithFrame_(NSMakeRect(13, 21, 7, 7))
        self.status_dot.setWantsLayer_(True)
        self.status_dot.layer().setCornerRadius_(3.5)
        self._refresh_status_dot()
        self.chrome.addSubview_(self.status_dot)

        self.optimize_button = self._button("优化", "optimize:", 24, 8, 72)
        self._style_floating_button(self.optimize_button, primary=True)
        self.optimize_button.setToolTip_(self._ready_status() + f" | 快捷键：{self.optimize_hotkey.raw}")
        self.chrome.addSubview_(self.optimize_button)

        self.undo_button = self._button("撤", "undo:", 100, 8, 24)
        self._style_floating_button(self.undo_button, primary=False)
        self.undo_button.setToolTip_(f"Undo：{self.undo_hotkey.raw}")
        self.undo_button.setEnabled_(False)
        self.chrome.addSubview_(self.undo_button)

        self.settings_button = self._button("...", "openSettings:", 128, 8, 24)
        self._style_floating_button(self.settings_button, primary=False)
        self.settings_button.setToolTip_("设置 API、模型和优化提示词")
        self.chrome.addSubview_(self.settings_button)

        self.collapse_button = self._button("-", "toggleCollapse:", 156, 8, 24)
        self._style_floating_button(self.collapse_button, primary=False)
        self.collapse_button.setToolTip_("隐藏浮窗，可从菜单栏 JS 恢复")
        self.chrome.addSubview_(self.collapse_button)

        self.buttons = [
            self.optimize_button,
            self.undo_button,
            self.settings_button,
            self.collapse_button,
        ]
        self.status_message = self._ready_status()

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

        font = (
            NSFont.systemFontOfSize_weight_(13, 0.38)
            if primary
            else NSFont.boldSystemFontOfSize_(13)
        )
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
    def _refresh_status_dot(self) -> None:
        if not hasattr(self, "status_dot"):
            return
        model_config = get_active_model_config()
        if self.needs_accessibility or self.needs_input_monitoring:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.26, 0.23, 0.95)
        elif model_config.llm_enabled:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.20, 0.90, 0.58, 0.95)
        else:
            color = NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.67, 0.25, 0.90)
        self.status_dot.layer().setBackgroundColor_(color.CGColor())

    @objc.python_method
    def _show_settings_window(self) -> None:
        if hasattr(self, "settings_window") and self.settings_window:
            self.settings_window.makeKeyAndOrderFront_(self)
            self._load_settings_into_fields()
            return

        self.settings_busy = False
        width = 560
        height = 650
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
        window.setTitle_("Just Saying 设置")
        window.setFloatingPanel_(True)
        window.setHidesOnDeactivate_(False)

        content = window.contentView()
        content.setWantsLayer_(True)
        content.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())

        self._label(content, "Provider", 20, 590, 100, 18)
        self.provider_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 584, 388, 28),
            False,
        )
        self.provider_popup.addItemsWithTitles_(provider_names())
        self.provider_popup.setTarget_(self)
        self.provider_popup.setAction_("settingsProviderChanged:")
        content.addSubview_(self.provider_popup)

        self._label(content, "API Key", 20, 550, 100, 18)
        self.api_key_field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(132, 544, 300, 26),
        )
        self.api_key_field.setPlaceholderString_("保存后写入本地 .env")
        content.addSubview_(self.api_key_field)

        paste_key_button = self._button("粘贴", "pasteApiKey:", 442, 542, 78)
        content.addSubview_(paste_key_button)

        self._label(content, "Base URL", 20, 510, 100, 18)
        self.base_url_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 504, 388, 26),
        )
        content.addSubview_(self.base_url_field)

        self._label(content, "模型", 20, 470, 100, 18)
        self.model_field = NSTextField.alloc().initWithFrame_(NSMakeRect(132, 464, 388, 26))
        content.addSubview_(self.model_field)

        self._label(content, "搜索结果", 20, 430, 100, 18)
        self.model_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 424, 388, 28),
            False,
        )
        self.model_popup.setTarget_(self)
        self.model_popup.setAction_("settingsModelChanged:")
        content.addSubview_(self.model_popup)

        self._label(content, "优化快捷键", 20, 390, 100, 18)
        self.optimize_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 384, 170, 26),
        )
        self.optimize_hotkey_field.setPlaceholderString_(DEFAULT_OPTIMIZE_HOTKEY)
        content.addSubview_(self.optimize_hotkey_field)
        self._label(content, "例：option+shift / option+space", 314, 389, 220, 18)

        self._label(content, "还原快捷键", 20, 354, 100, 18)
        self.undo_hotkey_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 348, 170, 26),
        )
        self.undo_hotkey_field.setPlaceholderString_(DEFAULT_UNDO_HOTKEY)
        content.addSubview_(self.undo_hotkey_field)
        self._label(content, "例：option*3 / command+z", 314, 353, 220, 18)

        self._label(content, "优化提示词", 20, 312, 100, 18)
        prompt_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(132, 112, 388, 190))
        prompt_scroll.setHasVerticalScroller_(True)
        prompt_scroll.setBorderType_(_appkit_constant("NSBezelBorder", "NSBezelBorder"))
        self.prompt_text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 388, 190))
        self.prompt_text_view.setFont_(NSFont.systemFontOfSize_(13))
        self.prompt_text_view.setString_(DEFAULT_OPTIMIZE_PROMPT)
        prompt_scroll.setDocumentView_(self.prompt_text_view)
        content.addSubview_(prompt_scroll)

        self.find_models_button = self._button("寻找模型", "findModels:", 132, 66, 110)
        self.save_settings_button = self._button("保存", "saveSettings:", 252, 66, 90)
        cancel_button = self._button("取消", "cancelSettings:", 352, 66, 90)
        content.addSubview_(self.find_models_button)
        content.addSubview_(self.save_settings_button)
        content.addSubview_(cancel_button)

        self.settings_status = NSTextField.labelWithString_(f"设置会保存到 {ENV_PATH}。")
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
        provider = provider_by_id(data["provider_id"])
        self.provider_popup.selectItemWithTitle_(provider.name)
        self.base_url_field.setStringValue_(data["base_url"] or provider.base_url)
        self.model_field.setStringValue_(data["model"] or provider.default_model)
        self.api_key_field.setStringValue_(data["api_key"] or "")
        self.optimize_hotkey_field.setStringValue_(data["optimize_hotkey"] or DEFAULT_OPTIMIZE_HOTKEY)
        self.undo_hotkey_field.setStringValue_(data["undo_hotkey"] or DEFAULT_UNDO_HOTKEY)
        self.prompt_text_view.setString_(data["optimize_prompt"] or DEFAULT_OPTIMIZE_PROMPT)
        self.model_popup.removeAllItems()
        self.settings_status.setStringValue_(f"设置会保存到 {ENV_PATH}。")

    @objc.python_method
    def _label(self, content, text: str, x: int, y: int, width: int, height: int) -> None:
        label = NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(x, y, width, height))
        label.setFont_(NSFont.systemFontOfSize_(12))
        label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(label)


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
        raise ValueError("快捷键不能为空。")

    tap = _parse_tap_hotkey(raw, normalized)
    if tap:
        return tap

    parts = [part for part in normalized.split("+") if part]
    if not parts:
        raise ValueError(f"无法识别 `{raw}`。")

    modifiers: list[str] = []
    key: str | None = None
    for part in parts:
        modifier = MODIFIER_ALIASES.get(part)
        if modifier:
            modifiers.append(modifier)
            continue
        key = part

    if not modifiers:
        raise ValueError("至少需要一个修饰键，比如 option 或 shift。")

    modifier_set = frozenset(modifiers)
    if key is None:
        return HotkeySpec(raw=raw, kind="modifier", modifiers=modifier_set)

    keycode = KEY_CODES.get(key)
    if keycode is None:
        raise ValueError(f"暂不支持按键 `{key}`。")
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


def _install_edit_menu(app) -> None:
    main_menu = NSMenu.alloc().initWithTitle_("")

    app_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Just Saying",
        None,
        "",
    )
    main_menu.addItem_(app_menu_item)
    app_menu = NSMenu.alloc().initWithTitle_("Just Saying")
    app_menu_item.setSubmenu_(app_menu)
    app_menu.addItemWithTitle_action_keyEquivalent_("Quit Just Saying", "terminate:", "q")

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
