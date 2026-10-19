"""数据模型与解析容错测试（离线）。"""

from __future__ import annotations

import unittest

from core.models import (
    ChatMessage,
    Member,
    Room,
    format_timestamp,
    make_system_message,
    now_ms,
    parse_members,
    parse_room_detail,
    parse_room_list,
    parse_ts,
)


class TimestampTests(unittest.TestCase):
    def test_parse_ts(self) -> None:
        self.assertEqual(parse_ts(1750000000000), 1750000000000)
        self.assertEqual(parse_ts("1750000000000"), 1750000000000)
        self.assertIsNone(parse_ts(None))
        self.assertIsNone(parse_ts("not-a-time"))
        self.assertIsNone(parse_ts(0))
        iso = parse_ts("2026-10-19T12:00:00+00:00")
        self.assertIsInstance(iso, int)

    def test_format_timestamp(self) -> None:
        self.assertRegex(format_timestamp(1750000000000), r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual(format_timestamp(None), "")
        self.assertEqual(format_timestamp("junk"), "")

    def test_now_ms(self) -> None:
        self.assertGreater(now_ms(), 1_600_000_000_000)


class RoomTests(unittest.TestCase):
    def test_target_room_summary(self) -> None:
        room = Room.from_api(
            {
                "id": "01J8Z9K3Q7",
                "code": "a1b2c",
                "name": "开黑房",
                "owner_id": "1",
                "member_count": 3,
                "has_password": True,
                "created_at": 1750000000000,
                "background_id": "bg_default_01",
            }
        )
        self.assertEqual(room.id, "01J8Z9K3Q7")
        self.assertEqual(room.code, "A1B2C")
        self.assertEqual(room.name, "开黑房")
        self.assertEqual(room.owner_id, "1")
        self.assertEqual(room.member_count, 3)
        self.assertTrue(room.has_password)
        self.assertEqual(room.background_id, "bg_default_01")
        self.assertEqual(room.display_name, "开黑房")
        self.assertRegex(room.created_text, r"^\d{2}:\d{2}:\d{2}$")

    def test_legacy_room_info(self) -> None:
        room = Room.from_api(
            {
                "room_code": "AB12C",
                "domain": 2,
                "creator": 7,
                "members_count": 2,
                "created_at": "2026-10-19T12:00:00",
            }
        )
        self.assertEqual(room.code, "AB12C")
        self.assertTrue(room.has_password)
        self.assertEqual(room.owner_id, "7")
        self.assertEqual(room.member_count, 2)
        self.assertEqual(room.display_name, "房间 AB12C")

    def test_room_with_members_and_background(self) -> None:
        room = Room.from_api(
            {
                "id": "r1",
                "code": "AB12C",
                "name": "房",
                "member_count": 2,
                "background": {"id": "bg_02", "url": "https://cdn/bg.png", "width": 1920, "height": 1080},
                "members": [{"id": "1", "username": "alice", "online": True}, {"id": "2", "username": "bob"}],
            }
        )
        self.assertEqual(room.background_id, "bg_02")
        self.assertEqual(len(room.members), 2)
        self.assertTrue(room.has_members)
        self.assertTrue(room.members[0].online)
        self.assertEqual(room.members[1].display_name, "bob")

    def test_invalid_payload_does_not_crash(self) -> None:
        room = Room.from_api({"code": None, "member_count": "bad"})
        self.assertEqual(room.code, "")
        self.assertEqual(room.member_count, 0)
        self.assertEqual(Room.from_api({}).display_name, "未命名房间")


class ParseListTests(unittest.TestCase):
    def test_variants(self) -> None:
        item = {"code": "AB12C", "name": "a"}
        for payload in (
            [item],
            {"items": [item]},
            {"rooms": [item]},
            {"data": {"items": [item]}},
            {"data": [item]},
        ):
            with self.subTest(payload=payload):
                rooms = parse_room_list(payload)
                self.assertEqual(len(rooms), 1)
                self.assertEqual(rooms[0].code, "AB12C")

    def test_invalid_entries_filtered(self) -> None:
        rooms = parse_room_list({"items": [{"code": "AB12C"}, "junk", None]})
        self.assertEqual(len(rooms), 1)
        self.assertEqual(parse_room_list(None), [])
        self.assertEqual(parse_room_list({"other": []}), [])

    def test_members(self) -> None:
        members = parse_members({"members": [{"id": "1", "username": "a"}]})
        self.assertEqual(len(members), 1)
        self.assertIsInstance(members[0], Member)
        self.assertEqual(parse_members({"members": "bad"}), [])


class ParseRoomDetailTests(unittest.TestCase):
    def test_envelope_detail(self) -> None:
        detail = parse_room_detail(
            {
                "code": 200,
                "message": "OK",
                "data": {
                    "room": {"id": "r1", "code": "ab12c", "name": "开黑房", "member_count": 2},
                    "members": [
                        {"id": "1", "username": "alice", "online": True},
                        {"id": "2", "username": "bob", "online": False},
                    ],
                },
            }
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.room.code, "AB12C")
        self.assertEqual(len(detail.members), 2)
        self.assertTrue(detail.members[0].online)
        self.assertFalse(detail.members[1].online)
        self.assertEqual(detail.member_names, ("alice", "bob"))

    def test_bare_detail_and_room_members_fallback(self) -> None:
        detail = parse_room_detail(
            {
                "room": {
                    "code": "AB12C",
                    "members": [{"id": "1", "username": "alice"}],
                },
                "members": [],
            }
        )
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual([m.username for m in detail.members], ["alice"])

    def test_invalid_payload(self) -> None:
        self.assertIsNone(parse_room_detail(None))
        self.assertIsNone(parse_room_detail("junk"))
        self.assertIsNone(parse_room_detail([]))


class ChatMessageTests(unittest.TestCase):
    def test_from_ws(self) -> None:
        message = ChatMessage.from_ws(
            {
                "type": "chat_message",
                "message_id": "msg_1",
                "client_msg_id": "m-1",
                "sender": {"id": "1", "username": "alice"},
                "content": "大家好",
                "ts": 1750000001500,
            }
        )
        self.assertEqual(message.sender_name, "alice")
        self.assertEqual(message.content, "大家好")
        self.assertEqual(message.client_msg_id, "m-1")
        self.assertIn("alice", message.display_text())
        self.assertIn("大家好", message.display_text())
        self.assertRegex(message.time_text, r"^\d{2}:\d{2}:\d{2}$")

    def test_from_ws_missing_sender(self) -> None:
        message = ChatMessage.from_ws({"content": "hi"})
        self.assertEqual(message.sender_name, "未知用户")

    def test_system_message_display(self) -> None:
        message = make_system_message("已加入房间")
        self.assertTrue(message.system)
        self.assertEqual(message.display_text(), "— 已加入房间 —")


if __name__ == "__main__":
    unittest.main()
