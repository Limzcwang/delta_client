"""Win32 全局热键：游戏前台也能触发悬浮窗显示/编辑。"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
HOTKEY_TOGGLE_ID = 0x4C01
HOTKEY_EDIT_ID = 0x4C02


@dataclass(frozen=True)
class HotkeySpec:
    modifiers: int
    vk: int
    label: str


def parse_hotkey(text: str) -> HotkeySpec | None:
    tokens = [token.strip() for token in str(text or "").replace("＋", "+").split("+") if token.strip()]
    if not tokens:
        return None
    modifiers = 0
    key = ""
    for token in tokens:
        upper = token.upper()
        if upper in ("CTRL", "CONTROL"):
            modifiers |= MOD_CONTROL
        elif upper == "ALT":
            modifiers |= MOD_ALT
        elif upper == "SHIFT":
            modifiers |= MOD_SHIFT
        elif upper in ("WIN", "META", "WINDOWS"):
            modifiers |= MOD_WIN
        elif key:
            return None
        else:
            key = upper
    if not key:
        return None
    if len(key) == 1 and key.isalnum():
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 12:
        vk = 0x70 + int(key[1:]) - 1
    else:
        return None
    return HotkeySpec(modifiers=modifiers, vk=vk, label=str(text))


def _user32() -> Any:
    return ctypes.WinDLL("user32", use_last_error=True)


def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, vk: int) -> bool:
    try:
        return bool(_user32().RegisterHotKey(int(hwnd), int(hotkey_id), int(modifiers), int(vk)))
    except Exception:  # noqa: BLE001
        return False


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    try:
        _user32().UnregisterHotKey(int(hwnd), int(hotkey_id))
    except Exception:  # noqa: BLE001
        pass


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, manager: "GlobalHotkeyManager") -> None:
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type: Any, message: Any) -> bool:  # noqa: N802
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            message_id = int(msg.message)
            if message_id == WM_HOTKEY:
                logger.info(
                    "nativeEvent WM_HOTKEY hwnd=%s id=%s modifiers=%s vk=%s",
                    int(msg.hwnd) if msg.hwnd else 0, int(msg.wParam), int(msg.lParam) & 0xFFFF,
                    (int(msg.lParam) >> 16) & 0xFFFF,
                )
            return self.manager.handle_message(message_id, int(msg.wParam))
        except Exception:  # noqa: BLE001
            return False


class GlobalHotkeyManager(QObject):
    triggered = Signal(str)  # action

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = QWidget()
        self._window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        # hwnd=0 注册到线程消息队列，由 Qt 原生事件过滤器接收 WM_HOTKEY；
        # 隐藏 QWidget 的 HWND 在部分游戏/DPI 场景下收不到热键消息。
        self._hwnd = 0
        self._filter = _NativeFilter(self)
        self._installed = False
        self._registered: dict[str, int] = {}
        self._failed: dict[str, str] = {}
        self._specs: dict[str, HotkeySpec] = {}

    @property
    def registered_actions(self) -> set[str]:
        return set(self._registered)

    @property
    def failures(self) -> dict[str, str]:
        return dict(self._failed)

    def start(self) -> None:
        if not self._installed and QApplication.instance() is not None:
            QApplication.instance().installNativeEventFilter(self._filter)
            self._installed = True
            logger.info("nativeEventFilter 已安装 hwnd=%s", self._hwnd)

    def stop(self) -> None:
        self.unregister_all()
        if self._installed and QApplication.instance() is not None:
            QApplication.instance().removeNativeEventFilter(self._filter)
        self._installed = False
        try:
            self._window.close()
            self._window.deleteLater()
        except Exception:  # noqa: BLE001
            pass

    def unregister_all(self) -> None:
        for hotkey_id in self._registered.values():
            unregister_hotkey(self._hwnd, hotkey_id)
        self._registered.clear()
        self._failed.clear()
        self._specs.clear()

    def register_all(self, toggle_text: str, edit_text: str) -> dict[str, str]:
        self.start()
        self.unregister_all()
        for action, text, hotkey_id in (
            ("toggle", toggle_text, HOTKEY_TOGGLE_ID),
            ("edit", edit_text, HOTKEY_EDIT_ID),
        ):
            spec = parse_hotkey(text)
            if spec is None:
                self._failed[action] = f"快捷键格式不支持：{text}（仅单键或 Ctrl/Alt/Shift+字母/数字/F1-F12）"
                logger.info(
                    "全局热键注册 action=%s key=%s success=False error=invalid",
                    action, text,
                )
                continue
            if register_hotkey(self._hwnd, hotkey_id, spec.modifiers, spec.vk):
                self._registered[action] = hotkey_id
                self._specs[action] = spec
                logger.info(
                    "全局热键注册 action=%s key=%s success=True error=0",
                    action, text,
                )
            else:
                error = int(ctypes.get_last_error() or 1409)
                hint = "（1409=被其他程序占用）" if error == 1409 else ""
                self._failed[action] = f"快捷键被其他程序占用，请换一个：{text}（错误码 {error}{hint}）"
                logger.info(
                    "全局热键注册 action=%s key=%s success=False error=%s",
                    action, text, error,
                )
        logger.info("热键注册映射 action/id=%s", dict(self._registered))
        return dict(self._failed)

    def spec_for(self, action: str) -> HotkeySpec | None:
        return self._specs.get(str(action))

    def handle_message(self, message: int, wparam: int) -> bool:
        if int(message) != WM_HOTKEY:
            return False
        for action, hotkey_id in self._registered.items():
            if int(wparam) == hotkey_id:
                logger.info("WM_HOTKEY 命中 action=%s id=%s", action, hotkey_id)
                self.triggered.emit(action)
                return True
        logger.info("WM_HOTKEY 未命中 id=%s", int(wparam))
        return False
