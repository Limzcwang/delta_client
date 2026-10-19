"""E3b1 标定对话框/ROI 等分测试（PySide6，离屏）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication, QLabel

    from core.hud_profile import HudProfile, Roi
    from capture.window import WindowCandidate
    from ui.calibration_dialog import HudCalibrationDialog
    from ui.window_picker import WindowPickerDialog

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

    def test_qimage_from_bgr_and_noncontiguous(self) -> None:
        try:
            import numpy as np
        except Exception:  # noqa: BLE001
            self.skipTest("numpy 未安装")
        from ui.calibration_dialog import qimage_from_frame

        frame = np.zeros((2, 3, 3), dtype=np.uint8)
        frame[0, 0] = [0, 0, 255]  # BGR 红
        frame[1, 2] = [255, 0, 0]  # BGR 蓝
        image = qimage_from_frame(frame)
        self.assertFalse(image.isNull())
        self.assertEqual(3, image.width())
        self.assertEqual(2, image.height())
        self.assertEqual("#ff0000", image.pixelColor(0, 0).name().lower())

        rgba = np.zeros((2, 3, 4), dtype=np.uint8)
        rgba[0, 1] = [0, 255, 0, 255]
        sliced = rgba[:, :, :3]
        self.assertFalse(sliced.flags["C_CONTIGUOUS"])
        image2 = qimage_from_frame(sliced)
        self.assertFalse(image2.isNull())
        self.assertEqual("#00ff00", image2.pixelColor(1, 0).name().lower())

    def test_null_preview_shows_error_and_refresh(self) -> None:
        dialog = HudCalibrationDialog(object(), HudProfile())
        try:
            self.assertTrue(dialog.preview._pixmap.isNull())
            labels = [label.text() for label in dialog.findChildren(QLabel)]
            self.assertTrue(any("预览生成失败" in text for text in labels))
            self.assertTrue(dialog.refresh_button.text())
            dialog._request_refresh()
            self.assertTrue(dialog.refresh_requested)
        finally:
            dialog.close()
            dialog.deleteLater()
            self.app.processEvents()

    def test_window_picker_lists_and_selects(self) -> None:
        candidates = [
            WindowCandidate(1, 100, "三角洲行动", "DeltaForceClient-Win64-Shipping.exe", 0, 0, 2560, 1440),
            WindowCandidate(2, 200, "浏览器", "chrome.exe", 0, 0, 1200, 800),
        ]
        dialog = WindowPickerDialog(candidates)
        try:
            self.assertEqual(2, dialog.list_widget.count())
            self.assertEqual(100, dialog.selected_candidate().pid)
            dialog.list_widget.setCurrentRow(1)
            self.assertEqual(200, dialog.selected_candidate().pid)
            self.assertIn("三角洲行动", dialog.list_widget.item(0).text())
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

