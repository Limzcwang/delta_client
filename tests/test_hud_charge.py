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
