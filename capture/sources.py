"""E3b1：窗口帧采集（WGC 优先，mss 回退）与 2 FPS 工作线程。"""

from __future__ import annotations

import logging
import os
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

logger = logging.getLogger(__name__)

DEFAULT_FPS = 2.0
MIN_FRAME_MEAN = 5.0


@dataclass(frozen=True)
class FrameStats:
    width: int
    height: int
    mean: float
    source: str = ""

    def label(self) -> str:
        return f"{self.width}×{self.height} 均值 {self.mean:.1f}（{self.source}）"


def frame_stats(image: Any, source: str = "") -> FrameStats | None:
    try:
        height, width = int(image.shape[0]), int(image.shape[1])
        try:
            import numpy as np  # type: ignore[import-not-found]

            mean = float(np.asarray(image, dtype=np.float32).mean())
        except ImportError:
            mean = float(image.mean())
        except Exception:
            return None
    except Exception:  # noqa: BLE001
        return None
    return FrameStats(width=width, height=height, mean=mean, source=source)


def validate_frame(image: Any, source: str = "") -> tuple[bool, str, FrameStats | None]:
    stats = frame_stats(image, source)
    if stats is None:
        return False, "帧格式无效（无法读取宽高/像素）", None
    if stats.width <= 0 or stats.height <= 0:
        return False, f"帧尺寸无效：{stats.width}×{stats.height}", stats
    if stats.mean < MIN_FRAME_MEAN:
        return False, f"画面全黑/无内容：{stats.label()}", stats
    return True, "", stats


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
        self.last_error = ""

    def grab(self) -> Frame | None:
        self.last_error = ""
        try:
            if self.window.is_minimized:
                self.last_error = "游戏窗口已最小化"
                return None
            if self._mss is None:
                import mss  # type: ignore[import-not-found]

                self._mss = mss
                self._sct = mss.mss()
            left = int(self.window.client_left)
            top = int(self.window.client_top)
            width = int(self.window.client_width)
            height = int(self.window.client_height)
            import numpy as np  # type: ignore[import-not-found]

            monitor = self._sct.monitors[0]
            outside = (
                left < monitor["left"]
                or top < monitor["top"]
                or left + width > monitor["left"] + monitor["width"]
                or top + height > monitor["top"] + monitor["height"]
            )
            if outside:
                shot = self._sct.grab(monitor)
                image = np.asarray(shot, dtype=np.uint8)[:, :, :3]
                x0 = max(0, left - monitor["left"])
                y0 = max(0, top - monitor["top"])
                image = image[y0 : y0 + height, x0 : x0 + width]
            else:
                shot = self._sct.grab(
                    {"left": left, "top": top, "width": width, "height": height}
                )
                image = np.asarray(shot, dtype=np.uint8)[:, :, :3]  # BGRA -> BGR
            valid, reason, stats = validate_frame(image, "mss")
            if not valid:
                self.last_error = reason
                logger.warning("mss 帧无效：%s", reason)
                return None
            return Frame(image=image, timestamp=time.time(), source="mss")
        except Exception as exc:  # noqa: BLE001 - 记录异常并让上层显示原因
            self.last_error = f"mss 异常 {type(exc).__name__}: {exc}"
            logger.warning("mss 抓帧异常：%s", exc, exc_info=True)
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
        self.last_error = ""
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
                valid, reason, _stats = validate_frame(image, "wgc")
                if not valid:
                    self.last_error = reason
                    logger.warning("WGC 帧无效：%s", reason)
                    return
                with self._condition:
                    self._latest = Frame(image=image, timestamp=time.time(), source="wgc")
                    self._condition.notify_all()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"WGC 帧处理异常 {type(exc).__name__}: {exc}"
                logger.warning("WGC 帧处理异常：%s", exc)
                return

        @capture.event
        def on_closed() -> None:
            self._closed = True
            with self._condition:
                self._condition.notify_all()

        self._control = capture.start_free_threaded()

    def grab(self) -> Frame | None:
        self.last_error = ""
        if self.window.is_minimized:
            self.last_error = "游戏窗口已最小化"
            return None
        with self._condition:
            if self._latest is None and not self._closed:
                self._condition.wait(timeout=self.timeout)
            frame = self._latest
            self._latest = None
            if frame is None and not self.last_error:
                self.last_error = "WGC 未收到帧"
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
    prefer_wgc: bool | None = None,
) -> tuple[FrameSource | None, str]:
    """默认 mss；仅显式 DELTA_CAPTURE_WGC=1 时先试 WGC（无边框窗口 WGC 常失败）。"""
    if window is None:
        keywords = (title_keyword,) if title_keyword else DEFAULT_TITLE_KEYWORDS
        result = find_game_window(process_name or DEFAULT_PROCESS_NAME, title_keywords=keywords)
        window = result.window
        if window is None:
            return None, result.reason
    if window.is_minimized:
        return None, "游戏窗口已最小化"
    if prefer_wgc is None:
        prefer_wgc = os.environ.get("DELTA_CAPTURE_WGC", "").strip().lower() in ("1", "true", "yes")
    if prefer_wgc:
        try:
            return WgcSource(window), "wgc"
        except Exception as exc:  # noqa: BLE001 - WGC 仅独占全屏可用
            logger.warning("WGC 采集失败，回退 mss：%s", exc)
    try:
        return MssSource(window), "mss"
    except Exception as exc:  # noqa: BLE001
        return None, f"mss 不可用: {exc}"


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
        self.last_error = ""

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
                    self.last_error = "游戏窗口已最小化"
                else:
                    frame = self.source.grab()
                    if frame is None:
                        self.last_error = getattr(self.source, "last_error", "") or "未取到有效画面"
                if frame is not None:
                    self.frames += 1
                    self.last_error = ""
                    self.on_frame(frame)
            except Exception as exc:  # noqa: BLE001
                self.errors += 1
                if self.on_error:
                    self.on_error(str(exc))
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.01, self.interval - elapsed))
