"""大厅房间列表 diff 测试（F-c3：自动刷新不整页重建的纯逻辑）。"""

from __future__ import annotations

import unittest

from core.models import Room
from core.room_list import diff_rooms, room_key, room_signature


def make_room(code: str, name: str = "", member_count: int = 1, room_id: str = "", has_password: bool = False) -> Room:
    return Room.from_api(
        {
            "id": room_id or f"id-{code}",
            "code": code,
            "name": name or f"房间 {code}",
            "member_count": member_count,
            "has_password": has_password,
        }
    )


class RoomKeyTests(unittest.TestCase):
    def test_key_prefers_id_then_code(self) -> None:
        self.assertEqual(room_key(make_room("AB12C", room_id="rid")), "rid")
        self.assertEqual(room_key(Room.from_api({"code": "AB12C"})), "AB12C")
        self.assertEqual(room_key(Room()), "")


class DiffTests(unittest.TestCase):
    def test_added_removed_updated(self) -> None:
        old = [make_room("AAAAA", "A"), make_room("BBBBB", "B")]
        new = [
            make_room("CCCCC", "C"),
            make_room("AAAAA", "A2"),          # 名称变化
            make_room("BBBBB", "B", member_count=3),  # 人数变化
        ]
        diff = diff_rooms(old, new)
        self.assertEqual(["CCCCC"], [room.code for room in diff.added])
        self.assertEqual(["AAAAA", "BBBBB"], [room.code for room in diff.updated])
        self.assertEqual([], list(diff.removed))
        self.assertEqual(["CCCCC", "AAAAA", "BBBBB"], [room.code for room in diff.order])
        self.assertTrue(diff.changed)

    def test_removed(self) -> None:
        diff = diff_rooms([make_room("AAAAA"), make_room("BBBBB")], [make_room("BBBBB")])
        self.assertEqual(["AAAAA"], [room.code for room in diff.removed])
        self.assertEqual([], list(diff.added))
        self.assertEqual([], list(diff.updated))

    def test_no_change(self) -> None:
        rooms = [make_room("AAAAA"), make_room("BBBBB")]
        diff = diff_rooms(list(rooms), list(rooms))
        self.assertFalse(diff.changed)
        self.assertEqual(rooms, list(diff.order))

    def test_has_password_change_detected(self) -> None:
        old = [make_room("AAAAA")]
        new = [Room.from_api({"id": "id-AAAAA", "code": "AAAAA", "name": "房间 AAAAA", "has_password": True})]
        diff = diff_rooms(old, new)
        self.assertEqual(["AAAAA"], [room.code for room in diff.updated])

    def test_member_changes_detected(self) -> None:
        old = [Room.from_api({"id": "r", "code": "AAAAA", "members": [{"id": "1", "nickname": "a"}]})]
        new = [Room.from_api({"id": "r", "code": "AAAAA", "members": [{"id": "1", "nickname": "b"}]})]
        self.assertNotEqual(room_signature(old[0]), room_signature(new[0]))
        self.assertEqual(1, len(diff_rooms(old, new).updated))


if __name__ == "__main__":
    unittest.main()
