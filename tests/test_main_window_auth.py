"""顶号/401 后 MainWindow 清会话并回登录页。"""

from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from core.models import Room
    from core.skill_payload import validate_payload
    from core.skills import (
        SLOT_ABILITY,
        SLOT_THROWABLE,
        SLOT_ULTIMATE,
        SkillSlot,
        SkillState,
    )
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

    def test_sharing_cached_ready_unknown_payload_is_valid(self) -> None:
        class FakeWs:
            connected = True

            def __init__(self) -> None:
                self.payload = None

            async def send_skill_update(self, *args) -> None:
                self.payload = args[2]

        config = AppConfig(use_mock=True, persist_token=False, server_migrated=False)
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(config, session)
        try:
            window._current_room = Room(id="1", code="ABC123", name="test")
            fake_ws = FakeWs()
            window._ws = fake_ws
            window._self_skill_state = SkillState(
                user_id="12",
                nickname="DeltaQA01",
                captured_at=1_700_000_000_000,
                slots={
                    "ultimate": SkillSlot(SLOT_ULTIMATE, "ready", None),
                    "ability": SkillSlot(SLOT_ABILITY, "unknown", None),
                    "throwable": SkillSlot(SLOT_THROWABLE, "ready", None),
                },
            )
            window._on_skill_sharing_toggled(True)
            for _ in range(100):
                if fake_ws.payload is not None:
                    break
                self.app.processEvents()
                time.sleep(0.01)
            self.assertIsNotNone(fake_ws.payload)
            valid, reason = validate_payload(fake_ws.payload)
            self.assertTrue(valid, reason)
            for item in fake_ws.payload:
                self.assertIsInstance(item["remaining_ms"], int)
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
