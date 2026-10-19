"""单实例锁测试（Qt 本地 socket）。"""

from __future__ import annotations

import os
import unittest
import uuid

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from ui.single_instance import SingleInstance

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class SingleInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_second_instance_rejected(self) -> None:
        name = f"DeltaClientTest-{uuid.uuid4().hex}"
        first = SingleInstance(name)
        second = SingleInstance(name)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            self.assertFalse(second.activate_existing())
        finally:
            second.release()
            first.release()

    def test_release_allows_new_lock(self) -> None:
        name = f"DeltaClientTest-{uuid.uuid4().hex}"
        first = SingleInstance(name)
        self.assertTrue(first.acquire())
        first.release()
        second = SingleInstance(name)
        try:
            self.assertTrue(second.acquire())
        finally:
            second.release()


if __name__ == "__main__":
    unittest.main()

