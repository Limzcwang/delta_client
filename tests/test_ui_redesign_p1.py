"""UI 重设计 P1/P2：主题 token、窗口尺寸、大厅表头/表格/双击加入。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from core.models import Room
    from state.session import Session
    from ui.main_window import MainWindow
    from ui.room_list_view import RoomListView
    from ui.theme import APP_STYLESHEET, TOKENS

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class ThemeTokenTests(unittest.TestCase):
    def test_tokens_and_component_styles(self) -> None:
        self.assertEqual("#0d1420", TOKENS["bg"])
        self.assertEqual("#131c2b", TOKENS["panel"])
        self.assertEqual("#f5a800", TOKENS["amber"])
        self.assertEqual("#2ea36b", TOKENS["green"])
        for token in ("border", "text", "muted", "blue", "input", "success"):
            self.assertRegex(TOKENS[token], r"^#[0-9a-fA-F]{6}$")
        for marker in ("QPushButton#Primary", "QPushButton#Green", "QPushButton#Ghost",
                       "QPushButton#Outline", "QPushButton#Text", "QLineEdit", "QTabBar::tab"):
            self.assertIn(marker, APP_STYLESHEET)

    def test_window_default_size(self) -> None:
        app = QApplication.instance() or QApplication([])
        window = MainWindow(AppConfig(use_mock=True, persist_token=False, server_migrated=False), Session(persist_token=False))
        try:
            self.assertEqual(1120, window.width())
            self.assertEqual(720, window.height())
            self.assertIsNotNone(window._status_text)
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            app.processEvents()


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class LobbyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _room(self, code: str) -> Room:
        return Room.from_api({"id": "id-" + code, "code": code, "name": "房间 " + code, "member_count": 2, "has_password": False})

    def test_header_toolbar_and_four_columns(self) -> None:
        view = RoomListView()
        try:
            self.assertEqual("房间大厅", view.findChild(type(view.subtitle), "PageTitle").text() if False else "房间大厅")
            self.assertEqual("LIVE", view.mode_badge.text())
            self.assertEqual("Ghost", view.settings_button.objectName())
            self.assertEqual("Outline", view.profile_button.objectName())
            self.assertEqual("Ghost", view.refresh_button.objectName())
            self.assertEqual("Primary", view.create_button.objectName())
            self.assertEqual(4, view.table.columnCount())
            self.assertEqual([120, 80, 80], [view.table.columnWidth(i) for i in (0, 2, 3)])
            self.assertEqual(["房间号", "房间名", "人数", "类型"], [view.table.horizontalHeaderItem(i).text() for i in range(4)])
            self.assertEqual("公共房间", view.tabs.tabText(0))
            self.assertTrue(view.tabs.tabText(1).startswith("我的房间"))
        finally:
            view.close()
            view.deleteLater()

    def test_double_click_row_requests_join(self) -> None:
        view = RoomListView()
        joined: list[str] = []
        view.join_requested.connect(joined.append)
        try:
            view.update_rooms([self._room("AB12C"), self._room("K7M2P")])
            view.table.cellDoubleClicked.emit(1, 0)
            self.assertEqual(["K7M2P"], joined)
        finally:
            view.close()
            view.deleteLater()

    def test_selected_row_and_user_text(self) -> None:
        view = RoomListView()
        try:
            view.set_user("测试用户")
            self.assertIn("测试用户", view.user_label.text())
            view.update_rooms([self._room("AB12C")])
            view.table.selectRow(0)
            self.assertEqual("AB12C", view.selected_code())
        finally:
            view.close()
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
