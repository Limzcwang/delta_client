"""E3b2：单帧 HUD -> 槽位识别 -> SkillState 的流水线（可注入 OCR）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.hud_ocr import HudOcr, read_roi_texts, read_skill_bar_texts
from core.hud_profile import HudProfile
from core.hud_recognition import (
    SlotRecognition,
    charged_remaining_ms,
    mask_ratio,
    parse_charge,
    parse_percent,
    parse_seconds,
    recognize_secondary,
    recognize_ultimate,
)
from core.operators import Operator, OperatorCatalog
from core.skill_icons import load_skill_icon_templates, match_icon_score
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState

logger = logging.getLogger(__name__)


@dataclass
class SlotDiagnostic:
    slot: int
    roi: tuple[int, int, int, int]
    texts: list[str] = field(default_factory=list)
    parsed: dict[str, Any] = field(default_factory=dict)
    mask_ratio: float = 0.0
    icon_score: float = 0.0
    expanded_roi: tuple[int, int, int, int] | None = None
    p90: float = 0.0
    bright_ratio: float = 0.0
    band_ratio: float = 0.0
    transition: str = ""
    text_texts: list[str] = field(default_factory=list)
    text_reason: str = ""
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
            "icon_score": round(float(self.icon_score), 4),
            "expanded_roi": list(self.expanded_roi) if self.expanded_roi else None,
            "p90": round(float(self.p90), 2),
            "bright_ratio": round(float(self.bright_ratio), 4),
            "band_ratio": round(float(self.band_ratio), 4),
            "transition": self.transition,
            "text_texts": list(self.text_texts),
            "text_reason": self.text_reason,
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


def _expanded_ultimate_roi(roi: Any) -> Any:
    from core.hud_profile import Roi

    width = max(1, int(roi.width))
    height = max(1, int(roi.height))
    return Roi(
        int(roi.x + round(width * 0.2)),
        int(roi.y),
        max(1, int(round(width * 0.6))),
        max(1, int(round(height * 1.4))),
    )


def _expanded_ocr(ocr: HudOcr, frame: Any, profile: HudProfile, roi: Any) -> tuple[Any, list[str]]:
    expanded = _expanded_ultimate_roi(roi)
    try:
        height, width = int(frame.shape[0]), int(frame.shape[1])
        expanded = expanded.clamp(width, height)
    except Exception:  # noqa: BLE001
        pass
    texts = read_roi_texts(ocr, frame, expanded, profile.ocr_threshold)
    return expanded, texts


def _recognize_frame_icons(
    frame: Any,
    profile: HudProfile,
    operator: Operator,
    ocr: HudOcr,
    templates: dict[int, Any],
) -> RecognitionFrame:
    """图标优先：先确认槽位图标，再按遮罩/OCR 判定充能状态。"""
    rois = profile.slot_rois()
    result = RecognitionFrame(operator_id=operator.id, operator_name=operator.display_name)
    try:
        texts_per_slot = read_skill_bar_texts(ocr, frame, profile)
    except Exception:  # noqa: BLE001
        texts_per_slot = [[], [], []]
    result.texts = texts_per_slot
    threshold = float(profile.skill_icon_threshold)
    for index, slot in enumerate((SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)):
        roi = rois[index]
        texts = texts_per_slot[index] if index < len(texts_per_slot) else []
        meta = _slot_config(operator, index)
        total_cd = meta.total_cd_ms if meta is not None else 0
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
        template = templates.get(index)
        score, hit = match_icon_score(frame, roi, template, threshold) if template is not None else (0.0, False)
        diagnostic.icon_score = score
        ratio = 0.0
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
        if index == 0 and diagnostic.parsed["percent"] is None:
            expanded, expanded_texts = _expanded_ocr(ocr, frame, profile, roi)
            pct = parse_percent(expanded_texts)
            diagnostic.expanded_roi = (expanded.x, expanded.y, expanded.width, expanded.height)
            if expanded_texts:
                texts = list(texts) + [text for text in expanded_texts if text not in texts]
                diagnostic.texts = list(texts)
            diagnostic.parsed["percent"] = pct
            if pct is None:
                diagnostic.reason = "百分比未读到（已扩展 ROI 重试）"
        if not hit:
            result.slots[slot] = SlotRecognition(slot, "unknown", raw_texts=tuple(texts))
            diagnostic.reason = f"技能图标未命中（{score:.2f} < {threshold:.2f}）"
        elif index == 0:
            pct = diagnostic.parsed["percent"]
            if pct is not None:
                if pct >= 100:
                    recognized = SlotRecognition(slot, "ready", percent=100.0, raw_texts=tuple(texts))
                else:
                    recognized = SlotRecognition(
                        slot,
                        "charging",
                        remaining_ms=charged_remaining_ms(int(pct), total_cd or 0, profile.ult_pct_meaning),
                        percent=float(pct),
                        raw_texts=tuple(texts),
                    )
            elif ratio > 0.01:
                recognized = SlotRecognition(
                    slot,
                    "charging",
                    remaining_ms=max(0, int(round(ratio * max(0, total_cd or 0)))),
                    charges=0,
                    max_charges=1,
                    source="icon_mask",
                    raw_texts=tuple(texts),
                )
            else:
                recognized = SlotRecognition(
                    slot,
                    "ready",
                    charges=1,
                    max_charges=1,
                    source="icon_ready",
                    raw_texts=tuple(texts),
                )
            if recognized.state == "charging":
                recognized = SlotRecognition(
                    slot,
                    recognized.state,
                    remaining_ms=recognized.remaining_ms,
                    percent=recognized.percent,
                    charges=1,
                    max_charges=1,
                    source=recognized.source,
                    raw_texts=recognized.raw_texts,
                )
            result.slots[slot] = recognized
            if recognized.state == "charging" and diagnostic.parsed["percent"] is None:
                diagnostic.reason = "无百分比，按遮罩比例估算"
        else:
            max_charges = max(1, min(9, int(meta.max_charges if meta is not None else 1)))
            seconds = diagnostic.parsed["seconds_ms"]
            charge = diagnostic.parsed["charge"]
            if seconds is not None:
                state = "charging" if seconds > 0 else "ready"
                remaining = int(seconds)
            elif ratio > 0.01:
                state = "charging"
                remaining = max(0, int(round(ratio * max(0, total_cd or 0))))
            else:
                state = "ready"
                remaining = 0
            if charge is None:
                charges = max_charges if state == "ready" else 0
                diagnostic.reason = "充能 OCR 失败，按遮罩比例/满充判断"
            else:
                charges = max(0, min(max_charges, int(charge)))
            if state == "ready":
                charges = max_charges
            result.slots[slot] = SlotRecognition(
                slot,
                state,
                remaining_ms=remaining,
                charges=charges,
                max_charges=max_charges,
                source="icon_mask" if seconds is None else "icon_ocr",
                raw_texts=tuple(texts),
            )
        diagnostic.state = result.slots[slot].state
        diagnostic.remaining_ms = int(result.slots[slot].remaining_ms)
        result.diagnostics.append(diagnostic)
        logger.debug(
            "HUD icon slot=%s roi=%s texts=%s parsed=%s icon_score=%.3f mask_ratio=%.3f state=%s remaining_ms=%s reason=%s",
            diagnostic.slot,
            diagnostic.roi,
            diagnostic.texts,
            diagnostic.parsed,
            diagnostic.icon_score,
            diagnostic.mask_ratio,
            diagnostic.state,
            diagnostic.remaining_ms,
            diagnostic.reason or "ok",
        )
    return result


def recognize_frame(
    frame: Any,
    profile: HudProfile,
    *,
    operator: Operator | None = None,
    ocr: HudOcr | None = None,
    tracker: Any = None,
    server_now: int = 0,
    use_icons: bool = False,
    ) -> RecognitionFrame:
    """默认亮度/状态跳变识别；use_icons 仅供旧模板实验，不参与生产。"""
    ocr = ocr or HudOcr()
    if use_icons:
        templates = load_skill_icon_templates(operator.id) if operator is not None else {}
        if templates and len(templates) == 3 and hasattr(frame, "shape") and len(getattr(frame, "shape", ())) >= 2:
            return _recognize_frame_icons(frame, profile, operator, ocr, templates)
    if hasattr(frame, "shape") and len(getattr(frame, "shape", ())) >= 2:
        from core.hud_brightness import recognize_frame_brightness

        return recognize_frame_brightness(
            frame, profile, operator=operator, ocr=ocr, tracker=tracker, server_now=server_now
        )
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
            if diagnostic.parsed["percent"] is None:
                expanded, expanded_texts = _expanded_ocr(ocr, frame, profile, roi)
                diagnostic.expanded_roi = (expanded.x, expanded.y, expanded.width, expanded.height)
                if expanded_texts:
                    texts = list(texts) + [text for text in expanded_texts if text not in texts]
                    diagnostic.texts = list(texts)
                diagnostic.parsed["percent"] = parse_percent(texts)
            recognized = recognize_ultimate(
                texts, total_cd or 0, meaning=profile.ult_pct_meaning
            )
            result.slots[slot] = recognized
            if recognized.state == "unknown":
                diagnostic.reason = "未读到百分比（已扩展 ROI 重试）"
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
