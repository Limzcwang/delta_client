"""E4 自动共享循环：变化去抖/节流/暂停/信号测试。"""

from __future__ import annotations

import time
import unittest
from dataclasses import dataclass

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from ui.auto_share import AutoShareController

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False

from core.skill_auto import ChangeTracker


class FakeSource:
    def __init__(self, frame=True):
        self.frame = frame
        self.closed = False

    def grab(self):
        return object() if self.frame else None

    def close(self):
        self.closed = True


class FakeRecognition:
    def __init__(self, payload):
        self._payload = payload

    def payload(self):
        return self._payload


def payload(remaining=15_000, state="charging", charges=1, pct=16):
    return [
        {"slot": 0, "state": state, "remaining_ms": remaining, "pct": pct},
        {"slot": 1, "state": "charging", "remaining_ms": remaining, "charges": charges, "max_charges": 2},
        {"slot": 2, "state": "unknown"},
    ]


class TrackerTests(unittest.TestCase):
    def test_state_charge_and_threshold(self) -> None:
        tracker = ChangeTracker(remaining_threshold_ms=500, min_interval_ms=0)
        first = payload()
        self.assertTrue(tracker.should_emit(first, 1000))
        tracker.mark_sent(first, 1000)
        self.assertFalse(tracker.should_emit(payload(15_200), 2000))
        self.assertFalse(tracker.should_emit(payload(16_000), 3000))  # remaining 变化不再上报
        self.assertTrue(tracker.should_emit(payload(charges=2), 4000))
        self.assertTrue(tracker.should_emit(payload(state="ready"), 5000))

    def test_min_interval_hard_limit(self) -> None:
        tracker = ChangeTracker(min_interval_ms=500)
        first = payload()
        tracker.mark_sent(first, 1000)
        self.assertFalse(tracker.should_emit(payload(state="ready"), 1100))
        self.assertTrue(tracker.should_emit(payload(state="ready"), 1600))


class ReportTriggerMatrixTests(unittest.TestCase):
    def _sent(self, tracker, item, now):
        tracker.mark_sent([item], now)

    def test_report_trigger_matrix(self) -> None:
        from core.skill_auto import ChangeTracker

        base = {"slot": 1, "state": "charging", "charges": 1, "max_charges": 2, "ready_at": 100_000}
        tracker = ChangeTracker(min_interval_ms=0)
        tracker.mark_sent([base], 1000)
        self.assertFalse(tracker.should_emit([dict(base, ready_at=99_000)], 2000))  # 1s 内不算重同步
        self.assertTrue(tracker.should_emit([dict(base, ready_at=101_500)], 3000))  # ready_at 跳变>1s
        tracker.mark_sent([dict(base, ready_at=101_500)], 3000)
        self.assertFalse(tracker.should_emit([dict(base, ready_at=101_500, remaining_ms=12000)], 4000))
        self.assertTrue(tracker.should_emit([dict(base, ready_at=101_500, state="ready")], 5000))
        tracker.mark_sent([dict(base, ready_at=101_500, state="ready")], 5000)
        self.assertTrue(tracker.should_emit([dict(base, ready_at=101_500, state="ready", charges=2)], 6000))
        tracker.mark_sent([dict(base, ready_at=101_500, state="ready", charges=2)], 6000)
        self.assertTrue(tracker.should_emit([dict(base, ready_at=101_500, state="ready", charges=2, max_charges=3)], 7000))


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_QT:
            raise unittest.SkipTest("PySide6 未安装")
        cls.app = QApplication.instance() or QApplication([])

    def _controller(self, source, recognition):
        emitted = []
        statuses = []
        ctl = AutoShareController(lambda: (source, "fake"), lambda frame: recognition)
        ctl.payload_ready.connect(emitted.append)
        ctl.status_changed.connect(statuses.append)
        return ctl, emitted, statuses

    def test_only_changes_are_emitted(self) -> None:
        source = FakeSource()
        current = [payload()]
        ctl, emitted, statuses = self._controller(source, FakeRecognition(current[0]))
        ctl._tracker.min_interval_ms = 0
        ctl.configure(enabled=True, sharing=True, room_active=True)
        ctl.tick()
        self.assertEqual(1, len(emitted))
        ctl.tick()
        self.assertEqual(1, len(emitted))  # 无变化
        current[0] = payload(remaining=20_000)
        ctl._recognizer = lambda frame: FakeRecognition(current[0])
        ctl.tick()
        self.assertEqual(1, len(emitted))  # remaining 变化不触发
        current[0] = payload(state="ready")
        ctl.tick()
        self.assertEqual(2, len(emitted))  # state 变化触发

    def test_pause_conditions(self) -> None:
        source = FakeSource()
        ctl, emitted, statuses = self._controller(source, FakeRecognition(payload()))
        ctl.configure(enabled=True, sharing=False, room_active=True)
        ctl.tick()
        self.assertEqual([], emitted)
        self.assertIn("技能共享未开启", statuses[-1])
        ctl.configure(sharing=True, room_active=False)
        ctl.tick()
        self.assertEqual([], emitted)
        self.assertIn("不在房间", statuses[-1])
        ctl.configure(room_active=True)
        ctl.start()
        self.assertTrue(ctl.running)
        ctl.stop()
        self.assertFalse(ctl.running)

    def test_window_lost_pauses(self) -> None:
        source = FakeSource(frame=False)
        ctl, emitted, statuses = self._controller(source, FakeRecognition(payload()))
        ctl.configure(enabled=True, sharing=True, room_active=True)
        ctl.tick()
        self.assertEqual([], emitted)
        self.assertIn("窗口丢失/最小化", statuses[-1])

    def test_interval_config(self) -> None:
        ctl, _, _ = self._controller(FakeSource(), FakeRecognition(payload()))
        ctl.configure(enabled=True, sharing=True, room_active=True, interval_ms=1000)
        self.assertEqual(1000, ctl.interval_ms)


if __name__ == "__main__":
    unittest.main()
