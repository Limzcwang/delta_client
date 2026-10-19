"""干员头像自动识别接线：命中更新/持久化/面板/上报，未命中回退，缓存。"""

from __future__ import annotations

import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from core.models import Room
    from core.skills import (
        SLOT_ABILITY,
        SLOT_THROWABLE,
        SLOT_ULTIMATE,
        SkillSlot,
        SkillState,
    )
    from state.session import Session
    from ui.main_window import MainWindow

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class OperatorRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, **config):
        values = dict(use_mock=True, persist_token=False, server_migrated=False, operator_id="weilong")
        values.update(config)
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(AppConfig(**values), session)
        window._current_room = Room(id="1", code="ABC123", name="test")
        window._self_skill_state = SkillState(
            user_id="12",
            nickname="DeltaQA01",
            operator_id="weilong",
            operator="威龙",
            captured_at=1_700_000_000_000,
            slots={
                "ultimate": SkillSlot(SLOT_ULTIMATE, "ready", 0),
                "ability": SkillSlot(SLOT_ABILITY, "ready", 0, charges=1, max_charges=1),
                "throwable": SkillSlot(SLOT_THROWABLE, "ready", 0, charges=1, max_charges=1),
            },
        )
        return window

    def _close(self, window) -> None:
        window.bridge.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_hit_updates_operator_persists_panel_and_send(self) -> None:
        class FakeWs:
            connected = True

            def __init__(self):
                self.payload = None
                self.operator_id = None

            async def send_skill_update(self, *args):
                self.payload = args[2]
                self.operator_id = args[3]

        window = self._window(auto_operator_enabled=True, operator_recognition_threshold=0.83)
        fake_ws = FakeWs()
        try:
            window._ws = fake_ws
            window._skill_share_enabled = True
            with mock.patch("ui.main_window.save_config") as save, mock.patch(
                "core.operator_match.recognize_operator", return_value=("honglang", 0.83)
            ) as match:
                operator = window._recognize_operator_frame(
                    SimpleNamespace(shape=(1440, 2560, 3)), force=True
                )
            self.assertIsNotNone(operator)
            self.assertEqual("honglang", window.config.operator_id)
            self.assertEqual("honglang", window._self_skill_state.operator_id)
            self.assertEqual("红狼", window._self_skill_state.operator)
            self.assertEqual("honglang", window._recognized_operator_id)
            save.assert_called()
            self.assertEqual(0.83, match.call_args.args[3])
            for _ in range(100):
                if fake_ws.payload is not None:
                    break
                self.app.processEvents()
                time.sleep(0.01)
            self.assertIsNotNone(fake_ws.payload)
            self.assertEqual("honglang", fake_ws.operator_id)
        finally:
            self._close(window)

    def test_miss_keeps_manual_operator(self) -> None:
        window = self._window(auto_operator_enabled=True, operator_id="weilong")
        try:
            with mock.patch("ui.main_window.save_config"), mock.patch(
                "core.operator_match.recognize_operator", return_value=("", 0.31)
            ):
                operator = window._recognize_operator_frame(
                    SimpleNamespace(shape=(1440, 2560, 3)), force=True
                )
            self.assertIsNone(operator)
            self.assertEqual("weilong", window.config.operator_id)
            self.assertIn("未命中", window._operator_recognition_text)
        finally:
            self._close(window)

    def test_success_is_cached_30s(self) -> None:
        window = self._window(auto_operator_enabled=True)
        try:
            with mock.patch("ui.main_window.save_config"), mock.patch(
                "core.operator_match.recognize_operator", return_value=("honglang", 0.9)
            ) as match:
                window._recognize_operator_frame(SimpleNamespace(shape=(1440, 2560, 3)))
                window._recognize_operator_frame(SimpleNamespace(shape=(1440, 2560, 3)))
                self.assertEqual(1, match.call_count)
            self.assertEqual("honglang", window._recognized_operator_id)
        finally:
            self._close(window)

    def test_auto_disabled_does_not_recognize(self) -> None:
        window = self._window(auto_operator_enabled=False, operator_id="weilong")
        try:
            with mock.patch("core.operator_match.recognize_operator") as match:
                self.assertIsNone(window._recognize_operator_frame(SimpleNamespace(shape=(1440, 2560, 3))))
                match.assert_not_called()
        finally:
            self._close(window)

    def test_ui_threshold_persisted_before_recheck(self) -> None:
        from ui.dialogs import SettingsDialog

        window = self._window(auto_operator_enabled=True, operator_recognition_threshold=0.70)
        dialog = SettingsDialog(window.config, catalog=window.operator_catalog)
        try:
            dialog.auto_operator_check.setChecked(False)
            dialog.operator_threshold_spin.setValue(0.86)
            with mock.patch("ui.main_window.save_config") as save:
                window._apply_recognition_ui_settings(dialog)
            self.assertFalse(window.config.auto_operator_enabled)
            self.assertAlmostEqual(0.86, window.config.operator_recognition_threshold)
            save.assert_called()
            self.assertAlmostEqual(0.86, dialog.current_operator_threshold())
        finally:
            dialog.deleteLater()
            self._close(window)


if __name__ == "__main__":
    unittest.main()
