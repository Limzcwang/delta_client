"""E4：自动共享循环（QTimer 驱动，采集/识别可注入）。"""

from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from core.hud_pipeline import RecognitionFrame
from core.skill_auto import ChangeTracker


class AutoShareController(QObject):
    """每 sample_interval_ms 抓一帧 -> 识别 -> 变化去抖 -> 发 payload。

    出错/未开共享/不在房间/窗口丢失自动暂停并给出状态；GUI/悬浮窗共享缓存。
    """

    payload_ready = Signal(object)  # list[dict]
    status_changed = Signal(str)
    capture_failed = Signal(str)

    def __init__(
        self,
        frame_source_factory: Callable[[], tuple[Any, str]],
        recognizer: Callable[[Any], RecognitionFrame],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._factory = frame_source_factory
        self._recognizer = recognizer
        self._source = None
        self._tracker = ChangeTracker()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._enabled = False
        self._sharing = False
        self._room_active = False
        self.interval_ms = 2000
        self.last_payload: list[dict[str, Any]] | None = None
        self.frames = 0
        self.emits = 0

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def configure(
        self,
        *,
        enabled: bool | None = None,
        sharing: bool | None = None,
        room_active: bool | None = None,
        interval_ms: int | None = None,
    ) -> None:
        if enabled is not None:
            self._enabled = bool(enabled)
        if sharing is not None:
            self._sharing = bool(sharing)
        if room_active is not None:
            self._room_active = bool(room_active)
        if interval_ms is not None:
            self.interval_ms = max(500, int(interval_ms))
            self._timer.setInterval(self.interval_ms)
        self._sync()

    def start(self) -> None:
        self._timer.setInterval(self.interval_ms)
        self._timer.start()
        self._sync()

    def stop(self) -> None:
        self._timer.stop()
        self._close_source()
        self._tracker.reset()
        self.status_changed.emit("自动共享已停止")

    def reset_tracker(self) -> None:
        self._tracker.reset()

    def _sync(self) -> None:
        if not self._enabled:
            self.status_changed.emit("自动识别未开启")
            if self.running:
                self._timer.stop()
                self._close_source()
            return
        if not self._sharing:
            self.status_changed.emit("技能共享未开启")
            self._timer.stop()
            self._close_source()
            return
        if not self._room_active:
            self.status_changed.emit("不在房间")
            self._timer.stop()
            self._close_source()
            return
        if not self._timer.isActive():
            self._timer.start(self.interval_ms)
        self.status_changed.emit("自动识别运行中")

    def tick(self) -> None:
        if not (self._enabled and self._sharing and self._room_active):
            self._sync()
            return
        if self._source is None:
            source, message = self._factory()
            if source is None:
                self.capture_failed.emit(message)
                self.status_changed.emit(f"自动识别暂停：{message}")
                return
            self._source = source
        try:
            frame = self._source.grab()
        except Exception as exc:  # noqa: BLE001
            frame = None
            self.capture_failed.emit(str(exc))
        if frame is None:
            self.capture_failed.emit("窗口丢失或最小化")
            self.status_changed.emit("自动识别暂停：窗口丢失/最小化")
            self._close_source()
            return
        self.frames += 1
        try:
            recognized = self._recognizer(frame)
            if hasattr(recognized, "payload"):
                payload = recognized.payload()
            else:
                payload = list(recognized)
        except Exception as exc:  # noqa: BLE001
            self.capture_failed.emit(str(exc))
            self.status_changed.emit(f"识别失败：{exc}")
            return
        now = time.monotonic() * 1000
        if self._tracker.should_emit(payload, now):
            self._tracker.mark_sent(payload, now)
            self.last_payload = payload
            self.emits += 1
            self.payload_ready.emit(payload)
            self.status_changed.emit(f"自动识别：已上报（第 {self.emits} 次）")

    def _close_source(self) -> None:
        if self._source is not None:
            try:
                self._source.close()
            except Exception:  # noqa: BLE001
                pass
        self._source = None
