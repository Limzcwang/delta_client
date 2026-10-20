"""队伍编号 ROI/OCR/域过滤测试。"""

from __future__ import annotations

import unittest

from core.hud_profile import HudProfile, Roi
from core.skills import SkillState
from core.squad_number import crop_self_avatar_number, number_roi, parse_squad_number, recognize_squad_number


class FakeCrop:
    shape = (30, 29, 3)


class FakeFrame:
    def __getitem__(self, _key):
        return FakeCrop()


class FakeLine:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeOcr:
    def __init__(self, text: str) -> None:
        self.text = text

    def read_lines(self, _image):
        return [FakeLine(self.text)]


class SquadNumberTests(unittest.TestCase):
    def test_default_roi_and_crop(self) -> None:
        profile = HudProfile()
        self.assertEqual((36, 1280, 88, 90), profile.self_avatar_roi.as_tuple())
        roi = number_roi(profile)
        self.assertEqual((36, 1280, 29, 30), roi.as_tuple())
        frame = FakeFrame()
        crop = crop_self_avatar_number(frame, profile)
        self.assertEqual((30, 29, 3), crop.shape)

    def test_parse_only_1_2_3(self) -> None:
        for text in ("1", "2", "3", " 2 "):
            self.assertEqual(int(text.strip()), parse_squad_number([text]))
        for text in ("0", "4", "9", "12", "23", "", "abc"):
            self.assertIsNone(parse_squad_number([text]))

    def test_ocr_recognizes_each_valid(self) -> None:
        frame = FakeFrame()
        for text in ("1", "2", "3"):
            self.assertEqual(int(text), recognize_squad_number(FakeOcr(text), frame, HudProfile()))

    def test_ocr_rejects_out_of_domain(self) -> None:
        frame = FakeFrame()
        for text in ("0", "4", "12"):
            self.assertIsNone(recognize_squad_number(FakeOcr(text), frame, HudProfile()))

    def test_skill_state_filters_domain(self) -> None:
        self.assertEqual(1, SkillState.from_ws({"squad_number": 1}).squad_number)
        self.assertEqual(3, SkillState.from_ws({"squadNumber": "3"}).squad_number)
        self.assertIsNone(SkillState.from_ws({"squad_number": 0}).squad_number)
        self.assertIsNone(SkillState.from_ws({"squad_number": 4}).squad_number)
        self.assertIsNone(SkillState.from_ws({"squad_number": 12}).squad_number)


if __name__ == "__main__":
    unittest.main()
