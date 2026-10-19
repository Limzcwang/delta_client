"""充能技能：charges 减少/增加/文字重同步的 ready_at 估算。"""

from __future__ import annotations

import unittest

from core.hud_brightness import SkillTransitionTracker


class ChargeTrackerTests(unittest.TestCase):
    def test_charge_decrease_increase_and_text_resync(self) -> None:
        tracker = SkillTransitionTracker()
        ready_at, remaining, transition = tracker.update_charge(1, 1, 2, 35_000, 1_000)
        self.assertEqual(36_000, ready_at)
        self.assertEqual(35_000, remaining)
        self.assertEqual("charge-init", transition)
        ready_at, remaining, transition = tracker.update_charge(1, 1, 2, 35_000, 5_000)
        self.assertEqual(36_000, ready_at)
        self.assertEqual(31_000, remaining)
        self.assertEqual("charge-steady", transition)
        ready_at, remaining, transition = tracker.update_charge(1, 0, 2, 35_000, 10_000)
        self.assertEqual(45_000, ready_at)
        self.assertEqual(35_000, remaining)
        self.assertEqual("charge-decrease", transition)
        ready_at, remaining, transition = tracker.update_charge(1, 1, 2, 35_000, 20_000)
        self.assertEqual(55_000, ready_at)
        self.assertEqual(35_000, remaining)
        self.assertEqual("charge-increase", transition)
        ready_at, remaining, transition = tracker.update_charge(
            1, 0, 2, 35_000, 30_000, text_remaining_ms=61_000
        )
        self.assertEqual(91_000, ready_at)
        self.assertEqual(61_000, remaining)
        self.assertEqual("text-resync", transition)
        ready_at, remaining, transition = tracker.update_charge(1, 2, 2, 35_000, 40_000)
        self.assertEqual(0, ready_at)
        self.assertEqual(0, remaining)
        self.assertEqual("charge-full", transition)


class ChargeEventTests(unittest.TestCase):
    def test_brightness_cast_needs_two_frames(self) -> None:
        tracker = SkillTransitionTracker()
        ready_at, remaining, state, event = tracker.observe_brightness(1, "ready", 70_000, 1_000)
        self.assertEqual("ready", state)
        self.assertEqual("", event)
        ready_at, remaining, state, event = tracker.observe_brightness(1, "charging", 70_000, 2_000)
        self.assertEqual("ready", state)  # 第一帧暗不触发
        self.assertEqual("", event)
        ready_at, remaining, state, event = tracker.observe_brightness(1, "charging", 70_000, 3_000)
        self.assertEqual("charging", state)
        self.assertEqual("cast", event)
        self.assertEqual(73_000, ready_at)
        self.assertEqual(70_000, remaining)

    def test_charge_decrease_and_text_resync(self) -> None:
        tracker = SkillTransitionTracker()
        charges, ready_at, remaining, state, event = tracker.observe_charge(1, 2, 2, 35_000, 70_000, 1_000)
        self.assertEqual("ready", state)
        charges, ready_at, remaining, state, event = tracker.observe_charge(1, 1, 2, 35_000, 70_000, 2_000)
        self.assertEqual("ready", state)  # 第一帧 OCR 变化不触发
        charges, ready_at, remaining, state, event = tracker.observe_charge(1, 1, 2, 35_000, 70_000, 3_000)
        self.assertEqual("cast", event)
        self.assertEqual(38_000, ready_at)
        self.assertEqual(35_000, remaining)
        charges, ready_at, remaining, state, event = tracker.observe_charge(
            1, 0, 2, 35_000, 70_000, 10_000, text_remaining_ms=61_000
        )
        self.assertEqual(0, charges)
        self.assertEqual(71_000, ready_at)
        self.assertEqual(61_000, remaining)
        self.assertEqual("charging", state)

    def test_charge_recovery_updates_state(self) -> None:
        tracker = SkillTransitionTracker()
        tracker.observe_charge(1, 1, 2, 35_000, 70_000, 1_000)
        tracker.observe_charge(1, 2, 2, 35_000, 70_000, 2_000)
        charges, ready_at, remaining, state, event = tracker.observe_charge(
            1, 2, 2, 35_000, 70_000, 3_000
        )
        self.assertEqual(2, charges)
        self.assertEqual("ready", state)
        self.assertEqual(0, ready_at)
        self.assertIn(event, ("recover", ""))


class ChargeFixtureTests(unittest.TestCase):
    def test_fixture_brightness_transition_creates_cast_event(self) -> None:
        try:
            import cv2
            import numpy as np
        except Exception:  # noqa: BLE001
            self.skipTest("opencv/numpy 未安装")
        from pathlib import Path
        from core.hud_brightness import recognize_frame_brightness
        from core.hud_profile import HudProfile, Roi
        from core.operators import Operator, OperatorSkill

        base = Path(__file__).parent / "fixtures" / "hud_charge"
        operator = Operator(id="fixture", name="fixture", skills={0: OperatorSkill(0, "d", 70_000, 1)})
        tracker = SkillTransitionTracker()
        events = []
        for name in ("charge_band_0.png", "charge_band_1.png", "charge_band_1.png"):
            image = cv2.imdecode(np.fromfile(str(base / name), dtype=np.uint8), cv2.IMREAD_COLOR)
            height, width = image.shape[:2]
            profile = HudProfile(
                client_width=width,
                client_height=height,
                slots=[Roi(0, 0, width, height).to_dict() for _ in range(3)],
                text_row=Roi(0, height + 10, 10, 10),
                brightness_threshold=110,
            )
            result = recognize_frame_brightness(
                image, profile, operator=operator, ocr=None, tracker=tracker, server_now=1000
            )
            events.append(result.diagnostics[0].transition)
        self.assertIn("cast", events)


class ChargeConfigTests(unittest.TestCase):
    def test_honglang_charge_cd_from_asset(self) -> None:
        from core.operators import load_operator_catalog

        operator = load_operator_catalog().get("honglang")
        self.assertIsNotNone(operator)
        self.assertEqual(90_000, operator.skill(0).effective_charge_cd_ms)
        self.assertEqual(35_000, operator.skill(1).effective_charge_cd_ms)
        self.assertEqual(22_500, operator.skill(2).effective_charge_cd_ms)

    def test_effective_charge_falls_back_to_division(self) -> None:
        from core.operators import OperatorSkill

        skill = OperatorSkill(slot=1, total_cd_ms=70_000, max_charges=2)
        self.assertEqual(35_000, skill.effective_charge_cd_ms)
        overridden = OperatorSkill(slot=1, total_cd_ms=70_000, max_charges=2, charge_cd_ms=33_000)
        self.assertEqual(33_000, overridden.effective_charge_cd_ms)


if __name__ == "__main__":
    unittest.main()

