"""E2：服务器时钟偏移估计（auth_ok + pong RTT/2，EMA 平滑）。"""

from __future__ import annotations

import time
from dataclasses import dataclass

EMA_ALPHA = 0.2


@dataclass
class ServerClock:
    """本机单调时钟驱动的服务器时间估计。

    - 偏移用 ``server_time - 本地中点`` 估算，pong 时用 (send+recv)/2 做 RTT/2 补偿；
    - 偏移 EMA（默认 α=0.2）；
    - 锚点 = 观测时的本地 epoch + 单调时刻；tick 用单调时钟，系统时间跳变不影响。
    """

    alpha: float = EMA_ALPHA
    offset_ms: float | None = None
    _anchor_epoch: float = 0.0
    _anchor_mono: float = 0.0
    _initialized: bool = False
    _observations: int = 0

    def reset(self) -> None:
        self.offset_ms = None
        self._anchor_epoch = 0.0
        self._anchor_mono = 0.0
        self._initialized = False
        self._observations = 0

    def observe(
        self,
        server_time_ms: float,
        local_epoch_ms: float | None = None,
        mono_ms: float | None = None,
    ) -> float:
        """直接观测（auth_ok）：offset = server - local。"""
        epoch = float(time.time() * 1000 if local_epoch_ms is None else local_epoch_ms)
        mono = float(time.monotonic() * 1000 if mono_ms is None else mono_ms)
        sample = float(server_time_ms) - epoch
        return self._apply(sample, epoch, mono)

    def observe_rtt(
        self,
        server_time_ms: float,
        send_epoch_ms: float,
        recv_epoch_ms: float,
        send_mono_ms: float | None = None,
        recv_mono_ms: float | None = None,
    ) -> float:
        """pong 观测：以本地发送/接收中点补偿 RTT/2。"""
        midpoint = (float(send_epoch_ms) + float(recv_epoch_ms)) / 2.0
        sample = float(server_time_ms) - midpoint
        monotonic = (
            float(time.monotonic() * 1000) if recv_mono_ms is None else float(recv_mono_ms)
        )
        return self._apply(sample, float(recv_epoch_ms), monotonic)

    def _apply(self, sample: float, anchor_epoch: float, anchor_mono: float) -> float:
        if self.offset_ms is None:
            self.offset_ms = float(sample)
        else:
            self.offset_ms = (1.0 - self.alpha) * self.offset_ms + self.alpha * float(sample)
        self._anchor_epoch = float(anchor_epoch)
        self._anchor_mono = float(anchor_mono)
        self._initialized = True
        self._observations += 1
        return self.offset_ms

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def observations(self) -> int:
        return self._observations

    def now_ms(self, mono_ms: float | None = None) -> int:
        """估计的服务器当前时间；未观测时回退本机 epoch。"""
        if not self._initialized or self.offset_ms is None:
            return int(time.time() * 1000 if mono_ms is None else mono_ms)
        mono = float(time.monotonic() * 1000 if mono_ms is None else mono_ms)
        return int(round(self._anchor_epoch + (mono - self._anchor_mono) + self.offset_ms))
