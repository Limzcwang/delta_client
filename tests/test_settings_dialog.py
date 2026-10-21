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

    def test_hud_tab_has_calibration_detection_and_auto_operator(self) -> None:
        dialog = self._dialog("weilong")
        labels = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
        self.assertEqual(["采集", "悬浮窗"], labels)
        self.assertIs(dialog.tabs.widget(0).widget(), dialog.calibration_button.parent())
        self.assertTrue(dialog.auto_operator_check.isChecked())
        self.assertTrue(dialog.match_auto_check.isChecked())
        from PySide6.QtWidgets import QLabel
        self.assertTrue(dialog.overlay_auto_show_check.isChecked())
        self.assertTrue(any("反作弊" in label.text() for label in dialog.findChildren(QLabel)))
        dialog.accept()
        result = dialog.config_result()
        self.assertTrue(result.match_auto_start)
        self.assertEqual(2000, result.match_interval_ms)

    def test_server_migration_hint(self) -> None:
        dialog = self._dialog("honglang")
        self.assertTrue(dialog.server_migrated_label.isHidden())
        dialog.set_server_migrated(True)
        self.assertFalse(dialog.server_migrated_label.isHidden())

    def test_tab_switch_no_resize_or_paint_storm(self) -> None:
        from PySide6.QtCore import QEvent, QObject
        from PySide6.QtTest import QTest

        dialog = self._dialog("weilong")
        counts = {"paint": 0, "resize": 0}

        class Filter(QObject):
            def eventFilter(self, obj, event):
                if obj is dialog:
                    if event.type() == QEvent.Type.Paint:
                        counts["paint"] += 1
                    elif event.type() == QEvent.Type.Resize:
                        counts["resize"] += 1
                return False

        filt = Filter()
        dialog.installEventFilter(filt)
        try:
            dialog.show()
            QTest.qWait(200)
            before_resize = counts["resize"]
            for index in (1, 2, 0, 1, 2):
                dialog.tabs.setCurrentIndex(index)
                QTest.qWait(120)
            self.assertLessEqual(counts["resize"] - before_resize, 1)
            self.assertLess(counts["paint"], 80)
            self.assertEqual((640, 560), (dialog.width(), dialog.height()))
        finally:
            dialog.removeEventFilter(filt)

    def test_no_shortcut_sequence_widgets(self) -> None:
        dialog = self._dialog("honglang")
        from PySide6.QtWidgets import QKeySequenceEdit
        self.assertEqual([], dialog.findChildren(QKeySequenceEdit))

    def test_overlay_tab_has_no_hotkey_controls(self) -> None:
        dialog = self._dialog("honglang")
        self.assertFalse(hasattr(dialog, "shortcut_toggle_edit"))
        self.assertFalse(hasattr(dialog, "shortcut_edit_edit"))
        self.assertFalse(hasattr(dialog, "test_hotkey_button"))
        self.assertIn("反作弊", dialog.hotkey_status_label.text())

    def test_overlay_settings_persist(self) -> None:
        dialog = self._dialog("honglang")
        self.assertTrue(dialog.overlay_enabled_check.isChecked())
        dialog.overlay_enabled_check.setChecked(True)
        dialog.overlay_auto_show_check.setChecked(True)
        dialog.overlay_opacity_spin.setValue(55)
        dialog.overlay_scale_spin.setValue(1.2)
        dialog._overlay_position_reset = True
        dialog.accept()
        result = dialog.config_result()
        self.assertTrue(result.overlay_enabled)
        self.assertTrue(result.overlay_auto_show)
        self.assertEqual(55, result.overlay_opacity)
        self.assertAlmostEqual(1.2, result.overlay_scale)
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

