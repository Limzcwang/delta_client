"""协议常量/WS 消息/响应包兼容逻辑测试（离线）。"""

from __future__ import annotations

import json
import unittest

from core import protocol


class PathTests(unittest.TestCase):
    def test_room_paths(self) -> None:
        self.assertEqual(protocol.room_join_path("AB12C"), "/api/v1/rooms/AB12C/join")
        self.assertEqual(protocol.room_leave_path("AB12C"), "/api/v1/rooms/AB12C/leave")
        self.assertEqual(protocol.room_detail_path("AB12C"), "/api/v1/rooms/AB12C")
        self.assertEqual(protocol.room_join_path("a/b"), "/api/v1/rooms/a%2Fb/join")

    def test_login_paths_match_protocol(self) -> None:
        self.assertEqual(protocol.API_V1_LOGIN, "/api/v1/auth/login")
        self.assertEqual(protocol.API_V1_ROOMS, "/api/v1/rooms")
        self.assertEqual(protocol.API_LOGIN_LEGACY, "/api/users/login")


class WsUrlTests(unittest.TestCase):
    def test_ws_from_http(self) -> None:
        self.assertEqual(protocol.ws_url_for("http://127.0.0.1:8000"), "ws://127.0.0.1:8000/ws")

    def test_ws_from_https_with_prefix(self) -> None:
        self.assertEqual(protocol.ws_url_for("https://game.example.com/delta"), "wss://game.example.com/delta/ws")

    def test_ws_invalid_scheme(self) -> None:
        with self.assertRaises(ValueError):
            protocol.ws_url_for("ftp://host")


class MessageTests(unittest.TestCase):
    def test_auth_message(self) -> None:
        message = protocol.auth_message("jwt-token")
        self.assertEqual(message["type"], "auth")
        self.assertEqual(message["token"], "jwt-token")
        self.assertEqual(message["protocol_version"], protocol.PROTOCOL_VERSION)
        self.assertEqual(message["client"]["name"], protocol.CLIENT_NAME)
        self.assertIn("version", message["client"])

    def test_join_room_message_optional_password(self) -> None:
        no_password = protocol.join_room_message("AB12C")
        self.assertNotIn("password", no_password)
        with_password = protocol.join_room_message("AB12C", "1234", request_id="c-1")
        self.assertEqual(with_password["password"], "1234")
        self.assertEqual(with_password["request_id"], "c-1")

    def test_chat_and_ping_messages(self) -> None:
        chat = protocol.chat_send_message("大家好", "m-1")
        self.assertEqual(chat, {"type": "chat_send", "client_msg_id": "m-1", "content": "大家好", "content_type": "text"})
        ping = protocol.ping_message(1750000000000)
        self.assertEqual(ping["type"], "ping")
        self.assertIsInstance(ping["ts"], int)

    def test_ids_are_unique(self) -> None:
        self.assertTrue(protocol.make_request_id().startswith("c-"))
        self.assertTrue(protocol.make_client_msg_id().startswith("m-"))
        self.assertNotEqual(protocol.make_client_msg_id(), protocol.make_client_msg_id())


class PayloadCompatTests(unittest.TestCase):
    def test_unwrap_envelope_and_bare(self) -> None:
        envelope = {"code": 200, "message": "OK", "data": {"items": []}}
        self.assertEqual(protocol.unwrap_payload(envelope), {"items": []})
        bare = {"room_code": "AB12C", "message": "ok"}
        self.assertEqual(protocol.unwrap_payload(bare), bare)
        self.assertEqual(protocol.unwrap_payload(["a"]), ["a"])

    def test_extract_token_variants(self) -> None:
        cases = [
            ({"code": 200, "data": {"access_token": "jwt-1"}}, "jwt-1"),
            ({"code": 200, "data": {"token": "jwt-2"}}, "jwt-2"),
            ({"data": {"accessToken": "jwt-3"}}, "jwt-3"),
            ({"access_token": "jwt-4"}, "jwt-4"),
            ({"code": 200, "data": {"id": 1, "username": "demo"}}, None),
            (None, None),
            ("not-a-mapping", None),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(protocol.extract_token(payload), expected)

    def test_extract_user(self) -> None:
        self.assertEqual(
            protocol.extract_user({"data": {"user": {"id": "1", "username": "alice"}}}),
            {"id": "1", "username": "alice"},
        )
        self.assertEqual(protocol.extract_user({"data": {"id": "2", "username": "bob"}}), {"id": "2", "username": "bob"})
        self.assertIsNone(protocol.extract_user({"data": {"access_token": "x"}}))
        self.assertIsNone(protocol.extract_user(None))

    def test_parse_json_message(self) -> None:
        self.assertEqual(protocol.parse_json_message('{"type":"heartbeat"}'), {"type": "heartbeat"})
        self.assertEqual(protocol.parse_json_message(b'{"type":"pong"}'), {"type": "pong"})
        self.assertIsNone(protocol.parse_json_message("not json"))
        self.assertIsNone(protocol.parse_json_message("[1,2]"))
        self.assertIsNone(protocol.parse_json_message(None))
        self.assertEqual(protocol.message_type({"type": "chat_message"}), "chat_message")
        self.assertEqual(protocol.message_type(None), "")


if __name__ == "__main__":
    unittest.main()
