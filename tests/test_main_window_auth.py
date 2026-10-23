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

    def test_close_api_closes_http_session(self) -> None:
        class FakeApi:
            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        config = AppConfig(use_mock=True, persist_token=False, server_migrated=False)
        session = Session(persist_token=False)
        window = MainWindow(config, session)
        try:
            fake = FakeApi()
            window.api = fake
            window._close_api()
            self.assertTrue(fake.closed)
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()

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
            window._membership_confirmed = True
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
                self.assertTrue(item["remaining_ms"] is None or isinstance(item["remaining_ms"], int))
        finally:
            window.bridge.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()


    def test_share_on_without_data_sends_nothing(self) -> None:
        class FakeWs:
            connected = True
            def __init__(self): self.sent = []
            async def send_skill_update(self, *args): self.sent.append(args)
            async def send_skill_off(self): self.sent.append("off")
        session = Session(persist_token=False); session.set_login("token", {"id":"12","username":"DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False, server_migrated=False), session)
        try:
            window._current_room = Room(id="1", code="ABC123", name="test")
            window._membership_confirmed = True
            window._self_skill_state = None
            fake = FakeWs(); window._ws = fake
            window._on_skill_sharing_toggled(True)
            for _ in range(50):
                if fake.sent: break
                self.app.processEvents(); time.sleep(0.01)
            self.assertTrue(fake.sent)
            self.assertEqual("idle", fake.sent[0][-1])
            self.assertIn("12", window.room_view.skill_panel._rows)
            self.assertTrue(window.room_view.skill_panel._rows["12"].unrecognized_label.isVisibleTo(window.room_view.skill_panel._rows["12"]))
            self.assertEqual("结束技能共享", window.room_view.skill_panel.share_toggle_button.text())
        finally:
            window.bridge.stop(); window.close(); window.deleteLater(); self.app.processEvents()

    def test_reset_removes_card_sends_off_keeps_share_on(self) -> None:
        class FakeWs:
            connected = True
            def __init__(self): self.off = 0
            async def send_skill_update(self, *args): pass
            async def send_skill_off(self): self.off += 1
        session = Session(persist_token=False); session.set_login("token", {"id":"12","username":"DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False, server_migrated=False), session)
        try:
            window._current_room = Room(id="1", code="ABC123", name="test")
            window._membership_confirmed = True
            window._skill_share_enabled = True
            window.room_view.skill_panel.set_sharing(True)
            window._self_skill_state = SkillState(user_id="12", nickname="DeltaQA01", captured_at=1)
            window._skills.update(window._self_skill_state)
            window.room_view.skill_panel.upsert(window._self_skill_state)
            fake = FakeWs(); window._ws = fake
            window._finish_match()
            self.assertEqual(0, fake.off)
            self.assertIn("12", window.room_view.skill_panel._rows)
            self.assertTrue(window.room_view.skill_panel._rows["12"].unrecognized_label.isVisibleTo(window.room_view.skill_panel._rows["12"]))
            self.assertEqual("结束技能共享", window.room_view.skill_panel.share_toggle_button.text())
        finally:
            window.bridge.stop(); window.close(); window.deleteLater(); self.app.processEvents()

    def test_user_left_clears_skill_card(self) -> None:
        session = Session(persist_token=False); session.set_login("token", {"id":"12","username":"DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False, server_migrated=False), session)
        try:
            window._current_room = Room(id="1", code="ABC123", name="test")
            window._ws_generation = 1
            state = SkillState(user_id="13", nickname="队友", captured_at=1)
            window._skills.update(state); window.room_view.skill_panel.upsert(state)
            window._on_ws_message(1, {"type":"user_left","user":{"id":"13","nickname":"队友"},"reason":"disconnected"})
            self.assertNotIn("13", window.room_view.skill_panel._rows)
            self.assertIsNone(window._skills.get("13"))
        finally:
            window.bridge.stop(); window.close(); window.deleteLater(); self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
