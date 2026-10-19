"""E2 技能 CD 数据/倒计时/缓存/限频测试（离线）。"""

from __future__ import annotations

import unittest

from core.skills import (
    SLOT_ABILITY,
    SLOT_THROWABLE,
    SLOT_ULTIMATE,
    SKILL_CHARGING,
    SKILL_READY,
    SKILL_UNKNOWN,
    UNSHARED_AFTER_MS,
    SkillBook,
    SkillShareThrottle,
    SkillSlot,
    SkillState,
    format_countdown,
    format_percent,
    parse_room_joined_skill_states,
    parse_skill_state_list,
)


def make_state(**overrides):
    payload = {
        "user_id": "2",
        "nickname": "队友-Alpha",
        "operator": "红狼",
        "captured_at": 1_000_000,
        "skills": {
            "ultimate": {"state": "ready", "percent": 100},
            "ability": {"state": "charging", "charges": 1, "max_charges": 2, "remaining_ms": 30_000},
            "throwable": {"state": "unknown"},
        },
    }
    payload.update(overrides)
    return SkillState.from_ws(payload)


class SkillParseTests(unittest.TestCase):
    def test_parse_states_and_slots(self) -> None:
        state = make_state()
        self.assertEqual("2", state.user_id)
        self.assertEqual("队友-Alpha", state.display_name)
        self.assertEqual("队友-Alpha"[:1].upper(), state.avatar_letter)
        self.assertEqual("红狼", state.operator)
        self.assertEqual(SKILL_READY, state.slot(SLOT_ULTIMATE).state)
        self.assertEqual(100.0, state.slot(SLOT_ULTIMATE).percent)
        self.assertEqual(1, state.slot(SLOT_ABILITY).charges)
        self.assertEqual(2, state.slot(SLOT_ABILITY).max_charges)
        self.assertEqual(SKILL_UNKNOWN, state.slot(SLOT_THROWABLE).state)

    def test_room_joined_containers(self) -> None:
        state = {"user_id": "9", "nickname": "X", "captured_at": 1}
        self.assertEqual(1, len(parse_room_joined_skill_states({"skill_states": [state]})))
        self.assertEqual(1, len(parse_room_joined_skill_states({"skill_state": {"items": [state]}})))
        self.assertEqual(2, len(parse_skill_state_list([state, {**state, "user_id": "10"}])))
        self.assertEqual([], parse_skill_state_list(None))

    def test_slot_fallbacks(self) -> None:
        slot = SkillSlot.from_api(SLOT_ABILITY, {"ready": True, "charges": 2, "max": 2})
        self.assertEqual(SKILL_READY, slot.state)
        slot = SkillSlot.from_api(SLOT_ULTIMATE, {"percent": 0.5, "ratio": True, "state": "ready"})
        self.assertEqual(50.0, slot.percent)


class CountdownTests(unittest.TestCase):
    def test_countdown_with_server_offset(self) -> None:
        state = make_state()
        slot = state.slot(SLOT_ABILITY)
        self.assertEqual(30_000, slot.remaining_now(1_000_000, 1_000_000))
        self.assertEqual(20_000, slot.remaining_now(1_000_000, 1_010_000))
        self.assertEqual(0, slot.remaining_now(1_000_000, 1_040_000))
        self.assertEqual(SKILL_READY, slot.effective_state(1_000_000, 1_040_000))

    def test_unshared_after_30_minutes(self) -> None:
        state = make_state()
        self.assertFalse(state.is_unshared(1_000_000 + UNSHARED_AFTER_MS))
        self.assertTrue(state.is_unshared(1_000_000 + UNSHARED_AFTER_MS + 1))
        self.assertTrue(make_state(captured_at=0).is_unshared(1_000_000))

    def test_format_helpers(self) -> None:
        self.assertEqual("0:00", format_countdown(0))
        self.assertEqual("0:05", format_countdown(5_900))
        self.assertEqual("1:05", format_countdown(65_000))
        self.assertEqual("65%", format_percent(64.6))


class SkillBookTests(unittest.TestCase):
    def test_add_update_remove(self) -> None:
        book = SkillBook()
        book.update(make_state())
        book.update(make_state(nickname="新昵称"))
        self.assertEqual(1, len(book))
        self.assertEqual("新昵称", book.get("2").display_name)
        self.assertTrue(book.remove("2"))
        self.assertFalse(book.remove("2"))
        self.assertEqual([], book.states())
        book.update(make_state(user_id="3"))
        book.clear()
        self.assertEqual(0, len(book))


class SkillThrottleTests(unittest.TestCase):
    def test_two_per_second(self) -> None:
        clock = [1_000.0]
        throttle = SkillShareThrottle(max_events=2, window_ms=1000, clock=lambda: clock[0])
        self.assertTrue(throttle.allow())
        self.assertTrue(throttle.allow())
        self.assertFalse(throttle.allow())
        clock[0] += 1001
        self.assertTrue(throttle.allow())
        throttle.reset()
        self.assertTrue(throttle.allow())


if __name__ == "__main__":
    unittest.main()
