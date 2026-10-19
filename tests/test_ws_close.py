"""WS 关闭原因分类：顶号/认证失效不重连，网络/更新继续。"""

from __future__ import annotations

import asyncio
import unittest

from core.ws_close import AUTH_ERROR, RECONNECT, REPLACED, RESTARTING, classify_close
from net.ws_client import WsClient


class CloseClassificationTests(unittest.TestCase):
    def test_replaced(self) -> None:
        self.assertEqual(REPLACED, classify_close(4001, "replaced"))
        self.assertEqual(REPLACED, classify_close(1000, "another device login"))
        self.assertEqual(REPLACED, classify_close(None, "账号被顶号"))

    def test_auth(self) -> None:
        self.assertEqual(AUTH_ERROR, classify_close(4003, ""))
        self.assertEqual(AUTH_ERROR, classify_close(4401, ""))

    def test_restart_and_network(self) -> None:
        self.assertEqual(RESTARTING, classify_close(1012, "service restart"))
        self.assertEqual(RECONNECT, classify_close(1001, "going away"))
        self.assertEqual(RECONNECT, classify_close(1006, ""))

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
