"""B1：成员按 user id 去重，房主+我同标签。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from core.models import Member, Room
    from ui.room_view import RoomView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装")
class MemberDedupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_same_id_different_username_collapses_and_tags_same_row(self) -> None:
        view = RoomView()
        try:
            view.set_room(Room(id="r", code="R1", name="房间", owner_id="1"))
            view.set_user("昵称我", "1")
            view.set_members([
                Member.from_api({"id": "1", "username": "owner-account", "nickname": "旧昵称", "online": True}),
                Member.from_api({"id": "1", "username": "", "nickname": "新昵称", "online": False}),
                Member.from_api({"id": "2", "username": "", "nickname": "队友"}),
            ])
            self.assertEqual(2, view.member_list.count())
            first = view.member_list.item(0).text()
            self.assertIn("新昵称", first)
            self.assertIn("房主", first)
            self.assertIn("我", first)
            self.assertNotIn("旧昵称", first)
        finally:
            view.close()
            view.deleteLater()

    def test_add_member_by_id_merges(self) -> None:
        view = RoomView()
        try:
            view.set_room(Room(id="r", code="R1", name="房间", owner_id="1"))
            view.add_member(Member.from_api({"id": "1", "username": "a", "nickname": "旧"}))
            view.add_member(Member.from_api({"id": "1", "username": "", "nickname": "新"}))
            self.assertEqual(1, view.member_list.count())
            self.assertIn("新", view.member_list.item(0).text())
        finally:
            view.close()
            view.deleteLater()


if __name__ == "__main__":
    unittest.main()
