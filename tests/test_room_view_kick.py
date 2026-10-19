"""右键菜单：成员列表行渲染与「移出房间」菜单状态测试（PySide6，离屏）。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from core.models import Member, Room
    from ui.room_view import RoomView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class RoomViewMemberMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._views: list[RoomView] = []

    def tearDown(self) -> None:
        for view in self._views:
            view.close()
            view.deleteLater()
        self.app.processEvents()

    def _view(self, user_id: str, owner_id: str = "1", members=None) -> RoomView:
        view = RoomView()
        self._views.append(view)
        view.set_room(Room(id="room-1", code="AB12C", name="测试房", owner_id=owner_id))
        view.set_user("当前用户", user_id)
        view.set_members(
            members
            if members is not None
            else [
                Member.from_api({"id": "1", "nickname": "房主"}),
                Member.from_api({"id": "2", "nickname": "成员A"}),
                Member.from_api({"id": "3", "nickname": "成员B"}),
            ]
        )
        return view

    def test_rows_render_without_inline_widgets(self) -> None:
        view = self._view("1")
        self.assertEqual(3, view.member_list.count())
        for row in range(view.member_list.count()):
            item = view.member_list.item(row)
            self.assertEqual(40, item.sizeHint().height())
            self.assertIsNone(view.member_list.itemWidget(item))
        self.assertEqual(Qt.TextElideMode.ElideRight, view.member_list.textElideMode())
        self.assertEqual(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            view.member_list.horizontalScrollBarPolicy(),
        )

    def test_long_nickname_has_tooltip_and_fixed_height(self) -> None:
        long_name = "超长昵称" * 20 + "😀"
        view = self._view(
            "1",
            members=[
                Member.from_api({"id": "1", "nickname": "房主"}),
                Member.from_api({"id": "2", "nickname": long_name, "online": False}),
            ],
        )
        item = view.member_list.item(1)
        self.assertEqual(40, item.sizeHint().height())
        self.assertIn(long_name, item.toolTip())

    def test_owner_menu_enabled_only_for_other_members(self) -> None:
        view = self._view("1")
        owner_menu = view.build_member_menu(view.member_list.item(0))
        member_menu = view.build_member_menu(view.member_list.item(1))
        self.assertEqual(["移出房间"], [action.text() for action in owner_menu.actions()])
        self.assertFalse(owner_menu.actions()[0].isEnabled())  # 目标是我/房主
        self.assertTrue(member_menu.actions()[0].isEnabled())

    def test_non_owner_menu_disabled(self) -> None:
        view = self._view("2")
        for row in range(view.member_list.count()):
            menu = view.build_member_menu(view.member_list.item(row))
            self.assertFalse(menu.actions()[0].isEnabled())

    def test_enabled_action_emits_user_id_and_nickname(self) -> None:
        view = self._view("1")
        received: list[tuple[str, str]] = []
        view.kick_requested.connect(lambda uid, name: received.append((uid, name)))
        menu = view.build_member_menu(view.member_list.item(1))
        menu.actions()[0].trigger()
        self.assertEqual([("2", "成员A")], received)

    def test_disabled_action_does_not_emit(self) -> None:
        view = self._view("1")
        received: list[tuple[str, str]] = []
        view.kick_requested.connect(lambda uid, name: received.append((uid, name)))
        menu = view.build_member_menu(view.member_list.item(0))
        menu.actions()[0].trigger()
        self.assertEqual([], received)


if __name__ == "__main__":
    unittest.main()
