"""P4：房间三栏、复制房间号、画板/技能 Tab 宽度稳定。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from core.models import Member, Room
    from ui.room_view import RoomView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False

MAP_RATIO = 1105 / 1260


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class RoomRedesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.view = RoomView()
        self.view.resize(1120, 720)
        room = Room.from_api({"id": "r1", "code": "AB12C", "name": "零号大坝", "owner_id": "11"})
        self.view.set_room(room)
        self.view.set_user("DeltaQA01", "12")
        self.view.set_connection_state("connected")
        self.view.set_members([
            Member.from_api({"id": "11", "nickname": "房主", "online": True}),
            Member.from_api({"id": "12", "nickname": "DeltaQA01", "online": True}),
        ])
        self.view.show()
        self.app.processEvents()
        self.view._sync_canvas_width()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()
        self.app.processEvents()

    def test_three_columns_and_canvas_aspect(self) -> None:
        self.assertEqual(230, self.view.members_panel.width())
        self.assertGreaterEqual(self.view.chat_panel.width(), 300)
        self.assertGreater(self.view.side_tabs.width(), 0)
        surface = self.view.canvas.surface
        self.assertAlmostEqual(MAP_RATIO, surface.width() / surface.height(), places=2)
        self.assertGreater(surface.width(), 300)

    def test_tab_switch_keeps_column_width(self) -> None:
        before = self.view.side_tabs.width()
        self.view.side_tabs.setCurrentWidget(self.view.skill_panel)
        self.app.processEvents()
        self.assertEqual(before, self.view.side_tabs.width())
        self.assertIs(self.view.side_tabs.currentWidget(), self.view.skill_panel)
        self.assertEqual(2, self.view.side_tabs.count())

    def test_copy_room_code_and_header(self) -> None:
        self.assertIn("房间号 AB12C", self.view.room_code.text())
        self.view.copy_button.click()
        self.assertIn("已复制房间号 AB12C", self.view.status_label.text())
        self.assertIn("房主：房主", self.view.owner_label.text())
        self.assertIn("已连接", self.view.connection_badge.text())

    def test_skill_settings_signal(self) -> None:
        seen: list[bool] = []
        self.view.skill_settings_requested.connect(lambda: seen.append(True))
        self.view.skill_panel.settings_button.click()
        self.assertEqual([True], seen)

    def test_canvas_column_matches_height_and_no_gutter(self) -> None:
        self.view._sync_canvas_width()
        self.app.processEvents()
        host = self.view.canvas.host
        ratio = self.view.canvas.surface.map_size[0] / self.view.canvas.surface.map_size[1]
        self.assertEqual(round(host.height() * ratio) + 24, self.view.side_tabs.width())
        total = self.view.members_panel.width() + self.view.chat_panel.width() + self.view.side_tabs.width()
        self.assertEqual(self.view.width() - 44 - 24, total)

    def test_fullscreen_removes_780_cap(self) -> None:
        self.view.resize(1870, 1150)
        self.app.processEvents()
        self.view._sync_canvas_width()
        self.app.processEvents()
        self.assertGreater(self.view.side_tabs.width(), 780)
        self.assertGreaterEqual(self.view.chat_panel.width(), 300)
        self.assertAlmostEqual(MAP_RATIO, self.view.canvas.surface.width() / self.view.canvas.surface.height(), places=2)
        total = self.view.members_panel.width() + self.view.chat_panel.width() + self.view.side_tabs.width()
        self.assertEqual(self.view.width() - 44 - 24, total)

    def test_five_canvas_tools(self) -> None:
        self.assertEqual(5, len(self.view.canvas.tool_buttons))
        self.assertFalse(self.view.canvas.color_button.isVisible())


if __name__ == "__main__":
    unittest.main()

