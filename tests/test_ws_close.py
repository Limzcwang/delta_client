"""WS 关闭原因分类：顶号/认证失效不重连，网络/更新继续。"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from core.ws_close import (
    AUTH_FAILED,
    RECONNECT,
    REPLACED,
    RESTARTING,
    classify_close,
    classify_open_error,
)
from net.ws_client import WsClient


class CloseClassificationTests(unittest.TestCase):
    def test_replaced(self) -> None:
        self.assertEqual(REPLACED, classify_close(4001, "replaced"))
        self.assertEqual(REPLACED, classify_close(1000, "another device login"))
        self.assertEqual(REPLACED, classify_close(None, "账号被顶号"))

    def test_auth(self) -> None:
        self.assertEqual(AUTH_FAILED, classify_close(401, "unauthorized"))
        self.assertEqual(AUTH_FAILED, classify_close(403, "forbidden"))
        self.assertEqual(AUTH_FAILED, classify_close(4003, ""))
        self.assertEqual(AUTH_FAILED, classify_close(4401, ""))

    def test_restart_and_network(self) -> None:
        self.assertEqual(RESTARTING, classify_close(1012, "service restart"))
        self.assertEqual(RECONNECT, classify_close(1001, "going away"))
        self.assertEqual(RECONNECT, classify_close(1006, ""))

    def test_handshake_401_403_classified_auth(self) -> None:
        class HandshakeError(Exception):
            def __init__(self, status):
                super().__init__(f"HTTP {status}")
                self.response = SimpleNamespace(status_code=status)

        self.assertEqual(AUTH_FAILED, classify_open_error(HandshakeError(401)))
        self.assertEqual(AUTH_FAILED, classify_open_error(HandshakeError(403)))
        self.assertEqual(AUTH_FAILED, classify_open_error(RuntimeError("HTTP 401 Unauthorized")))
        self.assertEqual(RECONNECT, classify_open_error(ConnectionError("refused")))

    def _run_handshake_error(self, exc: BaseException) -> list[str]:
        states: list[str] = []

        async def factory(_url):
            raise exc

        client = WsClient(
            "ws://test",
            "token",
            on_state=lambda state, info: states.append(state),
            connect_factory=factory,
        )
        asyncio.run(asyncio.wait_for(client.run(), timeout=5))
        return states

    def test_handshake_401_stops_without_reconnect(self) -> None:
        class HandshakeError(Exception):
            def __init__(self, status):
                super().__init__(f"HTTP {status}")
                self.response = SimpleNamespace(status_code=status)

        for status in (401, 403):
            with self.subTest(status=status):
                states = self._run_handshake_error(HandshakeError(status))
                self.assertIn("auth_failed", states)
                self.assertNotIn("waiting", states)

    def test_4001_stops_run_without_reconnect(self) -> None:
        class FakeWs:
            close_code = 4001
            close_reason = "replaced"

            async def send(self, data):
                return None

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def close(self):
                return None

        states: list[str] = []

        async def factory(_url):
            return FakeWs()

        client = WsClient(
            "ws://test",
            "token",
            on_state=lambda state, info: states.append(state),
            connect_factory=factory,
        )
        asyncio.run(asyncio.wait_for(client.run(), timeout=5))
        self.assertIn("replaced", states)
        self.assertNotIn("waiting", states)


if __name__ == "__main__":
    unittest.main()
