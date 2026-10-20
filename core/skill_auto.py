"""E4：技能共享自动循环的变化判定/最小间隔（纯逻辑）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

SKILL_STATES = ("ready", "charging", "unknown")


@dataclass
class ChangeTracker:
    """比较相邻识别结果，只在上报有意义的变化时触发。

    - state 切换必发；
    - charges 变化必发；
    - charging 的 remaining 变化超过阈值才发（避免 1s 抖动）；
    - 距上次发送不足 min_interval_ms 不发（硬下限）。
    """

    remaining_threshold_ms: int = 500
    min_interval_ms: int = 350
    _last_payload: list[dict[str, Any]] | None = None
    _last_sent_ms: float = 0.0

    def reset(self) -> None:
        self._last_payload = None
        self._last_sent_ms = 0.0

    @staticmethod
    def _by_slot(payload: Iterable[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        result: dict[int, dict[str, Any]] = {}
        for item in payload:
            try:
                result[int(item.get("slot", 0))] = item
            except (TypeError, ValueError):
                continue
        return result

    def should_emit(self, payload: list[dict[str, Any]], now_ms: float) -> bool:
        current = self._by_slot(payload)
        if self._last_payload is None:
            return True
        if self._last_sent_ms and now_ms - self._last_sent_ms < self.min_interval_ms:
            return False
        previous = self._by_slot(self._last_payload)
        for slot, item in current.items():
            old = previous.get(slot, {})
            if item.get("state") != old.get("state"):
                return True
            if int(item.get("charges", 0) or 0) != int(old.get("charges", 0) or 0):
                return True
            if int(item.get("max_charges", 0) or 0) != int(old.get("max_charges", 0) or 0):
                return True
            # 仅 ready_at 重同步（文字/充能事件时间跳变 >1s）才发；remaining 变化不发
            old_ready = int(old.get("ready_at", 0) or 0)
            new_ready = int(item.get("ready_at", 0) or 0)
            if abs(new_ready - old_ready) > 1000:
                return True
        return False

    def mark_sent(self, payload: list[dict[str, Any]], now_ms: float) -> None:
        self._last_payload = [dict(item) for item in payload]
        self._last_sent_ms = float(now_ms)
