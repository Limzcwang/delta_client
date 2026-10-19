"""崩溃日志：未捕获异常/最后步骤/正常退出清理。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from state import crash_logging


class CrashLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        crash_logging.install_crash_logging(
            "0.1.3-test",
            path=cls.root / "crash.log",
            step_path=cls.root / "last_step.json",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        crash_logging.shutdown_crash_logging()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        crash_logging.set_current_step("hud_capture")

    def test_uncaught_exception_writes_crash_log(self) -> None:
        try:
            raise ValueError("boom-crash-test")
        except ValueError:
            exc_type, exc, tb = sys.exc_info()
            crash_logging._exception_hook(exc_type, exc, tb)
        text = (self.root / "crash.log").read_text(encoding="utf-8")
        self.assertIn("UNCAUGHT ValueError", text)
        self.assertIn("boom-crash-test", text)
        self.assertIn("version=0.1.3-test", text)
        self.assertIn("thread=", text)

    def test_qt_message_handler_writes(self) -> None:
        from types import SimpleNamespace

        crash_logging._qt_message_handler(SimpleNamespace(name="Warning"), None, "qt-test-message")
        text = (self.root / "crash.log").read_text(encoding="utf-8")
        self.assertIn("QT Warning", text)
        self.assertIn("qt-test-message", text)
        self.assertIn("step=hud_capture", text)

    def test_last_step_and_clear(self) -> None:
        info = crash_logging.read_previous_step()
        self.assertIsNotNone(info)
        self.assertEqual("hud_capture", info["step"])
        crash_logging.clear_current_step()
        self.assertIsNone(crash_logging.read_previous_step())

    def test_zz_normal_shutdown_does_not_leave_marker(self) -> None:
        crash_logging.set_current_step("overlay_attach")
        crash_logging.shutdown_crash_logging()
        self.assertIsNone(crash_logging.read_previous_step())


if __name__ == "__main__":
    unittest.main()

