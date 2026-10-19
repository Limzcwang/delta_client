"""E3b 窗口截图采集层（WGC/mss）。"""

from capture.sources import CaptureWorker, Frame, FrameSource, MssSource, WgcSource, open_source
from capture.window import DEFAULT_PROCESS_NAME, WindowInfo, find_window_by_process

__all__ = [
    "CaptureWorker",
    "DEFAULT_PROCESS_NAME",
    "Frame",
    "FrameSource",
    "MssSource",
    "WgcSource",
    "WindowInfo",
    "find_window_by_process",
    "open_source",
]
