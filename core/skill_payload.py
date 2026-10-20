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
MAX_CHARGES = 9
MIN_CHARGES = 1


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


def _unknown(index: int) -> dict[str, Any]:
    # 后端对每个槽（含 unknown/大招）都要求 charges/max_charges 合法
    return {
        "slot": index,
        "state": SKILL_UNKNOWN,
        "remaining_ms": 0,
        "charges": 0,
        "max_charges": 1,
    }


def sanitize_slot(index: int, slot: Any) -> dict[str, Any]:
    """单个槽 -> 后端可接受字段；所有槽都输出 charges/max_charges。"""
    kind = SLOT_KINDS[index]
    state = _clean_state(getattr(slot, "state", None))
    if state == SKILL_UNKNOWN:
        return _unknown(index)
    if kind == SLOT_ULTIMATE:
        pct = clean_pct(getattr(slot, "percent", None))
        if state == SKILL_CHARGING and pct is None:
            return _unknown(index)
        remaining = 0 if state == SKILL_READY else clean_remaining(getattr(slot, "remaining_ms", None))
        if state == SKILL_CHARGING and remaining is None:
            return _unknown(index)
        item: dict[str, Any] = {
            "slot": index,
            "state": state,
            "remaining_ms": remaining or 0,
            "charges": 1,
            "max_charges": 1,
        }
        if pct is not None:
            item["pct"] = pct
        ready_at = clamp_int(getattr(slot, "ready_at", None), 0, 2**53 - 1)
        if ready_at:
            item["ready_at"] = ready_at
        return item
    remaining = clean_remaining(getattr(slot, "remaining_ms", None))
    if state == SKILL_CHARGING and remaining is None:
        return _unknown(index)
    raw_max = _finite(getattr(slot, "max_charges", None))
    if raw_max is None or raw_max < MIN_CHARGES:
        max_charges = 1
    else:
        max_charges = int(round(min(float(MAX_CHARGES), raw_max)))
    charges = clamp_int(getattr(slot, "charges", None), 0, max_charges)
    if charges is None:
        charges = 0
    item = {
        "slot": index,
        "state": state,
        "remaining_ms": remaining if remaining is not None else 0,
        "charges": charges,
        "max_charges": max_charges,
    }
    ready_at = clamp_int(getattr(slot, "ready_at", None), 0, 2**53 - 1)
    if ready_at:
        item["ready_at"] = ready_at
    return item


def build_payload_from_state(state: SkillState) -> list[dict[str, Any]]:
    return [sanitize_slot(index, state.slot(kind)) for index, kind in enumerate(SLOT_KINDS)]


def serialize_skill_state(state: SkillState) -> list[dict[str, Any]]:
    """唯一序列化入口：清洗 + 单槽修复；所有 skill_share_update 必须走这里。"""
    return repair_payload(build_payload_from_state(state))


def _validate_slot(item: Any) -> tuple[bool, str]:
    if not isinstance(item, Mapping):
        return False, "槽位必须是对象"
    slot = item.get("slot")
    if not isinstance(slot, int) or isinstance(slot, bool) or slot not in (0, 1, 2):
        return False, "slot 必须是 0/1/2 整数"
    state = item.get("state")
    if state not in SKILL_STATES:
        return False, "state 非法"
    remaining = item.get("remaining_ms", 0)
    if not isinstance(remaining, int) or isinstance(remaining, bool) or not (0 <= remaining <= MAX_REMAINING_MS):
        return False, "remaining_ms 必须是 0-600000 整数"
    if slot == 0 and state != SKILL_UNKNOWN:
        pct = item.get("pct")
        if pct is not None and (
            not isinstance(pct, int) or isinstance(pct, bool) or not (0 <= pct <= 100)
        ):
            return False, "pct 必须是 0-100 整数或空"
    max_charges = item.get("max_charges")
    if (
        not isinstance(max_charges, int)
        or isinstance(max_charges, bool)
        or not (MIN_CHARGES <= max_charges <= MAX_CHARGES)
    ):
        return False, "max_charges 必须是 1-9 整数"
    charges = item.get("charges")
    if (
        not isinstance(charges, int)
        or isinstance(charges, bool)
        or not (0 <= charges <= max_charges)
    ):
        return False, "charges 必须是 0..max_charges 整数"
    ready_at = item.get("ready_at")
    if ready_at is not None and (
        not isinstance(ready_at, int) or isinstance(ready_at, bool) or ready_at < 0
    ):
        return False, "ready_at 必须是非负整数"
    return True, ""


def validate_payload(payload: Any) -> tuple[bool, str]:
    """后端同规则自检；不合法返回 (False, 原因)。"""
    if not isinstance(payload, list) or len(payload) != 3:
        return False, "payload 必须是 3 个槽的数组"
    seen: set[int] = set()
    for item in payload:
        ok, reason = _validate_slot(item)
        if not ok:
            return False, reason
        slot = int(item["slot"])
        if slot in seen:
            return False, "slot 重复"
        seen.add(slot)
    return True, ""


def repair_payload(payload: Any) -> list[dict[str, Any]]:
    """单槽非法只降级该槽为 unknown，避免整条 payload 被后端拒绝。"""
    if not isinstance(payload, list):
        return [_unknown(index) for index in range(3)]
    by_slot: dict[int, Mapping[str, Any]] = {}
    for item in payload:
        if isinstance(item, Mapping):
            slot = item.get("slot")
            if isinstance(slot, int) and not isinstance(slot, bool) and slot in (0, 1, 2):
                by_slot.setdefault(slot, item)
    repaired: list[dict[str, Any]] = []
    for index in range(3):
        item = by_slot.get(index)
        ok, _reason = _validate_slot(item) if item is not None else (False, "")
        if ok and int(item["slot"]) == index:
            repaired.append(dict(item))
        else:
            repaired.append(_unknown(index))
    return repaired


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

