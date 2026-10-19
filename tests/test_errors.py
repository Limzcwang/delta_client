"""HTTP 错误映射测试（离线，不依赖 aiohttp）。"""

from __future__ import annotations

import asyncio
import unittest

from core.errors import (
    ApiError,
    ErrorKind,
    api_error_from_exception,
    api_error_from_response,
    code_message,
    kind_for_code,
    kind_for_status,
    parse_error_body,
    to_user_message,
)

WS_ERROR_CODES = [
    "NOT_AUTHENTICATED",
    "AUTH_INVALID",
    "AUTH_EXPIRED",
    "ALREADY_AUTHENTICATED",
    "NOT_ROOM_MEMBER",
    "NOT_ROOM_OWNER",
    "MEMBER_NOT_FOUND",
    "ROOM_NOT_FOUND",
    "ROOM_CLOSED",
    "ROOM_PASSWORD_REQUIRED",
    "ROOM_PASSWORD_INVALID",
    "ROOM_FULL",
    "RATE_LIMITED",
    "INVALID_MESSAGE",
    "INVALID_PAYLOAD",
    "INVALID_JSON",
    "UNSUPPORTED_MESSAGE_TYPE",
    "CANVAS_SEQ_GAP",
    "CANVAS_OUT_OF_ORDER",
    "INVALID_CANVAS_OP",
    "INTERNAL_ERROR",
]

HTTP_ERROR_CODES = [
    "ROOM_NOT_FOUND",
    "MEMBER_NOT_FOUND",
    "NOT_ROOM_MEMBER",
    "NOT_ROOM_OWNER",
    "ROOM_PASSWORD_REQUIRED",
    "ROOM_PASSWORD_INVALID",
    "ROOM_NAME_INVALID",
    "INVALID_BACKGROUND",
    "INVALID_VISIBILITY",
    "ROOM_PASSWORD_NOT_ALLOWED",
    "CANNOT_KICK_OWNER",
    "INVALID_PAGINATION",
    "INVALID_CURSOR",
    "INVALID_MESSAGE",
    "ROOM_FULL",
    "ROOM_OWNER_MUST_CLOSE",
    "ROOM_CLOSED",
    "RATE_LIMITED",
    "ROOM_CODE_GENERATION_FAILED",
    "INVALID_CANVAS_OP",
]

#: F：个人资料/账号相关错误码
PROFILE_ERROR_CODES = [
    "INVALID_USERNAME",
    "USERNAME_TAKEN",
    "INVALID_NICKNAME",
    "NICKNAME_TAKEN",
    "INVALID_PASSWORD",
    "OLD_PASSWORD_INVALID",
    "WRONG_OLD_PASSWORD",
    "INVALID_NEW_PASSWORD",
    "INVALID_OLD_PASSWORD",
    "PASSWORD_MISMATCH",
    "PASSWORD_TOO_WEAK",
]


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


class ProtocolPr9ErrorTableTests(unittest.TestCase):
    """PROTOCOL PR#9 §7.2/§7.3：客户端必须认识全部实名错误码。"""

    def test_all_ws_codes_known(self) -> None:
        for code in WS_ERROR_CODES:
            with self.subTest(code=code):
                kind = kind_for_code(code)
                self.assertIsNotNone(kind, f"WS 错误码 {code} 未映射")
                self.assertNotEqual(kind, ErrorKind.UNKNOWN, f"WS 错误码 {code} 映射为 UNKNOWN")
                self.assertTrue(code_message(code), f"WS 错误码 {code} 缺少用户文案")

    def test_all_http_error_codes_known(self) -> None:
        for code in HTTP_ERROR_CODES:
            with self.subTest(code=code):
                kind = kind_for_code(code)
                self.assertIsNotNone(kind, f"HTTP error_code {code} 未映射")
                self.assertNotEqual(kind, ErrorKind.UNKNOWN, f"HTTP error_code {code} 映射为 UNKNOWN")
                self.assertTrue(code_message(code), f"HTTP error_code {code} 缺少用户文案")

    def test_auth_code_semantics(self) -> None:
        self.assertEqual(kind_for_code("AUTH_INVALID"), ErrorKind.AUTH)
        self.assertEqual(kind_for_code("AUTH_EXPIRED"), ErrorKind.TOKEN_EXPIRED)
        self.assertEqual(kind_for_code("NOT_AUTHENTICATED"), ErrorKind.AUTH)
        self.assertEqual(kind_for_code("NOT_ROOM_MEMBER"), ErrorKind.FORBIDDEN)
        self.assertEqual(kind_for_code("ROOM_CLOSED"), ErrorKind.ROOM_NOT_FOUND)
        self.assertEqual(kind_for_code("ROOM_OWNER_MUST_CLOSE"), ErrorKind.CONFLICT)

    def test_auth_expired_ws_error_maps_to_relogin(self) -> None:
        error = api_error_from_response(
            401, {"type": "error", "code": "AUTH_EXPIRED", "message": "登录已过期，请重新登录"}
        )
        self.assertTrue(error.is_auth_error)
        self.assertEqual(error.kind, ErrorKind.TOKEN_EXPIRED)

    def test_room_owner_must_close_message(self) -> None:
        error = api_error_from_response(
            409,
            {"code": 40900, "message": "", "data": {"error_code": "ROOM_OWNER_MUST_CLOSE"}},
        )
        self.assertEqual(error.kind, ErrorKind.CONFLICT)
        self.assertIn("房主", error.user_message)

    def test_profile_error_codes_known(self) -> None:
        for code in PROFILE_ERROR_CODES:
            with self.subTest(code=code):
                kind = kind_for_code(code)
                self.assertIsNotNone(kind, f"资料错误码 {code} 未映射")
                self.assertNotEqual(kind, ErrorKind.UNKNOWN)
                self.assertTrue(code_message(code), f"资料错误码 {code} 缺少用户文案")

    def test_invalid_username_maps_to_friendly_hint(self) -> None:
        error = api_error_from_response(
            400,
            {"code": 40000, "message": "invalid username", "data": {"error_code": "INVALID_USERNAME"}},
        )
        self.assertEqual(error.kind, ErrorKind.VALIDATION)
        # 服务端 message 优先；无 message 时用 code 中文文案
        bare = api_error_from_response(
            400, {"code": 40000, "message": "", "data": {"error_code": "INVALID_USERNAME"}}
        )
        self.assertIn("6–20", bare.user_message)


if __name__ == "__main__":
    unittest.main()
