"""登录页历史账号下拉（0.1.4）：箭头/弹层/行高/键盘/删除/清空。"""

from __future__ import annotations

import unittest

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox

    from state.saved_logins import SavedLoginInfo
    from ui.login_history import ROW_HEIGHT
    from ui.login_view import LoginView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


def _entry(username: str, *, has_password: bool = True, expired: bool = False) -> SavedLoginInfo:
    return SavedLoginInfo(
        username=username,
        saved_at=1_700_000_000.0,
        expires_at=1_800_000_000.0,
        last_used_at=1_700_000_000.0,
        has_password=has_password,
        expired=expired,
    )


@unittest.skipUnless(HAS_QT, "PySide6 未安装")
class LoginHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.view = LoginView()
        self.view.set_saved_logins([_entry("alpha"), _entry("beta")])

    def tearDown(self) -> None:
        self.view.close()
        self.view.deleteLater()

    def test_arrow_visibility_by_history_and_mode(self) -> None:
        self.assertFalse(self.view.history_button.isHidden())
        self.view.set_saved_logins([])
        self.assertTrue(self.view.history_button.isHidden())
        self.view.set_saved_logins([_entry("alpha")])
        self.view.set_mode("register")
        self.assertTrue(self.view.history_button.isHidden())
        self.view.set_mode("login")
        self.assertFalse(self.view.history_button.isHidden())

    def test_popup_rows_height_and_long_account_elide(self) -> None:
        long_name = "account_" + "x" * 80
        self.view.set_saved_logins([_entry(long_name)])
        self.view._toggle_history()
        popup = self.view.history_popup
        self.assertIsNotNone(popup)
        self.assertEqual(1, popup.list.count())
        item = popup.list.item(0)
        self.assertGreaterEqual(item.sizeHint().height(), ROW_HEIGHT)
        row = popup.list.itemWidget(item)
        self.assertGreaterEqual(row.minimumHeight(), 38)
        self.assertEqual(long_name, row.account_label.full_text)
        self.assertEqual(long_name, row.account_label.toolTip())
        row.account_label.resize(90, 30)
        row.account_label._update_elide()
        self.assertLess(len(row.account_label.text()), len(long_name))
        self.assertIn("…", row.account_label.text())

    def test_popup_width_and_esc_close(self) -> None:
        self.view._toggle_history()
        popup = self.view.history_popup
        self.assertTrue(popup.isVisible())
        self.assertGreaterEqual(popup.width(), min(420, max(360, self.view.username_edit.width())))
        QTest.keyClick(popup.list, Qt.Key.Key_Escape)
        self.assertFalse(popup.isVisible())

    def test_click_and_keyboard_select_fills_account_and_password(self) -> None:
        selected: list[str] = []
        self.view.saved_login_selected.connect(selected.append)
        self.view.saved_login_selected.connect(lambda name: self.view.apply_saved_login(name, "pw-" + name))
        self.view._toggle_history()
        popup = self.view.history_popup
        QTest.keyClick(popup.list, Qt.Key.Key_Down)
        QTest.keyClick(popup.list, Qt.Key.Key_Return)
        self.assertEqual(["beta"], selected)
        self.assertFalse(popup.isVisible())
        self.assertEqual("beta", self.view.username_edit.text())
        self.assertEqual("pw-beta", self.view.password_edit.text())

    def test_click_row_selects_account(self) -> None:
        selected: list[str] = []
        self.view.saved_login_selected.connect(selected.append)
        self.view._toggle_history()
        popup = self.view.history_popup
        item = popup.list.item(0)
        popup._on_clicked(item)
        self.assertEqual(["alpha"], selected)
        self.assertFalse(popup.isVisible())

    def test_delete_single_entry(self) -> None:
        deleted: list[str] = []
        self.view.saved_login_delete_requested.connect(deleted.append)
        self.view._toggle_history()
        popup = self.view.history_popup
        row = popup.list.itemWidget(popup.list.item(0))
        row.delete_button.click()
        self.assertEqual(["alpha"], deleted)
        self.assertEqual(1, popup.list.count())

    def test_clear_confirmation(self) -> None:
        from unittest.mock import patch

        cleared: list[bool] = []
        self.view.saved_login_clear_requested.connect(lambda: cleared.append(True))
        self.view._toggle_history()
        popup = self.view.history_popup
        with patch(
            "ui.login_view.QMessageBox.question", return_value=QMessageBox.StandardButton.No
        ) as question:
            popup.clear_button.click()
            self.assertTrue(question.called)
        self.assertEqual([], cleared)
        self.view._toggle_history()
        popup = self.view.history_popup
        with patch(
            "ui.login_view.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes
        ) as question:
            popup.clear_button.click()
            self.assertTrue(question.called)
        self.assertEqual([True], cleared)

    def test_max_five_rows_and_scroll(self) -> None:
        self.view.set_saved_logins([_entry(f"user{i}") for i in range(7)])
        self.view._toggle_history()
        popup = self.view.history_popup
        self.assertGreaterEqual(popup.list.count(), 5)
        self.assertLessEqual(popup.list.height(), 5 * ROW_HEIGHT + 2)


if __name__ == "__main__":
    unittest.main()
