"""E3b 窗口截图采集层（WGC/mss）。"""

from capture.sources import CaptureWorker, Frame, FrameSource, MssSource, WgcSource, open_source
from capture.window import (
    DEFAULT_PROCESS_NAME,
    DEFAULT_TITLE_KEYWORDS,
    WindowCandidate,
    WindowInfo,
    WindowSearchResult,
    find_game_window,
    find_window_by_process,
    list_visible_windows,
    normalize_process_name,
)

__all__ = [
    "CaptureWorker",
    "DEFAULT_PROCESS_NAME",
    "DEFAULT_TITLE_KEYWORDS",
    "Frame",
    "FrameSource",
    "MssSource",
    "WgcSource",
    "WindowCandidate",
    "WindowInfo",
    "WindowSearchResult",
    "find_game_window",
    "find_window_by_process",
    "list_visible_windows",
    "normalize_process_name",
    "open_source",
]
