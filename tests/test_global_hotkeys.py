"""全局热键：解析、注册/注销、失败回退、消息分发。"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from ui.global_hotkeys import (
        HOTKEY_EDIT_ID,
        HOTKEY_TOGGLE_ID,
        MOD_ALT,
        MOD_CONTROL,
        MOD_SHIFT,
        GlobalHotkeyManager,
        parse_hotkey,
    )

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


class HotkeyParseTests(unittest.TestCase):
    def test_parse_supported(self) -> None:
        self.assertEqual(0x70, parse_hotkey("F1").vk)
        self.assertEqual(0x78, parse_hotkey("F9").vk)
        self.assertEqual(ord("D"), parse_hotkey("Ctrl+Shift+D").vk)
        spec = parse_hotkey("Ctrl+Alt+F9")
        self.assertEqual(MOD_CONTROL | MOD_ALT, spec.modifiers)
        self.assertEqual(ord("1"), parse_hotkey("Alt+1").vk)

    def test_parse_rejects_invalid(self) -> None:
        self.assertIsNone(parse_hotkey(""))
        self.assertIsNone(parse_hotkey("Ctrl"))
        self.assertIsNone(parse_hotkey("Ctrl+D+E"))
        self.assertIsNone(parse_hotkey("F13"))
        self.assertIsNone(parse_hotkey("Ctrl+Shift+F13"))


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class HotkeyManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_register_unregister_and_trigger(self) -> None:
        manager = GlobalHotkeyManager()
        seen: list[str] = []
        manager.triggered.connect(seen.append)
        try:
            with mock.patch("ui.global_hotkeys.register_hotkey", return_value=True) as register, mock.patch(
                "ui.global_hotkeys.unregister_hotkey"
            ) as unregister:
                failures = manager.register_all("F9", "Ctrl+Shift+E")
                self.assertEqual({}, failures)
                self.assertEqual({"toggle", "edit"}, manager.registered_actions)
                self.assertEqual(2, register.call_count)
                self.assertTrue(manager.handle_message(0x0312, HOTKEY_TOGGLE_ID))
                self.assertTrue(manager.handle_message(0x0312, HOTKEY_EDIT_ID))
                self.assertEqual(["toggle", "edit"], seen)
                manager.register_all("F10", "Ctrl+Shift+E")
                self.assertGreaterEqual(unregister.call_count, 2)
        finally:
            manager.stop()

    def test_register_logs_action_key_and_error_code(self) -> None:
        manager = GlobalHotkeyManager()
        try:
            with mock.patch("ui.global_hotkeys.register_hotkey", return_value=False), self.assertLogs(
                "ui.global_hotkeys", level="INFO"
            ) as captured:
                failures = manager.register_all("F9", "Ctrl+Shift+E")
            self.assertIn("action=toggle", "\n".join(captured.output))
            self.assertIn("success=False", "\n".join(captured.output))
            self.assertIn("错误码", failures["toggle"])
            self.assertIn("占用", failures["toggle"])
        finally:
            manager.stop()

    def test_occupied_falls_back_and_reports(self) -> None:
        manager = GlobalHotkeyManager()
        try:
            with mock.patch(
                "ui.global_hotkeys.register_hotkey", side_effect=[False, True]
            ):
                failures = manager.register_all("F9", "Ctrl+Shift+E")
            self.assertIn("toggle", failures)
            self.assertIn("占用", failures["toggle"])
            self.assertNotIn("edit", failures)
            self.assertEqual({"edit"}, manager.registered_actions)
        finally:
            manager.stop()


if __name__ == "__main__":
    unittest.main()
