"""H3 成员列表「移出」按钮可见性/参数测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtWidgets import QApplication, QPushButton

    from core.models import Member, Room
    from ui.room_view import RoomView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class RoomViewKickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self, user_id: str, owner_id: str = "1") -> RoomView:
        view = RoomView()
        self._views.append(view)
        view.set_room(Room(id="room-1", code="AB12C", name="测试房", owner_id=owner_id))
        view.set_user("当前用户", user_id)
        view.set_members(
            [
                Member.from_api({"id": "1", "nickname": "房主"}),
                Member.from_api({"id": "2", "nickname": "成员A"}),
                Member.from_api({"id": "3", "nickname": "成员B"}),
            ]
        )
        return view

    def setUp(self) -> None:
        self._views: list[RoomView] = []

    def tearDown(self) -> None:
        for view in self._views:
            view.close()
            view.deleteLater()
        self.app.processEvents()

    @staticmethod
    def _buttons(view: RoomView) -> list[QPushButton]:
        buttons: list[QPushButton] = []
        for row in range(view.member_list.count()):
            widget = view.member_list.itemWidget(view.member_list.item(row))
            if widget is not None:
                buttons.extend(widget.findChildren(QPushButton))
        return buttons

    def test_owner_sees_buttons_only_for_non_owner_members(self) -> None:
        view = self._view("1")
        buttons = self._buttons(view)
        self.assertEqual(2, len(buttons))  # 成员A/B，房主自己没有
        self.assertTrue(all(button.text() == "移出" for button in buttons))

    def test_non_owner_sees_no_kick_buttons(self) -> None:
        view = self._view("2")
        self.assertEqual([], self._buttons(view))

    def test_click_emits_user_id_and_nickname(self) -> None:
        view = self._view("1")
        received: list[tuple[str, str]] = []
        view.kick_requested.connect(lambda uid, name: received.append((uid, name)))
        buttons = self._buttons(view)
        buttons[0].click()
        self.assertEqual([("2", "成员A")], received)


if __name__ == "__main__":
    unittest.main()
