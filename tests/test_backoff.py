"""WebSocket 重连退避测试（离线）。"""

from __future__ import annotations

import unittest

from core.backoff import ReconnectBackoff


class BackoffTests(unittest.TestCase):
    def test_default_sequence(self) -> None:
        backoff = ReconnectBackoff()
        delays = [backoff.next_delay() for _ in range(8)]
        self.assertEqual(delays, [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0])
        self.assertEqual(backoff.attempt, 8)

    def test_reset_after_success(self) -> None:
        backoff = ReconnectBackoff()
        self.assertEqual(backoff.next_delay(), 1.0)
        self.assertEqual(backoff.next_delay(), 2.0)
        backoff.reset()
        self.assertEqual(backoff.attempt, 0)
        self.assertEqual(backoff.next_delay(), 1.0)

    def test_delay_for_does_not_advance(self) -> None:
        backoff = ReconnectBackoff()
        self.assertEqual(backoff.delay_for(3), 8.0)
        self.assertEqual(backoff.attempt, 0)

    def test_huge_attempt_capped_without_overflow(self) -> None:
        backoff = ReconnectBackoff()
        self.assertEqual(backoff.delay_for(10_000), 30.0)

    def test_custom_policy(self) -> None:
        backoff = ReconnectBackoff(base=0.5, factor=3.0, max_delay=5.0)
        self.assertEqual([backoff.next_delay() for _ in range(4)], [0.5, 1.5, 4.5, 5.0])

    def test_jitter_bounds(self) -> None:
        backoff = ReconnectBackoff(base=4.0, jitter=0.5, rng=lambda: 1.0)
        self.assertEqual(backoff.delay_for(0), 4.0)
        low = ReconnectBackoff(base=4.0, jitter=0.5, rng=lambda: 0.0)
        self.assertEqual(low.delay_for(0), 2.0)

    def test_invalid_arguments(self) -> None:
        with self.assertRaises(ValueError):
            ReconnectBackoff(base=0)
        with self.assertRaises(ValueError):
            ReconnectBackoff(factor=0.5)
        with self.assertRaises(ValueError):
            ReconnectBackoff(base=2, max_delay=1)
        with self.assertRaises(ValueError):
            ReconnectBackoff(jitter=1.0)


if __name__ == "__main__":
    unittest.main()
