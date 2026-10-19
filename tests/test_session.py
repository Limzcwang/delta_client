"""会话/token 存取测试：内存 + 可选落盘，且绝不落盘密码。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from state.session import Session


class SessionMemoryTests(unittest.TestCase):
    def test_set_login_and_clear(self) -> None:
        session = Session()
        self.assertFalse(session.is_logged_in)
        self.assertEqual(session.authorization_header(), {})

        session.set_login("jwt-1", {"id": "1", "username": "alice"})
        self.assertTrue(session.is_logged_in)
        self.assertTrue(session.has_token)
        self.assertEqual(session.username, "alice")
        self.assertEqual(session.user_id, "1")
        self.assertEqual(session.authorization_header(), {"Authorization": "Bearer jwt-1"})

        session.clear()
        self.assertFalse(session.is_logged_in)
        self.assertIsNone(session.token)
        self.assertEqual(session.user, {})

    def test_login_without_token_still_counts_as_logged_in(self) -> None:
        # A 现状后端登录不返回 JWT，但用户信息可用于进入大厅
        session = Session()
        session.set_login(None, {"username": "legacy"})
        self.assertFalse(session.has_token)
        self.assertTrue(session.is_logged_in)
        self.assertEqual(session.authorization_header(), {})

    def test_repr_does_not_leak_token(self) -> None:
        session = Session(token="super-secret-jwt", user={"username": "a"})
        self.assertNotIn("super-secret-jwt", repr(session))


class SessionPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / ".delta_client_session.json"

    def test_no_file_when_persistence_disabled(self) -> None:
        session = Session(persist_token=False, persist_path=self.path)
        session.set_login("jwt", {"username": "alice"})
        self.assertFalse(self.path.exists())

    def test_file_written_when_enabled_and_no_password(self) -> None:
        session = Session(persist_token=True, persist_path=self.path)
        session.set_login(
            "jwt-123",
            {"id": "1", "username": "alice", "password": "Pa55w0rd!", "access_token": "leak"},
        )
        self.assertTrue(self.path.exists())
        raw = self.path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        self.assertEqual(payload["token"], "jwt-123")
        self.assertEqual(payload["user"], {"id": "1", "username": "alice"})
        self.assertNotIn("Pa55w0rd", raw)
        self.assertNotIn("password", raw)
        self.assertNotIn("leak", raw)

    def test_reload_from_file(self) -> None:
        session = Session(persist_token=True, persist_path=self.path)
        session.set_login("jwt-abc", {"id": "2", "username": "bob"})
        restored = Session.from_file(self.path)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.token, "jwt-abc")
        self.assertEqual(restored.username, "bob")
        self.assertEqual(restored.authorization_header(), {"Authorization": "Bearer jwt-abc"})

    def test_clear_removes_file(self) -> None:
        session = Session(persist_token=True, persist_path=self.path)
        session.set_login("jwt", {"username": "alice"})
        self.assertTrue(self.path.exists())
        session.clear()
        self.assertFalse(self.path.exists())

    def test_toggle_persistence_off_removes_file(self) -> None:
        session = Session(persist_token=True, persist_path=self.path)
        session.set_login("jwt", {"username": "alice"})
        self.assertTrue(self.path.exists())
        session.set_persist_token(False)
        self.assertFalse(self.path.exists())
        # 内存 token 仍在，不影响当前会话
        self.assertEqual(session.token, "jwt")

    def test_no_token_no_file(self) -> None:
        session = Session(persist_token=True, persist_path=self.path)
        session.set_login(None, {"username": "legacy"})
        self.assertFalse(self.path.exists())

    def test_corrupt_or_missing_file(self) -> None:
        self.assertIsNone(Session.from_file(self.path))
        self.path.write_text("{broken", encoding="utf-8")
        self.assertIsNone(Session.from_file(self.path))
        self.path.write_text(json.dumps({"user": {"username": "a"}}), encoding="utf-8")
        self.assertIsNone(Session.from_file(self.path))


if __name__ == "__main__":
    unittest.main()
