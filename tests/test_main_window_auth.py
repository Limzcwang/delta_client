"""顶号/401 后 MainWindow 清会话并回登录页。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from state.session import Session
    from ui.main_window import MainWindow

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class WsFatalSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_auth_failure_clears_session_and_returns_login(self) -> None:
        config = AppConfig(use_mock=True, persist_token=False, server_migrated=False)
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(config, session)
        try:
            self.assertTrue(session.is_logged_in)
            window._handle_ws_fatal("登录已失效，请重新登录")
            self.assertFalse(session.is_logged_in)
            self.assertIs(window.stack.currentWidget(), window.login_view)
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
