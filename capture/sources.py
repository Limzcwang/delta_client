"""E3b1：窗口帧采集（WGC 优先，mss 回退）与 2 FPS 工作线程。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from capture.window import (
    DEFAULT_PROCESS_NAME,
    DEFAULT_TITLE_KEYWORDS,
    WindowInfo,
    find_game_window,
)

DEFAULT_FPS = 2.0


@dataclass
class Frame:
    image: Any  # numpy BGR 数组
    timestamp: float
    source: str = ""

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class FrameSource(Protocol):
    def grab(self) -> Frame | None: ...
    def close(self) -> None: ...


class MssSource:
    """mss 回退：抓窗口客户区矩形（要求窗口可见，不处理遮挡）。"""

    def __init__(self, window: WindowInfo) -> None:
        self.window = window
        self._sct = None
        self._mss = None

    def grab(self) -> Frame | None:
        try:
            if self._mss is None:
                import mss  # type: ignore[import-not-found]

                self._mss = mss
                self._sct = mss.mss()
            if self.window.is_minimized:
                return None
            shot = self._sct.grab(
                {
                    "left": self.window.client_left,
                    "top": self.window.client_top,
                    "width": self.window.client_width,
                    "height": self.window.client_height,
                }
            )
            import numpy as np  # type: ignore[import-not-found]

            image = np.asarray(shot, dtype=np.uint8)[:, :, :3]  # BGRA -> BGR
            return Frame(image=image, timestamp=time.time(), source="mss")
        except Exception:  # noqa: BLE001 - 采集失败返回 None，由上层回退/暂停
            return None

    def close(self) -> None:
        try:
            if self._sct is not None:
                self._sct.close()
        except Exception:  # noqa: BLE001
            pass
        self._sct = None


class WgcSource:
    """windows-capture WGC 后端：支持无边框/独占全屏（窗口未最小化时）。"""

    def __init__(self, window: WindowInfo, timeout: float = 0.4) -> None:
        self.window = window
        self.timeout = timeout
        self._latest: Frame | None = None
        self._condition = threading.Condition()
        self._control = None
        self._capture = None
        self._closed = False
        self._start()

    def _start(self) -> None:
        from windows_capture import WindowsCapture  # type: ignore[import-not-found]

        capture = WindowsCapture(
            window_hwnd=self.window.hwnd,
            cursor_capture=False,
            draw_border=False,
        )
        self._capture = capture

        @capture.event
        def on_frame_arrived(frame, _control) -> None:  # noqa: ANN001
            try:
                image = frame.frame_buffer[:, :, :3].copy()
                with self._condition:
                    self._latest = Frame(image=image, timestamp=time.time(), source="wgc")
                    self._condition.notify_all()
            except Exception:  # noqa: BLE001
                return

        @capture.event
        def on_closed() -> None:
            self._closed = True
            with self._condition:
                self._condition.notify_all()

        self._control = capture.start_free_threaded()

    def grab(self) -> Frame | None:
        if self.window.is_minimized:
            return None
        with self._condition:
            if self._latest is None and not self._closed:
                self._condition.wait(timeout=self.timeout)
            frame = self._latest
            self._latest = None
            return frame

    def close(self) -> None:
        self._closed = True
        try:
            if self._control is not None:
                self._control.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._control is not None:
                self._control.wait()
        except Exception:  # noqa: BLE001
            pass


def open_source(
    window: WindowInfo | None = None,
    process_name: str = "",
    *,
    title_keyword: str = "",
) -> tuple[FrameSource | None, str]:
    """优先 WGC，失败回退 mss；返回 (source, error/status)。"""
    if window is None:
        keywords = (title_keyword,) if title_keyword else DEFAULT_TITLE_KEYWORDS
        result = find_game_window(process_name or DEFAULT_PROCESS_NAME, title_keywords=keywords)
        window = result.window
        if window is None:
            return None, result.reason
    if window.is_minimized:
        return None, "游戏窗口已最小化"
    try:
        return WgcSource(window), "wgc"
    except Exception as exc:  # noqa: BLE001 - WGC 不可用时回退
        wgc_error = str(exc)
    try:
        return MssSource(window), f"mss (WGC 不可用: {wgc_error})"
    except Exception as exc:  # noqa: BLE001
        return None, f"WGC/mss 均不可用: {wgc_error}; {exc}"


class CaptureWorker:
    """独立线程 2 FPS 采集；最小化暂停，可停止；不阻塞 Qt 主线程。"""

    def __init__(
        self,
        source: FrameSource,
        on_frame: Callable[[Frame], None],
        on_error: Callable[[str], None] | None = None,
        fps: float = DEFAULT_FPS,
    ) -> None:
        self.source = source
        self.on_frame = on_frame
        self.on_error = on_error
        self.interval = 1.0 / max(0.1, float(fps))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.frames = 0
        self.errors = 0
        self.paused = False

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="delta-hud-capture", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.paused = getattr(getattr(self.source, "window", None), "is_minimized", False)
                if self.paused:
                    frame = None
                else:
                    frame = self.source.grab()
                if frame is not None:
                    self.frames += 1
                    self.on_frame(frame)
            except Exception as exc:  # noqa: BLE001
                self.errors += 1
                if self.on_error:
                    self.on_error(str(exc))
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.01, self.interval - elapsed))
