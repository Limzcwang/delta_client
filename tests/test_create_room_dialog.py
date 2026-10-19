"""创建房间对话框实时校验/失败保留表单测试（需要 PySide6，可选离屏）。

无 PySide6 的环境会跳过；CI 安装 requirements 后自动执行。
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtWidgets import QApplication

    from ui.dialogs import CreateRoomDialog

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class CreateRoomDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.dialog = CreateRoomDialog()

    def tearDown(self) -> None:
        self.dialog.deleteLater()

    def test_name_realtime_validation_and_button_state(self) -> None:
        self.assertFalse(self.dialog.create_button.isEnabled())  # 空名称禁用
        self.dialog.name_edit.setText("开黑房")
        self.assertTrue(self.dialog.create_button.isEnabled())

        self.dialog.name_edit.setText("x" * 30)
        self.assertTrue(self.dialog.create_button.isEnabled())
        self.assertIn("30/30", self.dialog.name_hint.text())

        self.dialog.name_edit.setText("x" * 31)
        self.assertFalse(self.dialog.create_button.isEnabled())
        self.assertIn("30", self.dialog.name_hint.text())

        self.dialog.name_edit.setText("开黑房")
        self.assertTrue(self.dialog.create_button.isEnabled())

    def test_private_password_realtime_validation(self) -> None:
        self.dialog.name_edit.setText("私有房")
        self.dialog.private_radio.setChecked(True)
        self.assertFalse(self.dialog.create_button.isEnabled())  # 空密码禁用

        for password in ("1", "123"):
            self.dialog.password_edit.setText(password)
            self.assertFalse(self.dialog.create_button.isEnabled())
            self.assertIn("至少 4", self.dialog.password_hint.text())

        self.dialog.password_edit.setText("1234")
        self.assertTrue(self.dialog.create_button.isEnabled())
        self.dialog.password_edit.setText("x" * 32)
        self.assertTrue(self.dialog.create_button.isEnabled())
        self.dialog.password_edit.setText("x" * 33)
        self.assertFalse(self.dialog.create_button.isEnabled())
        self.assertIn("32", self.dialog.password_hint.text())

    def test_switch_back_to_public_hides_and_clears_password(self) -> None:
        self.dialog.name_edit.setText("房间")
        self.dialog.private_radio.setChecked(True)
        self.dialog.password_edit.setText("123456")
        self.dialog.set_error("旧错误")
        self.dialog.public_radio.setChecked(True)
        self.assertFalse(self.dialog.password_edit.isVisible())
        self.assertEqual("", self.dialog.password_edit.text())
        self.assertFalse(self.dialog.error_label.isVisible())
        self.assertTrue(self.dialog.create_button.isEnabled())

    def test_failure_keeps_form_and_reenables_submit(self) -> None:
        self.dialog.name_edit.setText("失败保留房")
        self.dialog.private_radio.setChecked(True)
        self.dialog.password_edit.setText("roompass")
        emitted: list[tuple[str, str, str]] = []
        self.dialog.create_requested.connect(lambda *args: emitted.append(args))
        self.dialog._on_create_clicked()
        self.assertEqual([("失败保留房", "private", "roompass")], emitted)

        self.dialog.set_busy(True)
        self.assertFalse(self.dialog.create_button.isEnabled())
        self.dialog.set_error("网络错误")
        self.dialog.set_busy(False)
        self.assertEqual("失败保留房", self.dialog.name_edit.text())
        self.assertEqual("roompass", self.dialog.password_edit.text())
        self.assertTrue(self.dialog.create_button.isEnabled())
        self.assertIn("网络错误", self.dialog.error_label.text())


if __name__ == "__main__":
    unittest.main()
