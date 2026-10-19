"""HUD 异步识别服务：不阻塞 UI、单任务、超时取消。"""

from __future__ import annotations

import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from core.hud_profile import HudProfile
    from core.operators import OperatorCatalog
    from ui.hud_async import HudRecognitionService, get_hud_ocr

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class HudAsyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _wait(self, predicate, timeout_ms=3000) -> bool:
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: loop.quit() if predicate() else None)
        timer.start()
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        timer.stop()
        return bool(predicate())

    def test_submit_returns_immediately_and_callback(self) -> None:
        service = HudRecognitionService()
        results = []

        def slow_recognize(*args, **kwargs):
            time.sleep(0.2)
            return SimpleNamespace(payload=lambda: [])

        with mock.patch("ui.hud_async.recognize_operator", return_value=("", 0.0)), mock.patch(
            "ui.hud_async.recognize_frame", side_effect=slow_recognize
        ):
            started = time.monotonic()
            accepted = service.submit(
                object(), HudProfile(), None, OperatorCatalog(), 0.7,
                detect_operator=False, callback=results.append,
            )
            elapsed = time.monotonic() - started
        self.assertTrue(accepted)
        self.assertLess(elapsed, 0.05)
        self.assertTrue(self._wait(lambda: bool(results)))
        self.assertFalse(results[0].error)
        service.shutdown()

    def test_second_submit_ignored_while_busy(self) -> None:
        service = HudRecognitionService()
        results = []
        with mock.patch("ui.hud_async.recognize_operator", return_value=("", 0.0)), mock.patch(
            "ui.hud_async.recognize_frame", side_effect=lambda *a, **k: (time.sleep(0.2), SimpleNamespace(payload=lambda: []))[1]
        ):
            first = service.submit(object(), HudProfile(), None, OperatorCatalog(), 0.7, detect_operator=False, callback=results.append)
            second = service.submit(object(), HudProfile(), None, OperatorCatalog(), 0.7, detect_operator=False, callback=results.append)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(self._wait(lambda: bool(results)))
        service.shutdown()

    def test_cancel_drops_late_result(self) -> None:
        service = HudRecognitionService()
        results = []
        with mock.patch("ui.hud_async.recognize_operator", return_value=("", 0.0)), mock.patch(
            "ui.hud_async.recognize_frame", side_effect=lambda *a, **k: (time.sleep(0.2), SimpleNamespace(payload=lambda: []))[1]
        ):
            service.submit(object(), HudProfile(), None, OperatorCatalog(), 0.7, detect_operator=False, callback=results.append)
            service.cancel()
            time.sleep(0.5)
            self.app.processEvents()
        self.assertEqual([], results)
        self.assertFalse(service.active)
        service.shutdown()

    def test_ocr_singleton(self) -> None:
        self.assertIs(get_hud_ocr(), get_hud_ocr())


if __name__ == "__main__":
    unittest.main()

