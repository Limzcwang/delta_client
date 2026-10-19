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
        self.assertEqual(protocol.API_V1_REGISTER, "/api/v1/auth/register")
        self.assertEqual(protocol.API_LOGIN_LEGACY, "/api/users/login")


class WsUrlTests(unittest.TestCase):
    def test_ws_from_http(self) -> None:
        self.assertEqual(protocol.ws_url_for("http://127.0.0.1:8000"), "ws://127.0.0.1:8000/ws")

    def test_ws_from_https_with_prefix(self) -> None:
        self.assertEqual(protocol.ws_url_for("https://game.example.com/delta"), "wss://game.example.com/delta/ws")
        self.assertEqual(protocol.ws_url_for("https://deltachat.icu:8443"), "wss://deltachat.icu:8443/ws")

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
        # PR#9 §6.3：新字段 room_id_or_code，同时保留旧字段 room_code
        self.assertEqual(no_password["room_id_or_code"], "AB12C")
        self.assertEqual(no_password["room_code"], "AB12C")
        with_password = protocol.join_room_message("AB12C", "1234", request_id="c-1")
        self.assertEqual(with_password["password"], "1234")
        self.assertEqual(with_password["request_id"], "c-1")

    def test_leave_room_message(self) -> None:
        message = protocol.leave_room_message("AB12C")
        self.assertEqual(message["type"], "leave_room")
        self.assertEqual(message["room_id_or_code"], "AB12C")
        self.assertEqual(protocol.leave_room_message()["type"], "leave_room")

    def test_skill_share_update_message_with_operator(self) -> None:
        skills = [{"slot": 0, "state": "charging", "pct": 16}]
        message = protocol.skill_share_update_message(
            "AB12C", 1_700_000_000_000, skills, "honglang", "红狼"
        )
        self.assertEqual("skill_share_update", message["type"])
        self.assertEqual("AB12C", message["room_id"])
        self.assertEqual(skills, message["skills"])
        self.assertEqual("honglang", message["operator_id"])
        self.assertEqual("红狼", message["operator_name"])
        self.assertNotIn("room_id", protocol.leave_room_message())

    def test_chat_and_ping_messages(self) -> None:
        chat = protocol.chat_send_message("大家好", "m-1")
        self.assertEqual(chat, {"type": "chat_send", "client_msg_id": "m-1", "content": "大家好", "content_type": "text"})
        with_room = protocol.chat_send_message("hi", "c-1", room_id="room-9")
        self.assertEqual("room-9", with_room["room_id"])
        self.assertEqual("hi", with_room["content"])
        self.assertEqual("c-1", with_room["client_msg_id"])
        ping = protocol.ping_message(1750000000000)
        self.assertEqual(ping["type"], "ping")
        self.assertIsInstance(ping["ts"], int)

    def test_room_messages_path(self) -> None:
        self.assertEqual(protocol.room_messages_path("AB12C"), "/api/v1/rooms/AB12C/messages")
        self.assertEqual(protocol.room_messages_path("a/b"), "/api/v1/rooms/a%2Fb/messages")

    def test_canvas_messages_and_path(self) -> None:
        self.assertEqual(protocol.room_canvas_path("AB12C"), "/api/v1/rooms/AB12C/canvas")
        op = {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "color": "#FF3B30", "width": 4, "tool": "pen"}
        message = protocol.canvas_op_message("room-1", 3, op)
        self.assertEqual("canvas_op", message["type"])
        self.assertEqual("room-1", message["room_id"])
        self.assertEqual(3, message["rev"])
        self.assertEqual(op, message["op"])
        save = protocol.canvas_snapshot_save_message("room-1", 5, [op])
        self.assertEqual("canvas_snapshot_save", save["type"])
        self.assertEqual(5, save["rev"])
        self.assertEqual([op], save["strokes"])

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
