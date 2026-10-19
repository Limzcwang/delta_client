"""E3b1：Windows 顶层窗口查找（进程名 -> HWND/客户区）。"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

DEFAULT_PROCESS_NAME = "DeltaForceClient-Win64-Shipping"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = (_EnumWindowsProc, wintypes.LPARAM)
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
_user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_user32.IsWindowVisible.argtypes = (wintypes.HWND,)
_user32.IsIconic.argtypes = (wintypes.HWND,)
_user32.GetClientRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_user32.ClientToScreen.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.POINT))
_kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    process_name: str
    client_left: int
    client_top: int
    client_width: int
    client_height: int

    @property
    def client_rect(self) -> tuple[int, int, int, int]:
        return (self.client_left, self.client_top, self.client_width, self.client_height)

    @property
    def is_minimized(self) -> bool:
        return bool(_user32.IsIconic(self.hwnd))


def _process_name(pid: int) -> str:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return os.path.basename(buffer.value)
    finally:
        _kernel32.CloseHandle(handle)


def _window_title(hwnd: int) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _client_geometry(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return (0, 0, 0, 0)
    point = wintypes.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(point))
    return (point.x, point.y, max(0, rect.right - rect.left), max(0, rect.bottom - rect.top))


def find_window_by_process(process_name: str = DEFAULT_PROCESS_NAME, *, require_title: bool = True) -> WindowInfo | None:
    """EnumWindows 找匹配进程名、可见、带标题的顶层窗口；找不到返回 None。"""
    wanted = process_name.lower()
    found: list[WindowInfo] = []

    @_EnumWindowsProc
    def callback(hwnd, _lparam):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if _process_name(pid.value).lower() != wanted:
                return True
            title = _window_title(hwnd)
            if require_title and not title.strip():
                return True
            left, top, width, height = _client_geometry(hwnd)
            if width <= 0 or height <= 0:
                return True
            found.append(
                WindowInfo(
                    hwnd=int(hwnd),
                    pid=int(pid.value),
                    title=title,
                    process_name=wanted,
                    client_left=left,
                    client_top=top,
                    client_width=width,
                    client_height=height,
                )
            )
            return False
        except Exception:  # noqa: BLE001 - 枚举过程不能中断
            return True

    _user32.EnumWindows(callback, 0)
    return found[0] if found else None
