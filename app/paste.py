from __future__ import annotations

import platform
import time
from dataclasses import dataclass
from typing import Any


SENTINEL_PREFIX = "__JUSTSAYING_EMPTY_"


@dataclass(frozen=True)
class CapturedText:
    text: str
    previous_clipboard: str | None
    ax_element: Any | None = None
    method: str = "keyboard"


def capture_focused_text(target_pid: int | None = None) -> CapturedText:
    if target_pid is not None:
        ax_capture = _capture_with_accessibility(target_pid)
        if ax_capture:
            return ax_capture

    return _capture_with_keyboard()


def replace_captured_text(captured: CapturedText, text: str) -> None:
    if captured.ax_element is not None and _replace_with_accessibility(
        captured.ax_element,
        text,
    ):
        return

    replace_focused_text(text, captured.previous_clipboard)


def _capture_with_accessibility(target_pid: int) -> CapturedText | None:
    try:
        from ApplicationServices import (
            AXUIElementCreateApplication,
            AXUIElementCopyAttributeValue,
            kAXFocusedUIElementAttribute,
            kAXValueAttribute,
        )

        app_element = AXUIElementCreateApplication(target_pid)
        err, focused = AXUIElementCopyAttributeValue(
            app_element,
            kAXFocusedUIElementAttribute,
            None,
        )
        if err != 0 or focused is None:
            return None

        err, value = AXUIElementCopyAttributeValue(focused, kAXValueAttribute, None)
        if err != 0 or not isinstance(value, str):
            return None

        return CapturedText(
            text=str(value),
            previous_clipboard=None,
            ax_element=focused,
            method="accessibility",
        )
    except Exception:
        return None


def _replace_with_accessibility(ax_element: Any, text: str) -> bool:
    try:
        from ApplicationServices import AXUIElementSetAttributeValue, kAXValueAttribute

        return AXUIElementSetAttributeValue(ax_element, kAXValueAttribute, text) == 0
    except Exception:
        return False


def _capture_with_keyboard() -> CapturedText:
    import pyautogui
    import pyperclip

    previous_clipboard = _safe_paste()
    if previous_clipboard and previous_clipboard.startswith(SENTINEL_PREFIX):
        previous_clipboard = ""
    sentinel = f"{SENTINEL_PREFIX}{time.monotonic_ns()}__"

    pyperclip.copy(sentinel)
    time.sleep(0.05)
    _select_all(pyautogui)
    time.sleep(0.08)
    _copy(pyautogui)
    time.sleep(0.18)

    copied = _safe_paste()
    if copied is None or copied == sentinel:
        _restore_clipboard(previous_clipboard)
        raise RuntimeError("没有读到当前输入框里的文字。先点一下目标输入框，再点浮窗按钮。")

    return CapturedText(text=copied, previous_clipboard=previous_clipboard)


def replace_focused_text(text: str, restore_clipboard: str | None = None) -> None:
    if not text:
        return

    import pyautogui
    import pyperclip

    pyperclip.copy(text)
    time.sleep(0.08)
    _select_all(pyautogui)
    time.sleep(0.08)
    _paste(pyautogui)
    time.sleep(0.2)
    _restore_clipboard(restore_clipboard)


def paste_text(text: str) -> None:
    replace_focused_text(text, _safe_paste())


def _select_all(pyautogui_module) -> None:
    _hotkey(pyautogui_module, "a")


def _copy(pyautogui_module) -> None:
    _hotkey(pyautogui_module, "c")


def _paste(pyautogui_module) -> None:
    _hotkey(pyautogui_module, "v")


def _hotkey(pyautogui_module, key: str) -> None:
    if platform.system().lower() == "darwin":
        pyautogui_module.hotkey("command", key)
    else:
        pyautogui_module.hotkey("ctrl", key)


def _safe_paste() -> str | None:
    try:
        import pyperclip

        return pyperclip.paste()
    except Exception:
        return None


def _restore_clipboard(value: str | None) -> None:
    if value is None:
        return

    try:
        import pyperclip

        pyperclip.copy(value)
    except Exception:
        pass
