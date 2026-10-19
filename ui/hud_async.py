"""把 HUD 识别放到单线程 QThreadPool，UI 线程只抓帧/更新。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from core.hud_ocr import HudOcr
from core.hud_brightness import SkillTransitionTracker
from core.hud_pipeline import RecognitionFrame, recognize_frame
from core.hud_profile import HudProfile
from core.operator_match import recognize_operator_auto
from core.operators import Operator, OperatorCatalog

logger = logging.getLogger(__name__)
_OCR_SINGLETON: HudOcr | None = None


def get_hud_ocr() -> HudOcr:
    """OCR 引擎单例：首次由后台 worker 懒加载，绝不在 UI 线程初始化。"""
    global _OCR_SINGLETON
    if _OCR_SINGLETON is None:
        _OCR_SINGLETON = HudOcr()
    return _OCR_SINGLETON


@dataclass
class HudRecognitionResult:
    recognized: RecognitionFrame | None = None
    operator_id: str = ""
    operator_name: str = ""
    operator_score: float = 0.0
    duration_ms: int = 0
    error: str = ""
    debug_path: str = ""


class _TaskSignals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class _HudTask(QRunnable):
    def __init__(
        self,
        token: int,
        signals: _TaskSignals,
        service: "HudRecognitionService",
        frame: Any,
        profile: HudProfile,
        operator: Operator | None,
        catalog: OperatorCatalog,
        threshold: float,
        detect_operator: bool,
        server_now: int = 0,
        debug_export: bool = False,
    ) -> None:
        super().__init__()
        self.token = token
        self.signals = signals
        self.service = service
        self.frame = frame
        self.profile = profile
        self.operator = operator
        self.catalog = catalog
        self.threshold = threshold
        self.detect_operator = detect_operator
        self.server_now = int(server_now)
        self.debug_export = debug_export

    def run(self) -> None:
        if self.token != self.service.token:
            return
        started = time.monotonic()
        try:
            operator = self.operator
            operator_id = ""
            score = 0.0
            if self.detect_operator:
                height, width = int(self.frame.shape[0]), int(self.frame.shape[1])
                search = (
                    0,
                    int(height * 1200 / 1440),
                    int(width * 260 / 2560),
                    int(height * 240 / 1440),
                )
                operator_id, score, _box, top3 = recognize_operator_auto(
                    self.frame,
                    self.catalog,
                    self.threshold,
                    search_region=search,
                )
                logger.info(
                    "干员识别 top3：%s",
                    [
                        {"id": item["operator_id"], "score": round(item["score"], 3), "box": item["box"]}
                        for item in top3
                    ],
                )
                if operator_id:
                    operator = self.catalog.get(operator_id) or operator
                    if operator is not None and operator.id != self.service.tracker_operator:
                        self.service.tracker.reset()
                        self.service.tracker_operator = operator.id
                if self.token != self.service.token:
                    return
            ocr = get_hud_ocr()
            recognized = recognize_frame(
                self.frame,
                self.profile,
                operator=operator,
                ocr=ocr,
                tracker=self.service.tracker,
                server_now=self.server_now,
            )
            if self.token != self.service.token:
                return
            result = HudRecognitionResult(
                recognized=recognized,
                operator_id=operator_id or (operator.id if operator else ""),
                operator_name=operator.display_name if operator else "",
                operator_score=score,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            if self.debug_export:
                from core.hud_debug import HudDebugExporter

                path = HudDebugExporter().export(
                    self.frame,
                    self.profile,
                    recognized,
                    operator_id=result.operator_id,
                    operator_name=result.operator_name,
                    extra={"threshold": self.threshold, "duration_ms": result.duration_ms},
                )
                result.debug_path = str(path) if path is not None else ""
            self.signals.done.emit(self.token, result)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.token, str(exc))


class HudRecognitionService(QObject):
    """同一时间一个识别任务；超时后 token 失效，迟到结果丢弃。"""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._signals = _TaskSignals()
        self._signals.done.connect(self._on_done)
        self._signals.failed.connect(self._on_failed)
        self.token = 0
        self.busy = False
        self.tracker = SkillTransitionTracker()
        self.tracker_operator = ""
        self._callback: Callable[[HudRecognitionResult], None] | None = None

    def reset_tracker(self) -> None:
        self.tracker.reset()
        self.tracker_operator = ""

    @property
    def active(self) -> bool:
        return self.busy

    def submit(
        self,
        frame: Any,
        profile: HudProfile,
        operator: Operator | None,
        catalog: OperatorCatalog,
        threshold: float,
        *,
        detect_operator: bool = True,
        debug_export: bool = False,
        server_now: int = 0,
        callback: Callable[[HudRecognitionResult], None],
    ) -> bool:
        if self.busy:
            return False
        self.busy = True
        self.token += 1
        self._callback = callback
        self._pool.start(
            _HudTask(
                self.token,
                self._signals,
                self,
                frame,
                profile,
                operator,
                catalog,
                threshold,
                detect_operator,
                server_now,
                debug_export,
            )
        )
        return True

    def cancel(self) -> None:
        self.token += 1
        self.busy = False
        self._callback = None

    def _on_done(self, token: int, result: HudRecognitionResult) -> None:
        if token != self.token:
            return
        callback, self._callback = self._callback, None
        self.busy = False
        if callback is not None:
            callback(result)

    def _on_failed(self, token: int, message: str) -> None:
        if token != self.token:
            return
        callback, self._callback = self._callback, None
        self.busy = False
        if callback is not None:
            callback(HudRecognitionResult(error=message))

    def shutdown(self) -> None:
        self.cancel()
        self._pool.clear()
        self._pool.waitForDone(1500)
