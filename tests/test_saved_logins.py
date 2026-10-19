"""H2 历史账号/加密密码存储测试（DPAPI 在非 Windows 跳过）。"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

from state.saved_logins import (
    MAX_SAVED_LOGINS,
    PASSWORD_TTL_SECONDS,
    CryptoUnavailable,
    SavedLogins,
    dpapi_protect,
    dpapi_unprotect,
)


def fake_protect(plain: str) -> str:
    return base64.b64encode(b"FAKE:" + plain.encode("utf-8")).decode("ascii")


def fake_unprotect(token: str) -> str:
    raw = base64.b64decode(token.encode("ascii"), validate=True)
    if not raw.startswith(b"FAKE:"):
        raise CryptoUnavailable("bad fake cipher")
    return raw[5:].decode("utf-8")


class SavedLoginsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "saved_logins.json"
        self.now = 1_700_000_000.0

    def make_store(self, *, protector=fake_protect, unprotector=fake_unprotect, clock=None):
        return SavedLogins(
            self.path,
            clock=clock or (lambda: self.now),
            protector=protector,
            unprotector=unprotector,
        )

    def test_save_encrypts_password_not_plaintext(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "DeltaTest2026")
        text = self.path.read_text(encoding="utf-8")
        self.assertNotIn("DeltaTest2026", text)
        payload = json.loads(text)
        self.assertEqual(1, payload["version"])
        entry = payload["entries"][0]
        self.assertEqual("DeltaQA01", entry["username"])
        self.assertTrue(entry["secret"])
        self.assertEqual("DeltaTest2026", store.password_for("DeltaQA01"))
        self.assertTrue(store.infos()[0].has_password)

    def test_dpapi_fallback_only_saves_account(self) -> None:
        def broken(_plain: str) -> str:
            raise CryptoUnavailable("dpapi unavailable")

        store = self.make_store(protector=broken)
        store.upsert("DeltaQA02", "SecretPass123")
        self.assertIsNone(store.password_for("DeltaQA02"))
        info = store.recent_info()
        self.assertIsNotNone(info)
        self.assertEqual("DeltaQA02", info.username)
        self.assertFalse(info.has_password)
        self.assertNotIn("SecretPass123", self.path.read_text(encoding="utf-8"))

    def test_expiry_boundaries_29_30_31_days(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "SecretPass123")
        saved = self.now
        self.assertEqual("SecretPass123", store.password_for("DeltaQA01"))

        self.now = saved + 29 * 86400
        self.assertEqual("SecretPass123", store.password_for("DeltaQA01"))
        self.assertFalse(store.infos()[0].expired)

        self.now = saved + 30 * 86400
        self.assertIsNone(store.password_for("DeltaQA01"))
        self.assertTrue(store.infos()[0].expired)

        self.now = saved + 31 * 86400
        self.assertIsNone(store.password_for("DeltaQA01"))
        self.assertTrue(store.infos()[0].expired)
        # 账号仍保留
        self.assertEqual("DeltaQA01", store.recent_info().username)

    def test_lru_keeps_max_five_newest(self) -> None:
        store = self.make_store()
        for index in range(6):
            self.now += 10
            store.upsert(f"user{index}", "Pass12345")
        infos = store.infos()
        self.assertEqual(MAX_SAVED_LOGINS, len(infos))
        self.assertEqual("user5", infos[0].username)
        self.assertNotIn("user0", {info.username for info in infos})
        self.assertEqual(MAX_SAVED_LOGINS, len(json.loads(self.path.read_text())["entries"]))

    def test_change_password_clears_password_keeps_account(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "OldPass123")
        self.assertTrue(store.clear_password("DeltaQA01"))
        self.assertIsNone(store.password_for("DeltaQA01"))
        self.assertEqual("DeltaQA01", store.recent_info().username)
        self.assertFalse(store.recent_info().has_password)
        self.assertFalse(store.clear_password("nobody"))

    def test_delete_and_clear_all(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "Pass12345")
        store.upsert("DeltaQA02", "Pass12345")
        self.assertTrue(store.remove("DeltaQA01"))
        self.assertFalse(store.remove("DeltaQA01"))
        self.assertEqual(["DeltaQA02"], [info.username for info in store.infos()])
        store.clear()
        self.assertEqual([], store.infos())
        self.assertEqual([], json.loads(self.path.read_text())["entries"])

    def test_restart_keeps_history_like_logout(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "SecretPass123")
        # 重启/退出登录不会调用 clear，重新加载仍保留账号与可解密密码
        reloaded = self.make_store()
        self.assertEqual("DeltaQA01", reloaded.recent_info().username)
        self.assertEqual("SecretPass123", reloaded.password_for("DeltaQA01"))

    def test_corrupt_file_tolerated(self) -> None:
        self.path.write_text("{not-json", encoding="utf-8")
        store = self.make_store()
        self.assertEqual([], store.infos())
        store.upsert("DeltaQA01", "Pass12345")
        self.assertEqual("DeltaQA01", store.recent_info().username)

    def test_saved_at_and_expires_at(self) -> None:
        store = self.make_store()
        store.upsert("DeltaQA01", "Pass12345")
        entry = store.raw_entries()[0]
        self.assertEqual(self.now, entry.saved_at)
        self.assertEqual(self.now + PASSWORD_TTL_SECONDS, entry.expires_at)
        self.assertEqual(self.now, entry.last_used_at)


@unittest.skipUnless(sys.platform == "win32", "DPAPI 仅 Windows 可测")
class DpapiRoundTripTests(unittest.TestCase):
    def test_dpapi_roundtrip(self) -> None:
        token = dpapi_protect("DeltaTest2026-中文")
        self.assertIsInstance(token, str)
        self.assertNotIn("DeltaTest2026", token)
        self.assertEqual("DeltaTest2026-中文", dpapi_unprotect(token))


if __name__ == "__main__":
    unittest.main()
