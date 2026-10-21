"""0.2.11 对局状态机/OCR 解析（纯逻辑）。"""
from __future__ import annotations
import math, re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

class MatchPhase(str, Enum):
    OFF = "未开启"
    IDLE = "对局未进行"
    RUNNING = "对局进行中"

def window_plan(interval_ms: int, window_ms: int = 6000) -> tuple[int, int]:
    attempts = max(1, int(window_ms) // max(1, int(interval_ms)))
    return attempts, max(1, math.floor(attempts / 2))

@dataclass
class HitWindow:
    interval_ms: int
    window_ms: int = 6000
    attempts: int = field(init=False)
    threshold: int = field(init=False)
    seen: int = 0
    hits: int = 0
    def __post_init__(self):
        self.attempts, self.threshold = window_plan(self.interval_ms, self.window_ms)
    def rearm(self, interval_ms: int) -> None:
        self.interval_ms = int(interval_ms)
        self.attempts, self.threshold = window_plan(self.interval_ms, self.window_ms)
        self.seen = min(self.seen, self.attempts)
        self.hits = min(self.hits, self.threshold)
    def record(self, hit: bool) -> str:
        if self.seen >= self.attempts:
            return "abort"
        self.seen += 1
        if hit:
            self.hits += 1
        if self.hits >= self.threshold:
            return "hit"
        if self.hits + (self.attempts - self.seen) < self.threshold:
            return "abort"
        return "continue"

@dataclass
class MatchStateMachine:
    interval_ms: int = 2000
    auto_start: bool = True
    phase: MatchPhase = MatchPhase.OFF
    shared: bool = False
    logged_in: bool = False
    in_room: bool = False
    start_window: HitWindow | None = None
    end_window: HitWindow | None = None
    async_pending: bool = False
    async_generation: int = 0
    end_delay_ms: int = 3000
    locked_operator: str = ""
    operator_unknown: bool = False
    _reset_lock: bool = False
    def context(self) -> None:
        if not (self.shared and self.logged_in and self.in_room):
            self.phase = MatchPhase.OFF
            self._clear_tasks()
        elif self.phase == MatchPhase.OFF:
            self.phase = MatchPhase.IDLE
    def set_sharing(self, enabled: bool) -> None:
        self.shared = bool(enabled)
        if not enabled:
            self.phase = MatchPhase.OFF
            self._clear_tasks()
        elif self.phase == MatchPhase.OFF:
            self.phase = MatchPhase.IDLE
    def set_context(self, *, logged_in: bool, in_room: bool) -> None:
        self.logged_in = bool(logged_in); self.in_room = bool(in_room); self.context()
    def _clear_tasks(self) -> None:
        self.start_window = None; self.end_window = None
        self.async_pending = False; self.async_generation += 1
        self.locked_operator = ""; self.operator_unknown = False; self._reset_lock = False
    def reset(self) -> None:
        if self.phase == MatchPhase.IDLE:
            self.phase = MatchPhase.RUNNING; self.start_window = None
        elif self.phase == MatchPhase.RUNNING:
            self.phase = MatchPhase.IDLE; self._clear_tasks()
        self._reset_lock = True
    def release_reset_lock(self) -> None:
        self._reset_lock = False
    def observe_start(self, hit: bool) -> str:
        if self.phase != MatchPhase.IDLE or not self.auto_start:
            return "idle"
        if self.start_window is None:
            self.start_window = HitWindow(self.interval_ms)
        result = self.start_window.record(hit)
        if result == "hit":
            self.phase = MatchPhase.RUNNING; self.start_window = None
        elif result == "abort":
            self.start_window = HitWindow(self.interval_ms)
        return result
    def begin_end(self, generation: int | None = None) -> int:
        self.async_generation += 1
        self.async_pending = True
        self.end_window = HitWindow(self.interval_ms)
        return self.async_generation
    def observe_end(self, hit: bool, generation: int | None = None) -> str:
        if generation is not None and generation != self.async_generation:
            return "stale"
        if self.phase != MatchPhase.RUNNING or not self.async_pending:
            return "idle"
        assert self.end_window is not None
        result = self.end_window.record(hit)
        if result == "hit":
            self.phase = MatchPhase.IDLE; self._clear_tasks()
        elif result == "abort":
            self.async_pending = False; self.end_window = None
        return result
    def terminate(self) -> None:
        """统一停止入口；幂等，未启动/重复调用均安全。"""
        self.phase = MatchPhase.IDLE if (self.shared and self.logged_in and self.in_room) else MatchPhase.OFF
        self._clear_tasks()

    def window_closed(self) -> None:
        if self.phase == MatchPhase.RUNNING:
            self.phase = MatchPhase.IDLE; self._clear_tasks()
    def update_interval(self, interval_ms: int) -> None:
        self.interval_ms = int(interval_ms)
        for window in (self.start_window, self.end_window):
            if window is not None:
                window.rearm(self.interval_ms)
    def lock_operator(self, operator_id: str, score: float, high: float = 0.75) -> None:
        if self.locked_operator:
            return
        if score >= high or score > 0:
            self.locked_operator = operator_id
            self.operator_unknown = score < high
    def label(self) -> str:
        return self.phase.value

_DIGIT_MAP = str.maketrans({"O":"0","o":"0","I":"1","l":"1","|":"1","S":"5","s":"5","B":"8","Z":"2","G":"6","g":"9"})
_TIME_RE = re.compile(r"(\d{1,2})\s*[:\-]\s*(\d{2})")
def normalize_digits(text: str) -> str:
    return str(text or "").translate(_DIGIT_MAP)
def parse_countdown(text: str) -> bool:
    return bool(re.search(r"\d{1,2}\s*:\s*\d{2}", normalize_digits(text)))
def parse_settlement_texts(lines: Iterable[str]) -> bool:
    texts = [normalize_digits(x).strip() for x in lines if str(x).strip()]
    joined = " ".join(texts)
    if not any(word in joined for word in ("对局", "时长", "时间")):
        return False
    for text in texts:
        for m in _TIME_RE.finditer(text):
            a, b = int(m.group(1)), int(m.group(2))
            if 0 <= a <= 59 and 0 <= b <= 59:
                return True
    # 日期时间 07-31 02:09
    if re.search(r"\b\d{1,2}\s*-\s*\d{1,2}\b", joined):
        return True
    return False
