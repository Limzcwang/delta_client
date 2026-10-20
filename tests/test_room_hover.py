"""P6：房间列表 hover 不变色，选中态保留。"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication
    from core.models import Room
    from ui.room_list_view import RoomListView
    from ui.theme import APP_STYLESHEET
    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


class RoomHoverStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_stylesheet_has_no_table_hover(self) -> None:
        self.assertNotIn("QTableWidget::item:hover", APP_STYLESHEET)

    def test_qml_lobby_has_no_hover_bindings(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "ui_qml" / "pages" / "LobbyPage.qml").read_text(encoding="utf-8")
        self.assertNotIn("hoverEnabled", source)
        self.assertNotIn("containsMouse", source)
        self.assertNotIn("HoverHandler", source)

    @unittest.skipUnless(HAS_QT, "PySide6 未安装")
    def test_selected_row_still_selectable(self) -> None:
        view = RoomListView()
        try:
            view.resize(1120, 720)
            rooms = [Room.from_api({"id": f"r{i}", "code": f"R{i}", "name": f"房间 {i}"}) for i in range(3)]
            view.update_rooms(rooms)
            view.show()
            self.app.processEvents()
            view.table.selectRow(1)
            self.app.processEvents()
            self.assertEqual(1, view.table.currentRow())
            self.assertEqual("R1", view.selected_code())
        finally:
            view.close()
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
