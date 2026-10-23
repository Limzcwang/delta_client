"""0.2.4：连接候选回退。"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from config import AppConfig, FALLBACK_SERVER_URL, connection_candidates
    from core.connection import ConnectionCheck, probe_from_error, probe_ok
    from core.errors import ApiError, ErrorKind
    from net.api_client import LoginResult
    from state.session import Session
    from ui.main_window import MainWindow

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


class CandidateProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_network_false_continues_to_next(self) -> None:
        from ui import main_window

        checks = {
            "https://a": ConnectionCheck("https://a", probe_from_error("health", ApiError(ErrorKind.NETWORK)), probe_from_error("rooms", ApiError(ErrorKind.NETWORK))),
            "https://b": ConnectionCheck("https://b", probe_ok("health", "ok"), probe_ok("rooms", "ok")),
        }
        async def fake(url, token, timeout=8.0):
            return checks[url]
        original = main_window._run_connection_check
        main_window._run_connection_check = fake
        try:
            url, check = await main_window._run_connection_check_candidates(["https://a", "https://b"], None)
        finally:
            main_window._run_connection_check = original
        self.assertEqual("https://b", url)
        self.assertTrue(check.ok)

    async def test_business_failure_stops(self) -> None:
        from ui import main_window

        business = ConnectionCheck("https://a", probe_ok("health", "ok"), probe_from_error("rooms", ApiError(ErrorKind.AUTH, "401", status=401)))
        calls = []
        async def fake(url, token, timeout=8.0):
            calls.append(url)
            if url == "https://b":
                raise AssertionError("业务失败不应继续候选")
            return business
        original = main_window._run_connection_check
        main_window._run_connection_check = fake
        try:
            url, check = await main_window._run_connection_check_candidates(["https://a", "https://b"], None)
        finally:
            main_window._run_connection_check = original
        self.assertEqual("https://a", url)
        self.assertFalse(check.ok)
        self.assertEqual(["https://a"], calls)


class CandidateTests(unittest.TestCase):
    def test_order_and_dedup(self) -> None:
        self.assertEqual(
            ["https://deltachat.icu", "https://deltachat.icu:8443"],
            connection_candidates("https://deltachat.icu"),
        )
        self.assertEqual(
            ["https://deltachat.icu:8443"],
            connection_candidates("https://deltachat.icu:8443"),
        )
        self.assertEqual(
            ["https://manual.example", "https://deltachat.icu:8443"],
            connection_candidates("https://manual.example"),
        )
        self.assertEqual("wss://deltachat.icu:8443/ws", AppConfig(server_url=FALLBACK_SERVER_URL).effective_ws_url)


@unittest.skipUnless(HAS_QT, "PySide6 未安装")
class LoginFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False), session)
        return window

    def _close(self, window):
        window.bridge.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_network_failure_advances_candidate(self) -> None:
        window = self._window()
        try:
            window._login_candidates = connection_candidates("https://deltachat.icu")
            window._login_candidate_index = 0
            window._try_login_candidate = lambda: None
            window._on_login_candidate_failure(ApiError(ErrorKind.NETWORK, "reset"))
            self.assertEqual(1, window._login_candidate_index)
        finally:
            self._close(window)

    def test_success_persists_fallback_address(self) -> None:
        window = self._window()
        try:
            seen = []
            window._on_login_success = lambda *a: seen.append(a)
            result = LoginResult(token="t", user={"id": "12", "username": "DeltaQA01"})
            with mock.patch("ui.main_window.save_config") as save:
                window._on_login_candidate_success(
                    "https://deltachat.icu:8443", result, "DeltaQA01", "pw"
                )
            self.assertEqual("https://deltachat.icu:8443", window.config.server_url)
            self.assertIsNone(window.config.ws_url)
            self.assertEqual("wss://deltachat.icu:8443/ws", window.config.effective_ws_url)
            save.assert_called()
            self.assertTrue(seen)
        finally:
            self._close(window)

    def test_all_candidates_failure_reports_once(self) -> None:
        window = self._window()
        try:
            errors = []
            window.login_view.show_error = lambda text: errors.append(text)
            window._set_status = lambda text: errors.append(text)
            window._login_candidates = ["https://a", "https://b"]
            window._login_candidate_index = 2
            window._on_login_candidates_failed()
            self.assertEqual([], errors)
            self.assertEqual([], errors)
        finally:
            self._close(window)


if __name__ == "__main__":
    unittest.main()
