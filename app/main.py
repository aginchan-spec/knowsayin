from __future__ import annotations

import os
import threading
import time

import objc
import pyperclip
from AppKit import (
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
    NSTextField,
    NSTextView,
    NSView,
    NSVisualEffectView,
    NSWorkspace,
)
from Foundation import NSAttributedString, NSObject, NSTimer
from PyObjCTools import AppHelper

from .model_config import (
    ENV_PATH,
    DEFAULT_OPTIMIZE_PROMPT,
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


class JustSayingApp(NSObject):
    def applicationDidFinishLaunching_(self, notification) -> None:
        self.busy = False
        self.own_pid = os.getpid()
        self.target_app = None
        self.target_pid = None
        self.target_name = None
        self.last_original: str | None = None
        self.last_capture: CapturedText | None = None
        self.buttons: list[NSButton] = []
        self.window = self._build_window()
        self.tracker = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.25,
            self,
            "trackFrontApp:",
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

        if not base_url:
            self.settings_status.setStringValue_("请填写 Base URL。")
            return
        if not model:
            self.settings_status.setStringValue_("请填写或选择模型。")
            return

        try:
            save_model_settings(
                provider.provider_id,
                base_url,
                model,
                api_key,
                optimize_prompt_text or DEFAULT_OPTIMIZE_PROMPT,
            )
        except Exception as exc:
            self.settings_status.setStringValue_(f"保存失败：{exc}")
            return

        self.settings_status.setStringValue_(f"已保存到 {ENV_PATH}。")
        self._set_status(self._ready_status())
        self.settings_window.orderOut_(self)

    def cancelSettings_(self, sender) -> None:
        self.settings_window.orderOut_(self)

    @objc.python_method
    def _start_optimize(self) -> None:
        if self.busy:
            return

        self._set_status("正在读取当前输入框...")
        self._set_busy(True)
        self._set_button_title(self.optimize_button, "...", primary=True)
        threading.Thread(target=self._optimize_worker, daemon=True).start()

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
            AppHelper.callAfter(self._finish, "已恢复原文。")
        except Exception as exc:
            AppHelper.callAfter(self._fail, str(exc))

    @objc.python_method
    def _finish(self, message: str) -> None:
        self._set_status(message)
        self._set_busy(False)
        self._set_button_title(self.optimize_button, "完成", primary=True)
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

    @objc.python_method
    def _set_status(self, message: str) -> None:
        self.status_message = message
        if hasattr(self, "optimize_button"):
            self.optimize_button.setToolTip_(message)
        if hasattr(self, "status_dot"):
            self._refresh_status_dot()

    @objc.python_method
    def _reset_title_later(self) -> None:
        threading.Timer(1.1, lambda: AppHelper.callAfter(self._reset_optimize_title)).start()

    @objc.python_method
    def _reset_optimize_title(self) -> None:
        if not self.busy and hasattr(self, "optimize_button"):
            self._set_button_title(self.optimize_button, "优化", primary=True)

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
        width = 132
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

        chrome = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, width, height))
        chrome.setMaterial_(
            _appkit_constant("NSVisualEffectMaterialHUDWindow", "NSVisualEffectMaterialPopover"),
        )
        chrome.setBlendingMode_(
            _appkit_constant(
                "NSVisualEffectBlendingModeBehindWindow",
                "NSVisualEffectBlendingModeBehindWindow",
            ),
        )
        chrome.setState_(
            _appkit_constant("NSVisualEffectStateActive", "NSVisualEffectStateActive"),
        )
        chrome.setWantsLayer_(True)
        chrome.layer().setCornerRadius_(24)
        chrome.layer().setMasksToBounds_(True)
        content.addSubview_(chrome)

        self.status_dot = NSView.alloc().initWithFrame_(NSMakeRect(13, 21, 7, 7))
        self.status_dot.setWantsLayer_(True)
        self.status_dot.layer().setCornerRadius_(3.5)
        self._refresh_status_dot()
        chrome.addSubview_(self.status_dot)

        self.optimize_button = self._button("优化", "optimize:", 24, 8, 72)
        self._style_floating_button(self.optimize_button, primary=True)
        self.optimize_button.setToolTip_(self._ready_status())
        chrome.addSubview_(self.optimize_button)

        self.settings_button = self._button("...", "openSettings:", 100, 8, 24)
        self._style_floating_button(self.settings_button, primary=False)
        self.settings_button.setToolTip_("设置 API、模型和优化提示词")
        chrome.addSubview_(self.settings_button)

        self.buttons = [self.optimize_button, self.settings_button]
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
        if model_config.llm_enabled:
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
        height = 560
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

        self._label(content, "Provider", 20, 500, 100, 18)
        self.provider_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 494, 388, 28),
            False,
        )
        self.provider_popup.addItemsWithTitles_(provider_names())
        self.provider_popup.setTarget_(self)
        self.provider_popup.setAction_("settingsProviderChanged:")
        content.addSubview_(self.provider_popup)

        self._label(content, "API Key", 20, 460, 100, 18)
        self.api_key_field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(132, 454, 300, 26),
        )
        self.api_key_field.setPlaceholderString_("保存后写入本地 .env")
        content.addSubview_(self.api_key_field)

        paste_key_button = self._button("粘贴", "pasteApiKey:", 442, 452, 78)
        content.addSubview_(paste_key_button)

        self._label(content, "Base URL", 20, 420, 100, 18)
        self.base_url_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(132, 414, 388, 26),
        )
        content.addSubview_(self.base_url_field)

        self._label(content, "模型", 20, 380, 100, 18)
        self.model_field = NSTextField.alloc().initWithFrame_(NSMakeRect(132, 374, 388, 26))
        content.addSubview_(self.model_field)

        self._label(content, "搜索结果", 20, 340, 100, 18)
        self.model_popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(132, 334, 388, 28),
            False,
        )
        self.model_popup.setTarget_(self)
        self.model_popup.setAction_("settingsModelChanged:")
        content.addSubview_(self.model_popup)

        self._label(content, "优化提示词", 20, 300, 100, 18)
        prompt_scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(132, 110, 388, 202))
        prompt_scroll.setHasVerticalScroller_(True)
        prompt_scroll.setBorderType_(_appkit_constant("NSBezelBorder", "NSBezelBorder"))
        self.prompt_text_view = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, 388, 202))
        self.prompt_text_view.setFont_(NSFont.systemFontOfSize_(13))
        self.prompt_text_view.setString_(DEFAULT_OPTIMIZE_PROMPT)
        prompt_scroll.setDocumentView_(self.prompt_text_view)
        content.addSubview_(prompt_scroll)

        self.find_models_button = self._button("寻找模型", "findModels:", 132, 64, 110)
        self.save_settings_button = self._button("保存", "saveSettings:", 252, 64, 90)
        cancel_button = self._button("取消", "cancelSettings:", 352, 64, 90)
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
