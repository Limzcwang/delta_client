"""E3b2 识别流水线（可注入 OCR）测试。"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.hud_pipeline import RecognitionFrame, recognize_frame, to_skill_state
from core.hud_profile import HudProfile
from core.operators import load_operator_catalog
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState


class FakeOcr:
    def read_lines(self, image):
        return []


class PipelineTests(unittest.TestCase):
    def test_recognizes_three_slots(self) -> None:
        catalog = load_operator_catalog()
        profile = HudProfile()
        with patch(
            "core.hud_pipeline.read_skill_bar_texts",
            return_value=[["16%"], ["15秒"], ["2"]],
        ):
            result = recognize_frame(
                [[[0, 0, 0]]], profile, operator=catalog.get("honglang"), ocr=FakeOcr()
            )
        self.assertEqual("honglang", result.operator_id)
        self.assertEqual("charged", profile.ult_pct_meaning)
        self.assertEqual("charging", result.slots[SLOT_ULTIMATE].state)
        self.assertEqual(16.0, result.slots[SLOT_ULTIMATE].percent)
        self.assertEqual(75_600, result.slots[SLOT_ULTIMATE].remaining_ms)
        self.assertEqual(15_000, result.slots[SLOT_ABILITY].remaining_ms)
        self.assertEqual(2, result.slots[SLOT_THROWABLE].charges)

    def test_unknown_cd_slots_stay_unknown(self) -> None:
        catalog = load_operator_catalog()
        profile = HudProfile()
        with patch("core.hud_pipeline.read_skill_bar_texts", return_value=[["10%"], ["2"], ["2"]]):
            result = recognize_frame(
                [[[0, 0, 0]]], profile, operator=catalog.get("wuming"), ocr=FakeOcr()
            )
        self.assertEqual("unknown", result.slots[SLOT_THROWABLE].state)

    def test_to_skill_state(self) -> None:
        from core.hud_recognition import SlotRecognition

        recognized = RecognitionFrame(
            slots={
                SLOT_ULTIMATE: SlotRecognition(0, "charging", remaining_ms=10, percent=20),
                SLOT_ABILITY: SlotRecognition(1, "unknown"),
                SLOT_THROWABLE: SlotRecognition(2, "ready"),
            },
            operator_id="honglang",
            operator_name="红狼",
        )
        state = to_skill_state(recognized, user_id="1", nickname="我", captured_at=123)
        self.assertIsInstance(state, SkillState)
        self.assertEqual("honglang", state.operator_id)
        self.assertEqual(20.0, state.slot("ultimate").percent)
        self.assertEqual("unknown", state.slot("ability").state)

    def test_empty_frame_does_not_raise(self) -> None:
        result = recognize_frame(None, HudProfile(), ocr=FakeOcr())
        self.assertEqual(3, len(result.slots))
        self.assertEqual("unknown", result.slots[SLOT_ULTIMATE].state)


if __name__ == "__main__":
    unittest.main()
