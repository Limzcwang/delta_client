"""E3b2：单帧 HUD -> 槽位识别 -> SkillState 的流水线（可注入 OCR）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.hud_ocr import HudOcr, read_skill_bar_texts
from core.hud_profile import HudProfile
from core.hud_recognition import (
    SlotRecognition,
    mask_ratio,
    recognize_secondary,
    recognize_ultimate,
)
from core.operators import Operator, OperatorCatalog
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState


@dataclass
class RecognitionFrame:
    slots: dict[int, SlotRecognition] = field(default_factory=dict)
    operator_id: str = ""
    operator_name: str = ""
    texts: list[list[str]] = field(default_factory=list)

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
        if meta is not None and not meta.cd_known:
            result.slots[slot] = SlotRecognition(slot, "unknown", raw_texts=tuple(texts))
            continue
        if slot == SLOT_ULTIMATE:
            result.slots[slot] = recognize_ultimate(
                texts, total_cd or 0, meaning=profile.ult_pct_meaning
            )
            continue
        ratio = 0.0
        if total_cd:
            try:
                roi = rois[index]
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
        result.slots[slot] = recognize_secondary(
            slot,
            texts,
            total_cd or 0,
            meta.max_charges if meta is not None else 0,
            ratio=ratio,
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
