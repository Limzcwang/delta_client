"""技能图标优先识别：真实截图裁剪模板 fixture、未命中降级、遮罩/配置充能。"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.hud_pipeline import recognize_frame
from core.hud_profile import HudProfile, Roi
from core.operators import Operator, OperatorSkill

try:  # pragma: no cover
    import cv2
    import numpy as np

    from core.skill_icons import load_skill_icon_templates, skill_icon_dir

    HAS_CV = True
except Exception:  # noqa: BLE001
    HAS_CV = False


class _EmptyOcr:
    def read_lines(self, _image):
        return []


@unittest.skipUnless(HAS_CV, "opencv/numpy 未安装，跳过图标模板测试")
class SkillIconRecognitionTests(unittest.TestCase):
    def _operator(self) -> Operator:
        skills = {
            0: OperatorSkill(slot=0, name="大招", total_cd_ms=90_000, max_charges=1),
            1: OperatorSkill(slot=1, name="技能", total_cd_ms=30_000, max_charges=3),
            2: OperatorSkill(slot=2, name="投掷物", total_cd_ms=20_000, max_charges=2),
        }
        return Operator(id="fengyi", name="蜂医", skills=skills)

    def _profile(self) -> HudProfile:
        slots = [Roi(18, 35, 66, 70), Roi(86, 35, 72, 70), Roi(162, 35, 72, 70)]
        return HudProfile(
            client_width=290,
            client_height=147,
            skill_bar=Roi(10, 30, 260, 90),
            slots=[roi.to_dict() for roi in slots],
            skill_icon_threshold=0.70,
        )

    def _frame(self):
        templates = load_skill_icon_templates("fengyi")
        self.assertEqual(3, len(templates))
        frame = np.zeros((147, 290, 3), dtype=np.uint8)
        for index, roi in enumerate(self._profile().slot_rois()):
            template = templates[index]
            image = cv2.resize(template, (roi.width, roi.height))
            frame[roi.y : roi.bottom, roi.x : roi.right] = image
        return frame

    def test_real_templates_match_all_slots(self) -> None:
        result = recognize_frame(self._frame(), self._profile(), operator=self._operator(), ocr=_EmptyOcr())
        self.assertEqual(3, len(result.diagnostics))
        for diagnostic in result.diagnostics:
            self.assertGreaterEqual(diagnostic.icon_score, 0.70, diagnostic.reason)
            self.assertNotEqual("unknown", diagnostic.state, diagnostic.reason)
        self.assertEqual(3, result.slots["ability"].max_charges)
        self.assertEqual(2, result.slots["throwable"].max_charges)

    def test_icon_miss_degrades_unknown(self) -> None:
        frame = np.zeros((147, 290, 3), dtype=np.uint8)
        result = recognize_frame(frame, self._profile(), operator=self._operator(), ocr=_EmptyOcr())
        for diagnostic in result.diagnostics:
            self.assertEqual("unknown", diagnostic.state)
            self.assertIn("图标未命中", diagnostic.reason)

    def test_ultimate_without_percent_uses_mask(self) -> None:
        result = recognize_frame(self._frame(), self._profile(), operator=self._operator(), ocr=_EmptyOcr())
        ultimate = result.diagnostics[0]
        self.assertNotEqual("unknown", ultimate.state)
        self.assertIn(ultimate.state, ("ready", "charging", "unknown"))
        self.assertIsInstance(result.slots["ultimate"].remaining_ms, int)


if __name__ == "__main__":
    unittest.main()

