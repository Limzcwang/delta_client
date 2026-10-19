"""E3b2 识别纯逻辑 + 真实 HUD fixture（OCR/模板匹配部分按依赖 skip）。"""

from __future__ import annotations

import unittest
from pathlib import Path

from core.hud_recognition import (
    SlotRecognition,
    charged_remaining_ms,
    mask_ratio,
    parse_charge,
    parse_percent,
    parse_seconds,
    recognize_secondary,
    recognize_ultimate,
)
from core.skills import SKILL_CHARGING, SKILL_READY, SKILL_UNKNOWN

FIXTURES = Path(__file__).parent / "fixtures" / "hud"


class TextParseTests(unittest.TestCase):
    def test_percent_from_real_ocr(self) -> None:
        self.assertEqual(16, parse_percent(["2", "2", "16%"]))
        self.assertEqual(16, parse_percent(["16 %"]))
        self.assertIsNone(parse_percent(["无目标", "15秒"]))
        self.assertIsNone(parse_percent(["999%"]))

    def test_seconds_from_real_ocr(self) -> None:
        self.assertEqual(15_000, parse_seconds(["无目标", "15秒"]))
        self.assertEqual(15_000, parse_seconds(["15s"]))
        self.assertIsNone(parse_seconds(["16%"]))

    def test_charge(self) -> None:
        self.assertEqual(2, parse_charge(["2", "无目标", "15秒"]))
        self.assertEqual(1, parse_charge(["1", "四"]))
        self.assertIsNone(parse_charge(["16%", "15秒"]))

    def test_charged_formula(self) -> None:
        self.assertEqual(75_600, charged_remaining_ms(16, 90_000, "charged"))
        self.assertEqual(14_400, charged_remaining_ms(16, 90_000, "remaining"))
        self.assertEqual(0, charged_remaining_ms(100, 90_000))
        self.assertEqual(90_000, charged_remaining_ms(0, 90_000))


class SlotLogicTests(unittest.TestCase):
    def test_ultimate_percent_charged(self) -> None:
        result = recognize_ultimate(["16%"], 90_000, meaning="charged")
        self.assertEqual(SKILL_CHARGING, result.state)
        self.assertEqual(16.0, result.percent)
        self.assertEqual(75_600, result.remaining_ms)

    def test_ultimate_ready_unknown(self) -> None:
        self.assertEqual(SKILL_READY, recognize_ultimate(["100%"], 90_000).state)
        self.assertEqual(SKILL_UNKNOWN, recognize_ultimate([], 90_000).state)

    def test_secondary_seconds(self) -> None:
        result = recognize_secondary(1, ["15秒"], 70_000, 2)
        self.assertEqual(SKILL_CHARGING, result.state)
        self.assertEqual(15_000, result.remaining_ms)

    def test_secondary_charge_and_mask(self) -> None:
        ready = recognize_secondary(2, ["2"], 45_000, 2)
        self.assertEqual(SKILL_READY, ready.state)
        charge = recognize_secondary(2, ["2"], 45_000, 3)
        self.assertEqual(SKILL_UNKNOWN, charge.state)  # 只有充能数、无遮罩不猜 CD
        masked = recognize_secondary(2, ["2"], 45_000, 3, ratio=0.5)
        self.assertEqual(22_500, masked.remaining_ms)

    def test_secondary_unknown(self) -> None:
        self.assertEqual(SKILL_UNKNOWN, recognize_secondary(2, [], 45_000, 2).state)
        self.assertEqual(SKILL_UNKNOWN, recognize_secondary(2, [], 0, 2).state)

    def test_payload_omits_unknown_fields(self) -> None:
        payload = SlotRecognition(0, SKILL_UNKNOWN).to_payload()
        self.assertEqual({"slot": 0, "state": "unknown"}, payload)


class MaskRatioTests(unittest.TestCase):
    def test_synthetic_half_dark(self) -> None:
        image = [[0, 0, 255, 255], [0, 0, 255, 255]]
        self.assertEqual(0.5, mask_ratio(image, dark_threshold=70))
        self.assertEqual(0.0, mask_ratio(None))
        self.assertEqual(0.0, mask_ratio([]))

    def test_region(self) -> None:
        image = [[0, 255], [255, 255]]
        self.assertEqual(1.0, mask_ratio(image, dark_threshold=70, x=0, y=0, width=1, height=1))


class RealFixtureTests(unittest.TestCase):
    """真实截图识别（需要 site-e3 的 cv2/numpy/rapidocr；缺失时 skip）。"""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401

            cls.cv2 = cv2
            cls.np = numpy
        except Exception:  # noqa: BLE001
            raise unittest.SkipTest("E3 识别依赖未安装")

    def _read(self, name: str) -> list[str]:
        from core.hud_ocr import HudOcr

        image = self.cv2.imread(str(FIXTURES / name))
        self.assertIsNotNone(image)
        return [line.text for line in HudOcr().read_lines(image)]

    def test_real_percent_16(self) -> None:
        texts = self._read("skills2.png")
        self.assertEqual(16, parse_percent(texts), texts)

    def test_real_seconds_15(self) -> None:
        texts = self._read("skills1.png")
        self.assertEqual(15_000, parse_seconds(texts), texts)

    def test_real_charge_2(self) -> None:
        texts = self._read("skills1.png")
        self.assertEqual(2, parse_charge(texts), texts)

    def test_real_mask_ratio_range(self) -> None:
        image = self.cv2.imread(str(FIXTURES / "skills3.png"))
        ratio = mask_ratio(image, dark_threshold=70)
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)

    def test_operator_template_self_match(self) -> None:
        from core.hud_profile import Roi
        from core.operator_match import match_operator_template

        avatar = self.cv2.imread(str(Path(__file__).parents[1] / "assets" / "operators" / "honglang.png"))
        self.assertIsNotNone(avatar)
        roi = Roi(0, 0, avatar.shape[1], avatar.shape[0])
        operator_id, score = match_operator_template(
            avatar, roi, {"honglang": avatar, "weilong": avatar.copy()}, threshold=0.5
        )
        self.assertTrue(operator_id)
        self.assertGreater(score, 0.5)


if __name__ == "__main__":
    unittest.main()
