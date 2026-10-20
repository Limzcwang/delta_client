"""房间布局：画板优先扩张、聊天/成员最大宽度、小窗口不溢出。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from ui.room_view import RoomView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False

MAP_RATIO = 1105 / 1260


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class RoomLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.view = RoomView()
        self.view.resize(1920, 1080)
        self.view.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def test_wide_window_canvas_priority(self) -> None:
        self.assertEqual(230, self.view.members_panel.width())
        self.assertGreaterEqual(self.view.chat_panel.width(), 300)
        self.assertGreater(self.view.side_tabs.width(), 0)
        surface = self.view.canvas.surface
        self.assertAlmostEqual(MAP_RATIO, surface.width() / surface.height(), places=2)

    def test_skill_tab_does_not_change_column_width(self) -> None:
        canvas_width = self.view.side_tabs.width()
        self.view.side_tabs.setCurrentWidget(self.view.skill_panel)
        self.app.processEvents()
        self.assertEqual(canvas_width, self.view.side_tabs.width())
        self.assertGreaterEqual(self.view.skill_panel.width(), canvas_width - 10)

    def test_small_window_no_overflow(self) -> None:
        self.view.resize(1120, 720)
        self.app.processEvents()
        self.assertEqual(230, self.view.members_panel.width())
        self.assertGreaterEqual(self.view.chat_panel.width(), 300)
        total = self.view.members_panel.width() + self.view.chat_panel.width() + self.view.side_tabs.width() + 24
        self.assertLessEqual(total, self.view.width())
        surface = self.view.canvas.surface
        self.assertAlmostEqual(MAP_RATIO, surface.width() / surface.height(), places=2)


if __name__ == "__main__":
    unittest.main()
