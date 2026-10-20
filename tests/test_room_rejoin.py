"""B2：WS 重连后自动 join_room、membership 确认前禁发、错误去重。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from core.models import Room
    from core.skills import SkillState
    from state.session import Session
    from ui.main_window import MainWindow

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


class _DummyCoro:
    def close(self) -> None:
        pass


class _FakeApi:
    def __init__(self) -> None:
        self.joins: list[tuple[str, str | None]] = []

    def join_room(self, code, password=None):
        self.joins.append((code, password))
        return _DummyCoro()

    def get_canvas(self, code):
        return _DummyCoro()


class _FakeWs:
    connected = True

    def __init__(self) -> None:
        self.joins: list[tuple[str, str | None]] = []
        self.skill_sends = 0
        self.canvas_sends = 0

    def join_room(self, code, password=None):
        self.joins.append((code, password))
        return _DummyCoro()

    async def send_skill_update(self, *args):
        self.skill_sends += 1
        return True

    async def send_skill_off(self, *args):
        return True

    def send_canvas_op(self, op, rev, room_id):
        self.canvas_sends += 1
        return _DummyCoro()


@unittest.skipUnless(HAS_QT, "PySide6 未安装")
class RejoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False), session)
        window._current_room = Room(id="1", code="ABC123", name="test")
        window._room_password = None
        window._ws_generation = 1
        window._safe_submit = lambda coro, on_success=None, on_error=None: (
            coro.close() if hasattr(coro, "close") else None
        )
        return window

    def _close(self, window) -> None:
        window.bridge.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_canvas_queue_waits_for_membership_and_drains(self) -> None:
        window = self._window()
        fake = _FakeWs()
        try:
            window._ws = fake
            window._membership_confirmed = False
            window._canvas_queue.append({"op": "clear", "rev": 0})
            window._drain_canvas_queue()
            self.assertEqual(0, fake.canvas_sends)
            self.assertEqual(1, len(window._canvas_queue))
            window._membership_confirmed = True
            window._drain_canvas_queue()
            self.assertEqual(1, fake.canvas_sends)
            self.assertEqual([], window._canvas_queue)
        finally:
            self._close(window)

    def test_connected_triggers_join_room(self) -> None:
        window = self._window()
        fake = _FakeWs()
        try:
            window._ws = fake
            window._membership_confirmed = False
            window._on_ws_state(1, "connected", {})
            self.assertEqual([("ABC123", None)], fake.joins)
            self.assertFalse(window._membership_confirmed)
        finally:
            self._close(window)

    def test_send_blocked_before_membership(self) -> None:
        window = self._window()
        fake = _FakeWs()
        try:
            window._ws = fake
            window._membership_confirmed = False
            window._send_skill_state(SkillState(user_id="12", nickname="x"))
            self.assertEqual(0, fake.skill_sends)
            window._membership_confirmed = True
            window._send_skill_state(SkillState(user_id="12", nickname="x"))
            # 异步 bridge 由真实环境消费；本测试只验证确认前的硬拦截
        finally:
            self._close(window)

    def test_membership_error_deduplicated_and_http_rejoin(self) -> None:
        window = self._window()
        fake = _FakeWs()
        api = _FakeApi()
        try:
            window._ws = fake
            window.api = api
            window._membership_confirmed = True
            before = len(window._timeline.entries)
            window._handle_ws_error({"code": "NOT_ROOM_MEMBER", "message": "你还没有加入房间"})
            middle = len(window._timeline.entries)
            window._handle_ws_error({"code": "NOT_ROOM_MEMBER", "message": "你还没有加入房间"})
            self.assertEqual(before + 1, middle)
            self.assertEqual(middle, len(window._timeline.entries))
            self.assertEqual([("ABC123", None)], api.joins)
            self.assertTrue(window._rejoin_in_progress)
            # HTTP rejoin 成功 → 再发 WS join
            window._on_http_rejoin_success(window._current_room)
            self.assertTrue(window._rejoin_in_progress)
            self.assertEqual([("ABC123", None)], fake.joins)
            window._on_ws_message(1, {"type": "room_joined", "room": {"id": "1", "code": "ABC123", "name": "test"}})
            self.assertFalse(window._rejoin_in_progress)
            self.assertTrue(window._membership_confirmed)
        finally:
            self._close(window)

    def test_rejoin_failure_returns_to_lobby(self) -> None:
        window = self._window()
        try:
            window._on_rejoin_failed(RuntimeError("房间不存在"))
            self.assertIsNone(window._current_room)
            self.assertFalse(window._membership_confirmed)
        finally:
            self._close(window)


if __name__ == "__main__":
    unittest.main()
