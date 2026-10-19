"""E2：技能 CD 面板数据模型 / 倒计时 / 本地节流（纯逻辑）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

SKILL_READY = "ready"
SKILL_CHARGING = "charging"
SKILL_UNKNOWN = "unknown"
SKILL_STATES = (SKILL_READY, SKILL_CHARGING, SKILL_UNKNOWN)

SLOT_ULTIMATE = "ultimate"
SLOT_ABILITY = "ability"
SLOT_THROWABLE = "throwable"
SLOT_KINDS = (SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)
SLOT_LABELS = {
    SLOT_ULTIMATE: "大招",
    SLOT_ABILITY: "技能",
    SLOT_THROWABLE: "投掷物",
}

#: 超过 30 分钟没更新视为「未共享」
UNSHARED_AFTER_MS = 30 * 60 * 1000


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


@dataclass(frozen=True)
class SkillSlot:
    """单个技能槽：大招显示百分比，技能/投掷物显示充能与剩余 CD。"""

    kind: str = SLOT_ULTIMATE
    state: str = SKILL_UNKNOWN
    remaining_ms: int = 0
    percent: float = 0.0
    charges: int = 0
    max_charges: int = 0
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_api(cls, kind: str, payload: Any) -> "SkillSlot":
        if not isinstance(payload, Mapping):
            return cls(kind=kind)
        state = str(_first(payload, "state", "status", "phase") or "").strip().lower()
        if not state:
            if bool(payload.get("ready")):
                state = SKILL_READY
            elif payload.get("remaining_ms") is not None:
                state = SKILL_CHARGING
            else:
                state = SKILL_UNKNOWN
        if state in ("cooldown", "cooling", "charging", "recharging"):
            state = SKILL_CHARGING
        elif state in ("ready", "available"):
            state = SKILL_READY
        elif state in ("unknown", "unsupported", "?"):
            state = SKILL_UNKNOWN
        else:
            state = SKILL_UNKNOWN
        remaining = _as_int(
            _first(
                payload,
                "remaining_ms",
                "remaining",
                "cooldown_ms",
                "cd_ms",
                "remaining_time_ms",
            ),
            0,
        )
        charges = _as_int(_first(payload, "charges", "current", "count"), 0)
        max_charges = _as_int(_first(payload, "max_charges", "max", "max_count"), 0)
        percent = _as_float(_first(payload, "percent", "percentage", "charge_percent"), 0.0)
        if percent and 0.0 <= percent <= 1.0 and _first(payload, "ratio") is not None:
            percent *= 100.0
        percent = min(max(percent, 0.0), 100.0)
        if state == SKILL_READY and kind == SLOT_ULTIMATE and percent == 0:
            percent = 100.0
        return cls(
            kind=kind,
            state=state,
            remaining_ms=max(0, remaining),
            percent=percent,
            charges=max(0, charges),
            max_charges=max(0, max_charges),
            raw=dict(payload),
        )

    @property
    def is_ready(self) -> bool:
        return self.state == SKILL_READY

    @property
    def is_charging(self) -> bool:
        return self.state == SKILL_CHARGING

    @property
    def is_unknown(self) -> bool:
        return self.state == SKILL_UNKNOWN

    def remaining_now(self, captured_at: int, server_now: int) -> int:
        """remaining_ms - (server_now - captured_at)，不小于 0。"""
        elapsed = max(0, int(server_now) - int(captured_at or 0))
        return max(0, int(self.remaining_ms) - elapsed)

    def effective_state(self, captured_at: int, server_now: int) -> str:
        if self.state == SKILL_CHARGING and self.remaining_now(captured_at, server_now) <= 0:
            return SKILL_READY
        return self.state


@dataclass(frozen=True)
class SkillState:
    """一个队友的技能快照（captured_at 为服务器毫秒时间）。"""

    user_id: str = ""
    nickname: str = ""
    operator: str = ""
    captured_at: int = 0
    slots: Mapping[str, SkillSlot] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_ws(cls, payload: Mapping[str, Any]) -> "SkillState":
        if not isinstance(payload, Mapping):
            payload = {}
        # 兼容 payload 内再包 user/state 的实现
        data = payload.get("state")
        if isinstance(data, Mapping):
            merged = dict(data)
            merged.update({key: value for key, value in payload.items() if key != "state"})
            payload = merged
        user = payload.get("user")
        user_map = user if isinstance(user, Mapping) else {}
        user_id = str(
            _first(payload, "user_id", "userId", "id")
            or _first(user_map, "id", "user_id")
            or ""
        )
        nickname = str(
            _first(payload, "nickname")
            or _first(user_map, "nickname", "username")
            or ""
        )
        operator_raw = payload.get("operator")
        if isinstance(operator_raw, Mapping):
            operator = str(_first(operator_raw, "name", "label", "id") or "")
        else:
            operator = str(operator_raw or payload.get("operator_name") or "")
        captured_at = _as_int(
            _first(payload, "captured_at", "capturedAt", "server_time", "updated_at"), 0
        )
        slots_raw = payload.get("skills")
        if not isinstance(slots_raw, Mapping):
            slots_raw = payload.get("skill_state")
        if not isinstance(slots_raw, Mapping):
            slots_raw = payload.get("slots")
        slots: dict[str, SkillSlot] = {}
        if isinstance(slots_raw, Mapping):
            for kind in SLOT_KINDS:
                if kind in slots_raw:
                    slots[kind] = SkillSlot.from_api(kind, slots_raw.get(kind))
        elif isinstance(slots_raw, list):
            for index, item in enumerate(slots_raw[:3]):
                kind = SLOT_KINDS[index]
                slots[kind] = SkillSlot.from_api(kind, item)
        for kind in SLOT_KINDS:
            slots.setdefault(kind, SkillSlot(kind=kind))
        return cls(
            user_id=user_id,
            nickname=nickname,
            operator=operator,
            captured_at=max(0, captured_at),
            slots=slots,
            raw=dict(payload),
        )

    def slot(self, kind: str) -> SkillSlot:
        return self.slots.get(kind) or SkillSlot(kind=kind)

    @property
    def display_name(self) -> str:
        return self.nickname or self.user_id or "未知队友"

    @property
    def avatar_letter(self) -> str:
        return (self.display_name.strip()[:1] or "?").upper()

    def is_unshared(self, server_now: int) -> bool:
        if not self.captured_at:
            return True
        return int(server_now) - int(self.captured_at) > UNSHARED_AFTER_MS


def parse_skill_state_list(payload: Any) -> list[SkillState]:
    """解析 ``room_joined.skill_states`` / ``skill_state.items`` / 裸数组。"""
    if isinstance(payload, Mapping):
        for key in ("skill_states", "items", "states"):
            value = payload.get(key)
            if isinstance(value, list):
                return [SkillState.from_ws(item) for item in value if isinstance(item, Mapping)]
        # 单个 state 对象
        if any(key in payload for key in ("skills", "skill_state", "user_id")):
            return [SkillState.from_ws(payload)]
        return []
    if isinstance(payload, list):
        return [SkillState.from_ws(item) for item in payload if isinstance(item, Mapping)]
    return []


def parse_room_joined_skill_states(message: Mapping[str, Any]) -> list[SkillState]:
    """``room_joined`` 可能带 ``skill_states`` 列表或 ``skill_state:{items:...}``。"""
    states = parse_skill_state_list(message.get("skill_states"))
    if states:
        return states
    return parse_skill_state_list(message.get("skill_state"))


class SkillBook:
    """按 user_id 缓存房间内所有队友的技能状态（保持插入顺序）。"""

    def __init__(self) -> None:
        self._states: dict[str, SkillState] = {}

    def __len__(self) -> int:
        return len(self._states)

    def clear(self) -> None:
        self._states.clear()

    def update(self, state: SkillState) -> None:
        if not state.user_id:
            return
        self._states[state.user_id] = state

    def update_many(self, states: Iterable[SkillState]) -> None:
        for state in states:
            self.update(state)

    def remove(self, user_id: str) -> bool:
        return self._states.pop(str(user_id), None) is not None

    def get(self, user_id: str) -> SkillState | None:
        return self._states.get(str(user_id))

    def states(self) -> list[SkillState]:
        return list(self._states.values())


def format_countdown(remaining_ms: int) -> str:
    """毫秒 -> ``m:ss``（只用于技能/投掷物 CD 展示）。"""
    seconds = max(0, int(remaining_ms) // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_percent(percent: float) -> str:
    return f"{int(round(min(max(float(percent), 0.0), 100.0)))}%"


class SkillShareThrottle:
    """技能上报本地限频：窗口内最多 ``max_events`` 次（默认 2 次/秒）。"""

    def __init__(
        self,
        max_events: int = 2,
        window_ms: int = 1000,
        clock=None,
    ) -> None:
        self.max_events = max(1, int(max_events))
        self.window_ms = max(1, int(window_ms))
        self._clock = clock
        self._events: list[float] = []

    def reset(self) -> None:
        self._events.clear()

    def allow(self, now_ms: float | None = None) -> bool:
        import time

        moment = float(now_ms if now_ms is not None else (self._clock() if self._clock else time.time() * 1000))
        cutoff = moment - self.window_ms
        self._events = [stamp for stamp in self._events if stamp > cutoff]
        if len(self._events) >= self.max_events:
            return False
        self._events.append(moment)
        return True
