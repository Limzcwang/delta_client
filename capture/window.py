"""E3b1：Windows 顶层窗口查找（进程名/标题/尺寸兜底 + 诊断）。"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_PROCESS_NAME = "DeltaForceClient-Win64-Shipping"
DEFAULT_TITLE_KEYWORDS = ("三角洲", "Delta Force", "DeltaForce")
MIN_CLIENT_WIDTH = 800
MIN_CLIENT_HEIGHT = 600
_OWN_PROCESS_NAMES = {"python", "pythonw", "deltaclient"}


def _is_own_client(candidate: "WindowCandidate") -> bool:
    if normalize_process_name(candidate.process_name) in _OWN_PROCESS_NAMES:
        return True
    return candidate.title.strip().lower().startswith("delta client")

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


def normalize_process_name(name: str) -> str:
    """进程名归一化：去路径/引号、去扩展名、忽略大小写。"""
    text = str(name or "").strip().strip('"')
    base = os.path.basename(text)
    stem, _ext = os.path.splitext(base)
    return stem.lower()


@dataclass(frozen=True)
class WindowCandidate:
    hwnd: int
    pid: int
    title: str
    process_name: str
    client_left: int
    client_top: int
    client_width: int
    client_height: int
    minimized: bool = False

    @property
    def client_rect(self) -> tuple[int, int, int, int]:
        return (self.client_left, self.client_top, self.client_width, self.client_height)

    @property
    def process_label(self) -> str:
        return self.process_name or "(进程名读取失败)"


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
    match_method: str = ""

    @property
    def client_rect(self) -> tuple[int, int, int, int]:
        return (self.client_left, self.client_top, self.client_width, self.client_height)

    @property
    def is_minimized(self) -> bool:
        return bool(_user32.IsIconic(self.hwnd))


@dataclass
class WindowSearchResult:
    window: WindowInfo | None = None
    reason: str = ""
    candidates: list[WindowCandidate] = field(default_factory=list)
    match_method: str = ""


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
    except (OSError, ValueError):
        return ""
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


def _enumerate_candidates() -> list[WindowCandidate]:
    candidates: list[WindowCandidate] = []

    @_EnumWindowsProc
    def callback(hwnd, _lparam):
        try:
            if not _user32.IsWindowVisible(hwnd):
                return True
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title = _window_title(hwnd)
            left, top, width, height = _client_geometry(hwnd)
            if width <= 0 or height <= 0:
                return True
            candidates.append(
                WindowCandidate(
                    hwnd=int(hwnd),
                    pid=int(pid.value),
                    title=title,
                    process_name=_process_name(pid.value),
                    client_left=left,
                    client_top=top,
                    client_width=width,
                    client_height=height,
                    minimized=bool(_user32.IsIconic(hwnd)),
                )
            )
            return True
        except Exception:  # noqa: BLE001 - 枚举过程不能中断
            return True

    _user32.EnumWindows(callback, 0)
    return candidates


def list_visible_windows() -> list[WindowCandidate]:
    return [
        candidate
        for candidate in _enumerate_candidates()
        if candidate.title.strip() and not candidate.minimized
    ]


def _match_method(
    candidate: WindowCandidate,
    process_name: str,
    title_keywords: tuple[str, ...],
    min_size: tuple[int, int],
    *,
    allow_title: bool = True,
) -> str:
    if _is_own_client(candidate):
        return ""
    if candidate.client_width < min_size[0] or candidate.client_height < min_size[1]:
        return ""
    wanted = normalize_process_name(process_name)
    if wanted and normalize_process_name(candidate.process_name) == wanted:
        return "process"
    if not allow_title:
        return ""
    title_lower = candidate.title.lower()
    for keyword in title_keywords:
        if keyword and str(keyword).lower() in title_lower:
            return "title"
    return ""


def find_game_window(
    process_name: str = DEFAULT_PROCESS_NAME,
    *,
    title_keywords: tuple[str, ...] = DEFAULT_TITLE_KEYWORDS,
    min_size: tuple[int, int] = (MIN_CLIENT_WIDTH, MIN_CLIENT_HEIGHT),
    candidates: list[WindowCandidate] | None = None,
) -> WindowSearchResult:
    """按进程名（忽略 .exe/大小写）-> 标题关键词兜底，要求可见且客户区足够大。"""
    all_candidates = list(candidates) if candidates is not None else _enumerate_candidates()
    best: tuple[str, WindowCandidate] | None = None
    # 先按进程名匹配（最可靠），再按标题兜底，避免先枚举到同标题的客户端窗口。
    for allow_title in (False, True):
        for candidate in all_candidates:
            method = _match_method(candidate, process_name, title_keywords, min_size, allow_title=allow_title)
            if method:
                best = (method, candidate)
                break
        if best is not None:
            break
    if best is None:
        if all_candidates:
            logger.info(
                "未找到游戏窗口；候选：%s",
                [
                    {"pid": item.pid, "title": item.title, "exe": item.process_label,
                     "size": (item.client_width, item.client_height)}
                    for item in all_candidates
                ],
            )
        return WindowSearchResult(
            None,
            "未找到游戏窗口（无匹配窗口）",
            all_candidates,
        )
    method, candidate = best
    window = WindowInfo(
        hwnd=candidate.hwnd,
        pid=candidate.pid,
        title=candidate.title,
        process_name=candidate.process_name,
        client_left=candidate.client_left,
        client_top=candidate.client_top,
        client_width=candidate.client_width,
        client_height=candidate.client_height,
        match_method=method,
    )
    reason = "通过标题匹配" if method == "title" else "通过进程名匹配"
    if candidate.minimized:
        reason = "窗口已最小化"
    return WindowSearchResult(window, reason, all_candidates, method)


def find_window_by_process(
    process_name: str = DEFAULT_PROCESS_NAME, *, require_title: bool = True
) -> WindowInfo | None:
    return find_game_window(process_name).window
