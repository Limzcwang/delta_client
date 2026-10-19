"""HTTP 错误映射测试（离线，不依赖 aiohttp）。"""

from __future__ import annotations

import asyncio
import unittest

from core.errors import (
    ApiError,
    ErrorKind,
    api_error_from_exception,
    api_error_from_response,
    kind_for_status,
    parse_error_body,
    to_user_message,
)


class StatusMappingTests(unittest.TestCase):
    def test_kind_for_status(self) -> None:
        expected = {
            400: ErrorKind.VALIDATION,
            401: ErrorKind.AUTH,
            403: ErrorKind.FORBIDDEN,
            404: ErrorKind.NOT_FOUND,
            409: ErrorKind.CONFLICT,
            422: ErrorKind.VALIDATION,
            429: ErrorKind.RATE_LIMIT,
            500: ErrorKind.SERVER,
            502: ErrorKind.SERVER,
            503: ErrorKind.SERVER,
            418: ErrorKind.UNKNOWN,
        }
        for status, kind in expected.items():
            with self.subTest(status=status):
                self.assertEqual(kind_for_status(status), kind)


class ErrorBodyTests(unittest.TestCase):
    def test_fastapi_detail_string(self) -> None:
        error = api_error_from_response(401, {"detail": "用户名或密码错误"})
        self.assertEqual(error.kind, ErrorKind.AUTH)
        self.assertEqual(error.user_message, "用户名或密码错误")

    def test_room_error_code_envelope(self) -> None:
        error = api_error_from_response(
            404, {"detail": {"error_code": "ROOM_NOT_FOUND", "message": "房间不存在"}}
        )
        self.assertEqual(error.kind, ErrorKind.ROOM_NOT_FOUND)
        self.assertEqual(error.user_message, "房间不存在")

    def test_target_envelope_numeric_code(self) -> None:
        body = {"code": 40101, "message": "token 过期", "data": None, "request_id": "req_1"}
        error = api_error_from_response(401, body)
        self.assertEqual(error.kind, ErrorKind.TOKEN_EXPIRED)
        self.assertEqual(error.code, 40101)
        self.assertEqual(error.request_id, "req_1")
        self.assertTrue(error.is_auth_error)

    def test_string_code_from_ws(self) -> None:
        error = api_error_from_response(403, {"code": "ROOM_PASSWORD_REQUIRED", "message": "该房间需要密码"})
        self.assertEqual(error.kind, ErrorKind.ROOM_PASSWORD_REQUIRED)
        self.assertTrue(error.needs_room_password)

    def test_pydantic_validation_list(self) -> None:
        error = api_error_from_response(422, {"detail": [{"loc": ["body", "name"], "msg": "field required"}]})
        self.assertEqual(error.kind, ErrorKind.VALIDATION)
        self.assertIn("请求参数不合法", error.user_message)

    def test_server_error_hides_detail(self) -> None:
        error = api_error_from_response(500, {"code": 50000, "message": "SQLSTATE password=secret"})
        self.assertEqual(error.kind, ErrorKind.SERVER)
        self.assertNotIn("SQLSTATE", error.user_message)
        self.assertNotIn("secret", error.user_message)

    def test_password_message_refinement(self) -> None:
        required = api_error_from_response(403, {"detail": {"message": "该房间需要密码"}})
        self.assertEqual(required.kind, ErrorKind.ROOM_PASSWORD_REQUIRED)
        invalid = api_error_from_response(403, {"detail": {"message": "房间密码错误"}})
        self.assertEqual(invalid.kind, ErrorKind.ROOM_PASSWORD_INVALID)

    def test_parse_error_body_handles_junk(self) -> None:
        self.assertEqual(parse_error_body(None), (None, None, None))
        self.assertEqual(parse_error_body("<html>500</html>"), ("<html>500</html>", None, None))
        message, code, request_id = parse_error_body({"error": {"code": "X", "message": "boom"}, "request_id": "r"})
        self.assertEqual((message, code, request_id), ("boom", "X", "r"))

    def test_success_code_ignored(self) -> None:
        message, code, _ = parse_error_body({"code": 200, "message": "OK"})
        self.assertIsNone(code)
        self.assertEqual(message, "OK")

    def test_b2b_nested_data_error_code(self) -> None:
        """B2b 实测错误体：顶层 code 只是 40000 类别，具体码在 data.error_code。"""
        body = {
            "code": 40000,
            "message": "该房间需要密码",
            "data": {"error_code": "ROOM_PASSWORD_REQUIRED"},
            "request_id": "req_1",
        }
        error = api_error_from_response(400, body)
        self.assertEqual(error.code, "ROOM_PASSWORD_REQUIRED")
        self.assertEqual(error.kind, ErrorKind.ROOM_PASSWORD_REQUIRED)
        self.assertEqual(error.user_message, "该房间需要密码")
        self.assertEqual(error.request_id, "req_1")

        invalid = api_error_from_response(
            400,
            {"code": 40000, "message": "房间密码错误", "data": {"error_code": "ROOM_PASSWORD_INVALID"}},
        )
        self.assertEqual(invalid.kind, ErrorKind.ROOM_PASSWORD_INVALID)
        self.assertTrue(invalid.needs_room_password)

    def test_b2b_ws_error_code_aliases(self) -> None:
        not_authenticated = api_error_from_response(
            400,
            {"type": "error", "code": "NOT_AUTHENTICATED", "error_code": "NOT_AUTHENTICATED", "message": "请先完成认证"},
        )
        self.assertEqual(not_authenticated.kind, ErrorKind.AUTH)
        self.assertTrue(not_authenticated.is_auth_error)

        not_member = api_error_from_response(
            400,
            {"type": "error", "code": "NOT_ROOM_MEMBER", "error_code": "NOT_ROOM_MEMBER", "message": "你不在该房间中"},
        )
        self.assertEqual(not_member.kind, ErrorKind.FORBIDDEN)

        unsupported = api_error_from_response(
            400, {"type": "error", "code": "UNSUPPORTED_MESSAGE_TYPE", "message": "当前版本不支持消息类型"}
        )
        self.assertEqual(unsupported.kind, ErrorKind.VALIDATION)


class ExceptionMappingTests(unittest.TestCase):
    def test_timeout(self) -> None:
        self.assertEqual(api_error_from_exception(asyncio.TimeoutError()).kind, ErrorKind.TIMEOUT)

    def test_network(self) -> None:
        self.assertEqual(api_error_from_exception(ConnectionResetError("reset")).kind, ErrorKind.NETWORK)

    def test_unknown(self) -> None:
        self.assertEqual(api_error_from_exception(RuntimeError("boom")).kind, ErrorKind.UNKNOWN)

    def test_api_error_passthrough(self) -> None:
        original = ApiError(ErrorKind.AUTH, "bad")
        self.assertIs(api_error_from_exception(original), original)

    def test_to_user_message(self) -> None:
        self.assertEqual(to_user_message(ApiError(ErrorKind.NETWORK)), "无法连接到服务器，请检查网络或服务器地址")
        self.assertEqual(to_user_message(RuntimeError("自定义错误")), "自定义错误")


if __name__ == "__main__":
    unittest.main()
