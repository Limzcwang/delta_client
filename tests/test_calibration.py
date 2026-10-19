"""E3b1 标定对话框/ROI 等分测试（PySide6，离屏）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from core.hud_profile import HudProfile, Roi
    from ui.calibration_dialog import HudCalibrationDialog

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False

FIXTURE = Path(__file__).parent / "fixtures" / "hud" / "skills1.png"


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_select_bar_and_split(self) -> None:
        image = QImage(str(FIXTURE))
        self.assertFalse(image.isNull())
        dialog = HudCalibrationDialog(image, HudProfile())
        try:
            dialog.set_selection(Roi(10, 10, 150, 80))
            profile = dialog.result_profile()
            self.assertEqual((10, 10, 150, 80), profile.skill_bar.as_tuple())
            slots = profile.slot_rois()
            self.assertEqual(3, len(slots))
            self.assertEqual(150, sum(roi.width for roi in slots) + 0)
            self.assertEqual(slots[0].x, 10)
            self.assertEqual(slots[-1].right, 160)
            self.assertIn("技能栏", dialog.info_label.text())
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_save_reload_and_export(self) -> None:
        dialog = HudCalibrationDialog(QImage(str(FIXTURE)), HudProfile())
        try:
            dialog.set_selection(Roi(20, 30, 180, 90))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "profile.json"
                dialog.result_profile().save(path)
                loaded = HudProfile.load(path)
                self.assertEqual((20, 30, 180, 90), loaded.skill_bar.as_tuple())
                self.assertEqual(3, len(loaded.slot_rois()))
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
