"""P3：连接设置/个人资料独立页、600px 居中、修改密码折叠、保存回写。"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from state.session import Session
    from ui.main_window import MainWindow
    from ui.settings_pages import ConnectionPage, ProfilePage

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class SettingsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_connection_page_layout_and_validation(self) -> None:
        page = ConnectionPage(AppConfig(use_mock=True, persist_token=False))
        try:
            self.assertEqual("连接设置", page.title_label.text())
            self.assertEqual(600, page.form.width())
            self.assertEqual("https://deltachat.icu:8443", page.server_edit.text())
            self.assertTrue(page.mock_check.isChecked())
            page.server_edit.setText("")
            page.save_button.click()
            self.assertFalse(page.error_label.isHidden())
            page.server_edit.setText("https://example.com:8443")
            page.ws_edit.clear()
            config = page.result_config()
            self.assertEqual("https://example.com:8443", config.server_url)
            self.assertIsNone(config.ws_url)
        finally:
            page.close()
            page.deleteLater()

    def test_profile_password_fold_and_unfold(self) -> None:
        page = ProfilePage(account="DeltaQA01", nickname="QA")
        try:
            self.assertTrue(page.password_section.isHidden())
            self.assertFalse(page.password_reveal_button.isHidden())
            page.password_reveal_button.click()
            self.assertFalse(page.password_section.isHidden())
            self.assertTrue(page.password_reveal_button.isHidden())
            page.password_cancel_button.click()
            self.assertTrue(page.password_section.isHidden())
            self.assertFalse(page.password_reveal_button.isHidden())
            self.assertEqual("DeltaQA01", page.account_label.text().split("：", 1)[1].split("（", 1)[0])
        finally:
            page.close()
            page.deleteLater()

    def test_profile_bottom_buttons_signals(self) -> None:
        page = ProfilePage()
        seen: list[str] = []
        page.logout_requested.connect(lambda: seen.append("logout"))
        page.back_requested.connect(lambda: seen.append("back"))
        try:
            page.logout_button.click()
            page.cancel_button.click()
            self.assertEqual(["logout", "back"], seen)
        finally:
            page.close()
            page.deleteLater()

    def test_window_navigation_and_connection_save(self) -> None:
        config = AppConfig(use_mock=True, persist_token=False, server_migrated=False)
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01", "nickname": "QA"})
        window = MainWindow(config, session)
        try:
            window._show_connection_page()
            self.assertIs(window.stack.currentWidget(), window.connection_page)
            page = window.connection_page
            page.server_edit.setText("https://example.com:8443")
            window._close_api = lambda timeout=2.0: None
            with mock.patch("ui.main_window.save_config") as save:
                page.save_button.click()
            self.assertTrue(save.called)
            self.assertEqual("https://example.com:8443", window.config.server_url)
            self.assertIsNot(window.stack.currentWidget(), page)
            window._show_profile_page()
            self.assertIs(window.stack.currentWidget(), window.profile_page)
            window.profile_page.back_button.click()
            self.assertIsNot(window.stack.currentWidget(), window.profile_page)
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()

