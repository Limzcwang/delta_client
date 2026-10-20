"""E3a：设置页干员下拉/保存/重启保留测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtWidgets import QApplication

    from config import AppConfig, load_config, save_config
    from core.operators import load_operator_catalog
    from ui.dialogs import SettingsDialog

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class SettingsOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.dialogs: list[SettingsDialog] = []
        self.catalog = load_operator_catalog()

    def tearDown(self) -> None:
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        self.app.processEvents()

    def _dialog(self, operator_id: str) -> SettingsDialog:
        dialog = SettingsDialog(
            AppConfig(operator_id=operator_id), catalog=self.catalog
        )
        self.dialogs.append(dialog)
        return dialog

    def test_dropdown_has_16_operators_and_selects_saved(self) -> None:
        dialog = self._dialog("weilong")
        self.assertEqual(3, dialog.tabs.count())
        self.assertEqual(17, dialog.operator_combo.count())
        self.assertEqual("weilong", dialog.operator_combo.currentData())
        self.assertIn("威龙", dialog.operator_combo.currentText())
        self.assertIn("虎蹲炮", dialog.operator_detail_label.text())
        from PySide6.QtWidgets import QLabel

        self.assertTrue(
            any("版本 v0.2.3" in label.text() for label in dialog.findChildren(QLabel))
        )

    def test_hud_tab_has_calibration_detection_and_auto_operator(self) -> None:
        dialog = self._dialog("weilong")
        labels = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        self.assertEqual(["HUD / 采屏", "干员", "悬浮窗"], labels)
        self.assertEqual(dialog.tabs.widget(0), dialog.calibration_button.parent())
        self.assertIsNotNone(dialog.calibration_button)
        self.assertIsNotNone(dialog.detect_window_button)
        self.assertTrue(dialog.auto_operator_check.isChecked())
        self.assertAlmostEqual(0.65, dialog.operator_threshold_spin.value())
        self.assertFalse(dialog.hud_debug_check.isChecked())
        self.assertEqual(140, dialog.brightness_spin.value())
        self.assertIn("亮度阈值", dialog.hud_profile_label.text())
        self.assertIn("skill_bar", dialog.hud_profile_label.text())
        self.assertIn("avatar_roi", dialog.hud_profile_label.text())
        dialog.hud_debug_check.setChecked(True)
        dialog.brightness_spin.setValue(155)
        dialog.auto_operator_check.setChecked(False)
        dialog.operator_threshold_spin.setValue(0.83)
        dialog.accept()
        result = dialog.config_result()
        self.assertFalse(result.auto_operator_enabled)
        self.assertTrue(result.hud_debug_export)
        self.assertAlmostEqual(0.83, result.operator_recognition_threshold)
        self.assertEqual(155, result.hud_profile["brightness_threshold"])

    def test_config_center_labels_and_check_button(self) -> None:
        from types import SimpleNamespace

        manager = SimpleNamespace(
            state=SimpleNamespace(version="v3", source_label="服务器", updated_at="2026-10-20")
        )
        dialog = SettingsDialog(
            AppConfig(server_migrated=False),
            catalog=self.catalog,
            config_manager=manager,
        )
        self.dialogs.append(dialog)
        self.assertIn("v3", dialog.config_version_label.text())
        self.assertIn("服务器", dialog.config_source_label.text())
        self.assertIn("2026-10-20", dialog.config_updated_label.text())
        events: list[bool] = []
        dialog.config_check_requested.connect(lambda: events.append(True))
        dialog.check_config_button.click()
        self.assertEqual([True], events)
        dialog.set_config_check_result("已是最新", ok=True)
        self.assertIn("已是最新", dialog.config_check_result.text())

    def test_server_migration_hint(self) -> None:
        dialog = self._dialog("honglang")
        self.assertTrue(dialog.server_migrated_label.isHidden())
        dialog.set_server_migrated(True)
        self.assertFalse(dialog.server_migrated_label.isHidden())

    def test_switch_and_result_operator_id(self) -> None:
        dialog = self._dialog("honglang")
        index = dialog.operator_combo.findData("muyangren")
        self.assertGreaterEqual(index, 0)
        dialog.operator_combo.setCurrentIndex(index)
        self.assertEqual("muyangren", dialog.operator_combo.currentData())
        self.assertIn("CD未知", dialog.operator_detail_label.text())
        dialog.accept()
        self.assertEqual("muyangren", dialog.config_result().operator_id)

    def test_overlay_settings_persist(self) -> None:
        dialog = self._dialog("honglang")
        self.assertFalse(dialog.overlay_enabled_check.isChecked())
        dialog.overlay_enabled_check.setChecked(True)
        dialog.overlay_opacity_spin.setValue(55)
        dialog.overlay_scale_spin.setValue(1.2)
        dialog.shortcut_toggle_edit.setKeySequence("Ctrl+Alt+D")
        dialog.shortcut_edit_edit.setKeySequence("Ctrl+Alt+E")
        dialog.set_hotkey_status("快捷键被其他程序占用，请换一个：F9")
        self.assertIn("占用", dialog.hotkey_status_label.text())
        dialog._overlay_position_reset = True
        dialog.accept()
        result = dialog.config_result()
        self.assertTrue(result.overlay_enabled)
        self.assertEqual(55, result.overlay_opacity)
        self.assertAlmostEqual(1.2, result.overlay_scale)
        self.assertEqual("Ctrl+Alt+D", result.shortcut_toggle)
        self.assertEqual("Ctrl+Alt+E", result.shortcut_edit)
        self.assertIsNone(result.overlay_x)
        self.assertIsNone(result.overlay_y)

    def test_capture_window_selection_persist(self) -> None:
        dialog = self._dialog("honglang")
        dialog._capture_process = "DeltaForceClient-Win64-Shipping.exe"
        dialog._capture_title = "三角洲行动"
        dialog.accept()
        result = dialog.config_result()
        self.assertEqual("DeltaForceClient-Win64-Shipping.exe", result.capture_window_process)
        self.assertEqual("三角洲行动", result.capture_window_title)

    def test_operator_recognition_status(self) -> None:
        dialog = self._dialog("weilong")
        dialog.set_operator_recognition_status("当前识别：红狼（置信度 0.83）")
        self.assertIn("红狼", dialog.operator_recognition_label.text())

    def test_overlay_shortcut_conflict_rejected(self) -> None:
        dialog = self._dialog("honglang")
        dialog.shortcut_toggle_edit.setKeySequence("Ctrl+Shift+X")
        dialog.shortcut_edit_edit.setKeySequence("Ctrl+Shift+X")
        dialog.accept()
        self.assertFalse(dialog.error_label.isHidden())
        self.assertIn("不能相同", dialog.error_label.text())

    def test_invalid_saved_falls_back_and_persists(self) -> None:
        dialog = self._dialog("no-such-operator")
        self.assertEqual("honglang", dialog.operator_combo.currentData())
        dialog.accept()
        result = dialog.config_result()
        self.assertEqual("honglang", result.operator_id)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config.json"
            save_config(result, target)
            reloaded = load_config(path=target, env={})
            self.assertEqual("honglang", reloaded.operator_id)


if __name__ == "__main__":
    unittest.main()





