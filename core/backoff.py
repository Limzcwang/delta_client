"""WebSocket 重连退避（PROTOCOL.md §6.1：1s/2s/4s… 上限 30s）。"""

from __future__ import annotations

import random
from typing import Callable


class ReconnectBackoff:
    """指数退避计算器。

    - ``delay_for(attempt)`` 只计算第 ``attempt`` 次退避的秒数（0 起）；
    - ``next_delay()`` 取当前退避并推进计数；
    - 连接/认证成功后退调用 :meth:`reset` 回到 0；
    - ``jitter`` 为 0 时完全确定，便于测试；>0 时结果落在
      ``[raw*(1-jitter), raw]`` 区间。
    """

    def __init__(
        self,
        base: float = 1.0,
        factor: float = 2.0,
        max_delay: float = 30.0,
        jitter: float = 0.0,
        rng: Callable[[], float] | None = None,
    ) -> None:
        if base <= 0:
            raise ValueError("base 必须 > 0")
        if factor < 1:
            raise ValueError("factor 必须 >= 1")
        if max_delay < base:
            raise ValueError("max_delay 必须 >= base")
        if not 0.0 <= jitter < 1.0:
            raise ValueError("jitter 必须在 [0, 1) 区间")
        self.base = float(base)
        self.factor = float(factor)
        self.max_delay = float(max_delay)
        self.jitter = float(jitter)
        self._rng = rng or random.random
        self._attempt = 0

    @property
    def attempt(self) -> int:
        return self._attempt

    def delay_for(self, attempt: int, rng: Callable[[], float] | None = None) -> float:
        """第 ``attempt`` 次退避的秒数（未加随机抖动的值受 jitter 约束）。"""
        attempt = max(0, int(attempt))
        # 限制指数规模，避免极大 attempt 让 float 溢出
        exponent = min(attempt, 30)
        raw = min(self.max_delay, self.base * (self.factor**exponent))
        if self.jitter <= 0:
            return round(raw, 6)
        draw = (rng or self._rng)()
        draw = min(max(float(draw), 0.0), 1.0)
        return round(raw * (1.0 - self.jitter + self.jitter * draw), 6)

    def next_delay(self) -> float:
        delay = self.delay_for(self._attempt)
        self._attempt += 1
        return delay

    def reset(self) -> None:
        self._attempt = 0
