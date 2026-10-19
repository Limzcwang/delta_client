"""连通性自检结果模型测试（离线，不联网）。"""

from __future__ import annotations

import unittest

from core.connection import ConnectionCheck, probe_from_error, probe_ok
from core.errors import ApiError, ErrorKind


class ProbeTests(unittest.TestCase):
    def test_probe_ok(self) -> None:
        probe = probe_ok("health", "/health 200", status=200, elapsed_ms=12)
        self.assertTrue(probe.ok)
        self.assertEqual(probe.category, "ok")
        self.assertEqual(probe.elapsed_ms, 12)

    def test_timeout(self) -> None:
        probe = probe_from_error("health", ApiError(ErrorKind.TIMEOUT), elapsed_ms=8000)
        self.assertFalse(probe.ok)
        self.assertEqual(probe.category, "timeout")
        self.assertIn("超时", probe.category_label)

    def test_auth(self) -> None:
        probe = probe_from_error("rooms", ApiError(ErrorKind.TOKEN_EXPIRED, "登录已过期", status=401))
        self.assertEqual(probe.category, "auth")
        self.assertEqual(probe.status, 401)
        self.assertIn("鉴权", probe.category_label)

    def test_network(self) -> None:
        probe = probe_from_error("health", ApiError(ErrorKind.NETWORK, "无法连接"))
        self.assertEqual(probe.category, "network")

    def test_server_error(self) -> None:
        probe = probe_from_error("rooms", ApiError(ErrorKind.SERVER, "boom", status=500))
        self.assertEqual(probe.category, "server")

    def test_http_error(self) -> None:
        probe = probe_from_error("rooms", ApiError(ErrorKind.NOT_FOUND, "不存在", status=404))
        self.assertEqual(probe.category, "http_error")

    def test_unexpected_exception(self) -> None:
        probe = probe_from_error("rooms", RuntimeError("weird"))
        self.assertEqual(probe.category, "unexpected")
        self.assertIn("weird", probe.detail)


class ConnectionCheckTests(unittest.TestCase):
    def test_ok_format(self) -> None:
        check = ConnectionCheck(
            server_url="http://127.0.0.1:8000",
            health=probe_ok("health", "/health 200", elapsed_ms=5),
            rooms=probe_ok("rooms", "ok", elapsed_ms=8),
            rooms_count=3,
        )
        text = check.format_text()
        self.assertTrue(check.ok)
        self.assertIn("服务器：http://127.0.0.1:8000", text)
        self.assertIn("HTTP 可达：✅", text)
        self.assertIn("房间接口：✅", text)
        self.assertIn("3 个房间", text)
        self.assertIn("8ms", text)

    def test_auth_failure_format(self) -> None:
        check = ConnectionCheck(
            server_url="http://host:8000",
            health=probe_ok("health", "/health 200", elapsed_ms=3),
            rooms=probe_from_error("rooms", ApiError(ErrorKind.AUTH, "登录凭证无效", status=401)),
        )
        text = check.format_text()
        self.assertFalse(check.ok)
        self.assertIn("HTTP 可达：✅", text)
        self.assertIn("鉴权失效：❌ 登录凭证无效", text)

    def test_health_timeout_format(self) -> None:
        check = ConnectionCheck(
            server_url="http://host:8000",
            health=probe_from_error("health", ApiError(ErrorKind.TIMEOUT), elapsed_ms=8000),
            rooms=probe_from_error("rooms", ApiError(ErrorKind.TIMEOUT), elapsed_ms=8000),
        )
        text = check.format_text()
        self.assertFalse(check.ok)
        self.assertIn("HTTP 可达：❌ 超时", text)
        self.assertIn("房间接口：❌ 超时", text)

    def test_network_format(self) -> None:
        check = ConnectionCheck(
            server_url="http://host:8000",
            health=probe_from_error("health", ApiError(ErrorKind.NETWORK, "网络不可达")),
            rooms=probe_from_error("rooms", ApiError(ErrorKind.NETWORK, "网络不可达")),
        )
        text = check.format_text()
        self.assertIn("网络不可达", text)


if __name__ == "__main__":
    unittest.main()
