"""E2/E3b：技能上报 payload 的类型/范围/NaN 清洗与自检。"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from core.skills import (
    SLOT_ABILITY,
    SLOT_KINDS,
    SLOT_THROWABLE,
    SLOT_ULTIMATE,
    SKILL_CHARGING,
    SKILL_READY,
    SKILL_STATES,
    SKILL_UNKNOWN,
    SkillState,
)

MAX_REMAINING_MS = 600_000
MAX_CHARGES = 999


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def clamp_int(value: Any, low: int, high: int) -> int | None:
    number = _finite(value)
    if number is None:
        return None
    return int(round(max(float(low), min(float(high), number))))


def clean_pct(value: Any) -> int | None:
    return clamp_int(value, 0, 100)


def clean_remaining(value: Any) -> int | None:
    return clamp_int(value, 0, MAX_REMAINING_MS)


def clean_charge(value: Any) -> int | None:
    return clamp_int(value, 0, MAX_CHARGES)


def _clean_state(value: Any) -> str:
    state = str(value or "").strip().lower()
    return state if state in SKILL_STATES else SKILL_UNKNOWN


def sanitize_slot(index: int, slot: Any) -> dict[str, Any]:
    """单个槽 -> 后端可接受字段；任何非法值将该槽降级 unknown。"""
    kind = SLOT_KINDS[index]
    state = _clean_state(getattr(slot, "state", None))
    if state == SKILL_UNKNOWN:
        return {"slot": index, "state": SKILL_UNKNOWN}
    if kind == SLOT_ULTIMATE:
        pct = clean_pct(getattr(slot, "percent", None))
        if state == SKILL_CHARGING and pct is None:
            return {"slot": index, "state": SKILL_UNKNOWN}
        remaining = 0 if state == SKILL_READY else clean_remaining(getattr(slot, "remaining_ms", None))
        if state == SKILL_CHARGING and remaining is None:
            return {"slot": index, "state": SKILL_UNKNOWN}
        item: dict[str, Any] = {"slot": index, "state": state}
        if pct is not None:
            item["pct"] = pct
        item["remaining_ms"] = remaining or 0
        return item
    remaining = clean_remaining(getattr(slot, "remaining_ms", None))
    if state == SKILL_CHARGING and remaining is None:
        return {"slot": index, "state": SKILL_UNKNOWN}
    max_charges = clean_charge(getattr(slot, "max_charges", None)) or 0
    charges = clean_charge(getattr(slot, "charges", None)) or 0
    if max_charges and charges > max_charges:
        charges = max_charges
    item = {"slot": index, "state": state}
    if max_charges:
        item["charges"] = charges
        item["max_charges"] = max_charges
    item["remaining_ms"] = remaining if remaining is not None else 0
    return item


def build_payload_from_state(state: SkillState) -> list[dict[str, Any]]:
    return [sanitize_slot(index, state.slot(kind)) for index, kind in enumerate(SLOT_KINDS)]


def validate_payload(payload: Any) -> tuple[bool, str]:
    """后端同规则自检；不合法返回 (False, 原因)。"""
    if not isinstance(payload, list) or len(payload) != 3:
        return False, "payload 必须是 3 个槽的数组"
    seen: set[int] = set()
    for item in payload:
        if not isinstance(item, Mapping):
            return False, "槽位必须是对象"
        slot = item.get("slot")
        if not isinstance(slot, int) or isinstance(slot, bool) or slot not in (0, 1, 2):
            return False, "slot 必须是 0/1/2 整数"
        if slot in seen:
            return False, "slot 重复"
        seen.add(slot)
        state = item.get("state")
        if state not in SKILL_STATES:
            return False, "state 非法"
        if state == SKILL_UNKNOWN:
            continue
        remaining = item.get("remaining_ms", 0)
        if not isinstance(remaining, int) or isinstance(remaining, bool) or not (0 <= remaining <= MAX_REMAINING_MS):
            return False, "remaining_ms 必须是 0-600000 整数"
        if slot == 0:
            pct = item.get("pct")
            if pct is not None and (
                not isinstance(pct, int) or isinstance(pct, bool) or not (0 <= pct <= 100)
            ):
                return False, "pct 必须是 0-100 整数或空"
        for key in ("charges", "max_charges"):
            value = item.get(key)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or not (0 <= value <= MAX_CHARGES)
            ):
                return False, f"{key} 必须是非负整数"
    return True, ""


def clean_captured_at(value: Any) -> int | None:
    """captured_at 必须是整数毫秒（可接受有限数字/数字字符串，拒绝 float 小数/NaN）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return int(value) if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None
