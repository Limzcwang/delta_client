"""E3b2：单帧 HUD -> 槽位识别 -> SkillState 的流水线（可注入 OCR）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.hud_ocr import HudOcr, read_skill_bar_texts
from core.hud_profile import HudProfile
from core.hud_recognition import (
    SlotRecognition,
    mask_ratio,
    parse_charge,
    parse_percent,
    parse_seconds,
    recognize_secondary,
    recognize_ultimate,
)
from core.operators import Operator, OperatorCatalog
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState

logger = logging.getLogger(__name__)


@dataclass
class SlotDiagnostic:
    slot: int
    roi: tuple[int, int, int, int]
    texts: list[str] = field(default_factory=list)
    parsed: dict[str, Any] = field(default_factory=dict)
    mask_ratio: float = 0.0
    state: str = "unknown"
    remaining_ms: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "roi": list(self.roi),
            "texts": list(self.texts),
            "parsed": dict(self.parsed),
            "mask_ratio": round(float(self.mask_ratio), 4),
            "state": self.state,
            "remaining_ms": int(self.remaining_ms),
            "reason": self.reason,
        }


@dataclass
class RecognitionFrame:
    slots: dict[int, SlotRecognition] = field(default_factory=dict)
    operator_id: str = ""
    operator_name: str = ""
    texts: list[list[str]] = field(default_factory=list)
    diagnostics: list[SlotDiagnostic] = field(default_factory=list)

    def payload(self) -> list[dict[str, Any]]:
        return [self.slots[index].to_payload() for index in sorted(self.slots)]


def _slot_config(operator: Operator | None, slot: int):
    return operator.skill(slot) if operator is not None else None


def recognize_frame(
    frame: Any,
    profile: HudProfile,
    *,
    operator: Operator | None = None,
    ocr: HudOcr | None = None,
) -> RecognitionFrame:
    """识别一帧；识别失败/未知 CD 槽返回 unknown，不抛异常。"""
    ocr = ocr or HudOcr()
    rois = profile.slot_rois()
    result = RecognitionFrame(operator_id=operator.id if operator else "", operator_name=operator.display_name if operator else "")
    try:
        texts_per_slot = read_skill_bar_texts(ocr, frame, profile)
    except Exception:  # noqa: BLE001
        texts_per_slot = [[], [], []]
    result.texts = texts_per_slot
    for index, slot in enumerate((SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)):
        texts = texts_per_slot[index] if index < len(texts_per_slot) else []
        meta = _slot_config(operator, index)
        total_cd = meta.total_cd_ms if meta is not None else 0
        roi = rois[index]
        diagnostic = SlotDiagnostic(
            slot=index,
            roi=(roi.x, roi.y, roi.width, roi.height),
            texts=list(texts),
            parsed={
                "percent": parse_percent(texts),
                "seconds_ms": parse_seconds(texts),
                "charge": parse_charge(texts),
            },
        )
        if meta is not None and not meta.cd_known:
            result.slots[slot] = SlotRecognition(slot, "unknown", raw_texts=tuple(texts))
            diagnostic.reason = "配置未知 CD"
        elif slot == SLOT_ULTIMATE:
            recognized = recognize_ultimate(
                texts, total_cd or 0, meaning=profile.ult_pct_meaning
            )
            result.slots[slot] = recognized
            if recognized.state == "unknown":
                diagnostic.reason = "未读到百分比"
        else:
            ratio = 0.0
            if total_cd:
                try:
                    ratio = mask_ratio(
                        frame,
                        profile.mask_dark_threshold,
                        x=roi.x,
                        y=roi.y,
                        width=roi.width,
                        height=roi.height,
                    )
                except Exception:  # noqa: BLE001
                    ratio = 0.0
            diagnostic.mask_ratio = ratio
            recognized = recognize_secondary(
                slot,
                texts,
                total_cd or 0,
                meta.max_charges if meta is not None else 0,
                ratio=ratio,
            )
            result.slots[slot] = recognized
            if recognized.state == "unknown":
                if not texts and ratio <= 0:
                    diagnostic.reason = "未读到文本"
                elif ratio <= 0 and diagnostic.parsed["charge"] is not None:
                    diagnostic.reason = "只有充能数且缺少 CD/遮罩比例"
                elif ratio <= 0:
                    diagnostic.reason = "未解析出数字且遮罩比例低"
                else:
                    diagnostic.reason = "识别结果未知"
        diagnostic.state = result.slots[slot].state
        diagnostic.remaining_ms = int(result.slots[slot].remaining_ms)
        result.diagnostics.append(diagnostic)
        logger.debug(
            "HUD slot=%s roi=%s texts=%s parsed=%s mask_ratio=%.3f state=%s remaining_ms=%s reason=%s",
            diagnostic.slot,
            diagnostic.roi,
            diagnostic.texts,
            diagnostic.parsed,
            diagnostic.mask_ratio,
            diagnostic.state,
            diagnostic.remaining_ms,
            diagnostic.reason or "ok",
        )
    return result


def to_skill_state(
    recognized: RecognitionFrame,
    *,
    user_id: str,
    nickname: str,
    captured_at: int,
    operator_id: str = "",
    operator_name: str = "",
) -> SkillState:
    slots = []
    kinds = (SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)
    for index in range(3):
        recognized_slot = recognized.slots.get(index) or recognized.slots.get(kinds[index])
        item = (recognized_slot or SlotRecognition(index)).to_payload()
        item["slot"] = index
        slots.append(item)
    return SkillState.from_ws(
        {
            "user_id": user_id,
            "nickname": nickname,
            "operator_id": operator_id or recognized.operator_id,
            "operator_name": operator_name or recognized.operator_name,
            "captured_at": captured_at,
            "skills": slots,
        }
    )


def operator_from_catalog(catalog: OperatorCatalog, operator_id: str, operator_name: str = "") -> Operator | None:
    return catalog.resolve(operator_id, operator_name)
