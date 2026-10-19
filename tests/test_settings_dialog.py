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
        self.assertEqual(16, dialog.operator_combo.count())
        self.assertEqual("weilong", dialog.operator_combo.currentData())
        self.assertIn("威龙", dialog.operator_combo.currentText())
        self.assertIn("虎蹲炮", dialog.operator_detail_label.text())

    def test_switch_and_result_operator_id(self) -> None:
        dialog = self._dialog("honglang")
        index = dialog.operator_combo.findData("muyangren")
        self.assertGreaterEqual(index, 0)
        dialog.operator_combo.setCurrentIndex(index)
        self.assertEqual("muyangren", dialog.operator_combo.currentData())
        self.assertIn("CD未知", dialog.operator_detail_label.text())
        dialog.accept()
        self.assertEqual("muyangren", dialog.config_result().operator_id)

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
