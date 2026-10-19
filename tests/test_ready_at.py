"""E2 ready_at：服务端时钟偏移/延迟到达/兜底测试。"""

from __future__ import annotations

import unittest

from core.clock import ServerClock
from core.skills import SkillSlot, SkillState


class ServerClockTests(unittest.TestCase):
    def test_auth_offset_and_ema_convergence(self) -> None:
        clock = ServerClock(alpha=0.2)
        for noise in (0, 40, -20, 10, -30, 20, 0):
            clock.observe(1_000_000 + 1000 + noise, 1_000_000, 0)
        self.assertTrue(clock.initialized)
        self.assertAlmostEqual(1000, clock.offset_ms, delta=30)

    def test_pong_rtt_midpoint_compensation(self) -> None:
        clock = ServerClock(alpha=1.0)
        # 发送 epoch=1_000_000，接收=1_000_500，服务器时间取中点 2_000_250
        offset = clock.observe_rtt(2_000_250, 1_000_000, 1_000_500, recv_mono_ms=500)
        self.assertAlmostEqual(1_000_000, offset, delta=1)
        # 中点补偿后比直接用接收时刻多 250ms（因为服务器时间按中点算）
        clock2 = ServerClock(alpha=1.0)
        self.assertAlmostEqual(
            1_000_000,
            clock2.observe_rtt(2_000_250, 1_000_000, 1_000_500),
            delta=1,
        )

    def test_now_uses_monotonic_not_wall_clock(self) -> None:
        clock = ServerClock(alpha=1.0)
        clock.observe(1_000_000 + 500, 1_000_000, 0)
        self.assertEqual(1_001_500, clock.now_ms(mono_ms=1000))
        self.assertEqual(1_005_500, clock.now_ms(mono_ms=5000))

    def test_uninitialized_falls_back_epoch(self) -> None:
        clock = ServerClock()
        self.assertFalse(clock.initialized)
        self.assertGreater(clock.now_ms(mono_ms=123), 0)


class ReadyAtParsingTests(unittest.TestCase):
    def _state(self):
        return SkillState.from_ws(
            {
                "user_id": "2",
                "nickname": "队友",
                "captured_at": 1_000_000,
                "server_received_at": 1_000_500,
                "skills": [
                    {"slot": 0, "state": "charging", "pct": 16, "ready_at": 1_050_000},
                    {"slot": 1, "state": "charging", "remaining_ms": 30_000, "ready_at": 1_030_000},
                    {"slot": 2, "state": "unknown"},
                ],
            }
        )

    def test_parse_ready_at_and_server_received_at(self) -> None:
        state = self._state()
        self.assertEqual(1_000_500, state.server_received_at)
        self.assertEqual(1_050_000, state.slot("ultimate").ready_at)
        self.assertEqual(1_030_000, state.slot("ability").ready_at)

    def test_delayed_receive_does_not_shift_countdown(self) -> None:
        state = self._state()
        self.assertEqual(50_000, state.slot("ultimate").remaining_now(1_000_000, 1_000_000))
        self.assertEqual(49_500, state.slot("ultimate").remaining_now(1_000_000, 1_000_500))
        self.assertEqual(0, state.slot("ultimate").remaining_now(1_000_000, 1_060_000))
        self.assertEqual("ready", state.slot("ultimate").effective_state(1_000_000, 1_060_000))

    def test_old_payload_falls_back(self) -> None:
        old = SkillSlot.from_api("ability", {"state": "charging", "remaining_ms": 30_000})
        self.assertEqual(0, old.ready_at)
        self.assertEqual(20_000, old.remaining_now(1_000_000, 1_010_000))
        self.assertEqual(0, old.remaining_now(1_000_000, 1_040_000))


if __name__ == "__main__":
    unittest.main()
