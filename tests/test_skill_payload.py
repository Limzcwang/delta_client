"""技能上报 payload 类型/范围/NaN 清洗与后端规则自检测试。"""

from __future__ import annotations

import math
import unittest

from core.skill_payload import (
    MAX_REMAINING_MS,
    build_payload_from_state,
    clean_captured_at,
    clean_pct,
    clean_remaining,
    repair_payload,
    sanitize_slot,
    serialize_skill_state,
    validate_payload,
)
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillSlot, SkillState


def make_state(**overrides) -> SkillState:
    base = {
        "ultimate": SkillSlot(SLOT_ULTIMATE, "charging", 14_999.6, percent=16.4),
        "ability": SkillSlot(SLOT_ABILITY, "charging", 14999.6, charges=2.0, max_charges=3.0),
        "throwable": SkillSlot(SLOT_THROWABLE, "ready", 0, charges=2.0, max_charges=2.0),
    }
    base.update(overrides)
    return SkillState(user_id="1", nickname="我", captured_at=1_700_000_000_000, slots=base)


class CleaningTests(unittest.TestCase):
    def test_float_rounding_and_clamp(self) -> None:
        self.assertEqual(15_000, clean_remaining(14_999.6))
        self.assertEqual(16, clean_pct(16.4))
        self.assertEqual(0, clean_pct(-3))
        self.assertEqual(100, clean_pct(150.4))
        self.assertEqual(MAX_REMAINING_MS, clean_remaining(10**9))
        self.assertEqual(0, clean_remaining(-10))

    def test_nan_and_none_are_invalid(self) -> None:
        self.assertIsNone(clean_pct(float("nan")))
        self.assertIsNone(clean_remaining(float("inf")))
        self.assertIsNone(clean_pct(None))
        self.assertIsNone(clean_remaining("oops"))

    def test_sanitize_slots(self) -> None:
        payload = build_payload_from_state(make_state())
        self.assertEqual(3, len(payload))
        ultimate = payload[0]
        self.assertEqual(16, ultimate["pct"])
        self.assertEqual(15_000, ultimate["remaining_ms"])
        ability = payload[1]
        self.assertEqual(2, ability["charges"])
        self.assertEqual(3, ability["max_charges"])
        self.assertEqual(15_000, ability["remaining_ms"])

    def test_invalid_fields_degrade_unknown(self) -> None:
        nan = float("nan")
        state = make_state(
            ultimate=SkillSlot(SLOT_ULTIMATE, "charging", nan, percent=nan),
            ability=SkillSlot(SLOT_ABILITY, "charging", nan, charges=1.0, max_charges=2.0),
            throwable=SkillSlot(SLOT_THROWABLE, "unknown", percent=nan),
        )
        payload = build_payload_from_state(state)
        self.assertEqual("unknown", payload[0]["state"])
        self.assertEqual("unknown", payload[1]["state"])
        self.assertEqual("unknown", payload[2]["state"])

    def test_max_charges_clamped_and_missing_unknown(self) -> None:
        state = make_state(
            ability=SkillSlot(SLOT_ABILITY, "charging", 5_000, charges=20, max_charges=20),
            throwable=SkillSlot(SLOT_THROWABLE, "ready", 0, charges=0, max_charges=0),
        )
        payload = build_payload_from_state(state)
        self.assertEqual(9, payload[1]["max_charges"])
        self.assertEqual(9, payload[1]["charges"])
        self.assertEqual("ready", payload[2]["state"])
        self.assertEqual(1, payload[2]["max_charges"])
        self.assertEqual(0, payload[2]["charges"])

    def test_every_slot_has_charges_fields(self) -> None:
        states = [
            make_state(),
            make_state(ultimate=SkillSlot(SLOT_ULTIMATE, "ready", 0)),
            make_state(throwable=SkillSlot(SLOT_THROWABLE, "unknown", 0)),
            make_state(ability=SkillSlot(SLOT_ABILITY, "ready", 0, charges=0, max_charges=None)),
        ]
        for state in states:
            payload = serialize_skill_state(state)
            valid, reason = validate_payload(payload)
            self.assertTrue(valid, reason)
            for item in payload:
                self.assertIn("charges", item)
                self.assertIn("max_charges", item)
                self.assertGreaterEqual(item["max_charges"], 1)
                self.assertLessEqual(item["max_charges"], 9)
                self.assertGreaterEqual(item["charges"], 0)
                self.assertLessEqual(item["charges"], item["max_charges"])

    def test_repair_only_demotes_invalid_slots(self) -> None:
        good = build_payload_from_state(make_state())
        broken = [
            good[0],
            {**good[1], "max_charges": 0},
            {**good[2], "max_charges": 99},
        ]
        repaired = repair_payload(broken)
        self.assertEqual("charging", repaired[0]["state"])
        self.assertEqual("unknown", repaired[1]["state"])
        self.assertEqual("unknown", repaired[2]["state"])
        valid, reason = validate_payload(repaired)
        self.assertTrue(valid, reason)

    def test_serialize_share_state_has_int_remaining_every_slot(self) -> None:
        # 开启共享时缓存里可能是 ready/unknown 且 remaining_ms 缺省/None
        state = make_state(
            ultimate=SkillSlot(SLOT_ULTIMATE, "ready", None, percent=None),
            ability=SkillSlot(SLOT_ABILITY, "unknown", None),
            throwable=SkillSlot(SLOT_THROWABLE, "ready", None, charges=None, max_charges=None),
        )
        payload = serialize_skill_state(state)
        valid, reason = validate_payload(payload)
        self.assertTrue(valid, reason)
        for item in payload:
            remaining = item["remaining_ms"]
            if remaining is not None:
                self.assertIsInstance(remaining, int)
                self.assertTrue(0 <= remaining <= MAX_REMAINING_MS)
            self.assertNotIn(None, {k: v for k, v in item.items() if k != "remaining_ms"}.values())
        self.assertEqual("unknown", payload[1]["state"])
        self.assertIsNone(payload[1]["remaining_ms"])
        self.assertEqual("ready", payload[2]["state"])
        self.assertEqual(1, payload[2]["max_charges"])
        self.assertEqual(0, payload[2]["charges"])

    def test_serialize_nan_float_and_overrange(self) -> None:
        state = make_state(
            ultimate=SkillSlot(SLOT_ULTIMATE, "charging", float("nan"), percent=float("nan")),
            ability=SkillSlot(SLOT_ABILITY, "charging", float("inf"), charges=99, max_charges=20),
            throwable=SkillSlot(SLOT_THROWABLE, "charging", 1.5, charges=0.2, max_charges=2.7),
        )
        payload = serialize_skill_state(state)
        valid, reason = validate_payload(payload)
        self.assertTrue(valid, reason)
        self.assertEqual("unknown", payload[0]["state"])
        self.assertEqual("unknown", payload[1]["state"])
        self.assertIsInstance(payload[2]["remaining_ms"], int)
        self.assertIsInstance(payload[2]["max_charges"], int)

    def test_captured_at_must_be_integer_ms(self) -> None:
        self.assertEqual(1_700_000_000_000, clean_captured_at(1_700_000_000_000.0))
        self.assertEqual(123, clean_captured_at("123"))
        self.assertIsNone(clean_captured_at(123.4))
        self.assertIsNone(clean_captured_at(float("nan")))
        self.assertIsNone(clean_captured_at(True))
        self.assertIsNone(clean_captured_at(None))


class ValidationTests(unittest.TestCase):
    def test_built_payload_matches_backend_rules(self) -> None:
        payload = build_payload_from_state(make_state())
        valid, reason = validate_payload(payload)
        self.assertTrue(valid, reason)
        for item in payload:
            if item["state"] == "unknown":
                continue
            self.assertIsInstance(item["remaining_ms"], int)
            self.assertTrue(0 <= item["remaining_ms"] <= MAX_REMAINING_MS)
            if "pct" in item:
                self.assertIsInstance(item["pct"], int)
                self.assertTrue(0 <= item["pct"] <= 100)
            for key in ("charges", "max_charges"):
                if key in item:
                    self.assertIsInstance(item[key], int)

    def test_backend_rule_violations_detected(self) -> None:
        good = build_payload_from_state(make_state())
        cases = [
            ([], "3 个槽"),
            ([{**good[0], "remaining_ms": 1.2}, good[1], good[2]], "remaining_ms"),
            ([{**good[0], "pct": 16.4}, good[1], good[2]], "pct"),
            ([{**good[0], "pct": 150}, good[1], good[2]], "pct"),
            ([{**good[0], "remaining_ms": -1}, good[1], good[2]], "remaining_ms"),
            ([{**good[0], "state": "wat"}, good[1], good[2]], "state"),
            ([good[0], {**good[1], "max_charges": 0}, good[2]], "max_charges"),
            ([good[0], {**good[1], "max_charges": 10}, good[2]], "max_charges"),
            ([good[0], {**good[1], "charges": 4}, good[2]], "charges"),
            ([good[0], good[1], {**good[2], "max_charges": None}], "max_charges"),
        ]
        for payload, fragment in cases:
            valid, reason = validate_payload(payload)
            self.assertFalse(valid)
            self.assertIn(fragment, reason)

    def test_real_recognition_style_floats(self) -> None:
        # 识别管线典型值：mask ratio*total 是 float、pct 是 float
        state = make_state(
            ultimate=SkillSlot(SLOT_ULTIMATE, "charging", 90_000 * (100 - 16.4) / 100, percent=16.4),
            ability=SkillSlot(SLOT_ABILITY, "charging", 30_000 * 0.4999, charges=1.0, max_charges=2.0),
        )
        payload = build_payload_from_state(state)
        valid, reason = validate_payload(payload)
        self.assertTrue(valid, reason)
        self.assertEqual(16, payload[0]["pct"])
        self.assertEqual(75_240, payload[0]["remaining_ms"])
        self.assertEqual(14_997, payload[1]["remaining_ms"])


if __name__ == "__main__":
    unittest.main()

class UnknownNullTests(unittest.TestCase):
    def test_unknown_remaining_null(self):
        from core.skills import SkillState
        from core.skill_payload import serialize_skill_state
        import json
        state=SkillState.from_ws({"user_id":"1","captured_at":1,"skills":{"ultimate":{"state":"unknown"},"ability":{"state":"unknown"},"throwable":{"state":"unknown"}}})
        payload=serialize_skill_state(state)
        self.assertTrue(all(item["remaining_ms"] is None for item in payload))
        self.assertIn('"remaining_ms": null', json.dumps(payload))
