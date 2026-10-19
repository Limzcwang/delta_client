"""技能栏亮度判定 + 状态跳变 ready_at 估算。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.hud_profile import HudProfile
from core.hud_recognition import parse_charge, parse_duration_ms, parse_percent

READY_P90_THRESHOLD = 140
BRIGHT_PIXEL = 150


def p90_brightness(image: Any) -> tuple[float, float]:
    """返回 (灰度 p90, >150 亮像素比例)；无 numpy 时退回逐像素排序。"""
    if image is None:
        return 0.0, 0.0
    try:
        import numpy as np  # type: ignore[import-not-found]

        array = np.asarray(image)
        if array.ndim == 3:
            gray = 0.299 * array[:, :, 0] + 0.587 * array[:, :, 1] + 0.114 * array[:, :, 2]
        else:
            gray = array.astype(float)
        if gray.size == 0:
            return 0.0, 0.0
        p90 = float(np.percentile(gray, 90))
        ratio = float(np.mean(gray > BRIGHT_PIXEL))
        return p90, ratio
    except Exception:  # noqa: BLE001
        try:
            values = []
            for row in image:
                for pixel in row:
                    if hasattr(pixel, "__len__") and len(pixel) >= 3:
                        values.append(0.299 * pixel[0] + 0.587 * pixel[1] + 0.114 * pixel[2])
                    else:
                        values.append(float(pixel))
            if not values:
                return 0.0, 0.0
            values.sort()
            p90 = float(values[min(len(values) - 1, int(len(values) * 0.9))])
            return p90, sum(1 for value in values if value > BRIGHT_PIXEL) / len(values)
        except Exception:  # noqa: BLE001
            return 0.0, 0.0


@dataclass
class SkillTransitionTracker:
    states: dict[int, str] = field(default_factory=dict)
    ready_at: dict[int, int] = field(default_factory=dict)
    charges: dict[int, int] = field(default_factory=dict)

    def reset(self) -> None:
        self.states.clear()
        self.ready_at.clear()
        self.charges.clear()

    def update(self, slot: int, state: str, total_cd_ms: int, server_now: int) -> tuple[int, int, str]:
        """返回 (ready_at, remaining_ms, transition)。"""
        previous = self.states.get(slot)
        transition = ""
        if state == "ready":
            self.ready_at[slot] = 0
            remaining = 0
            if previous == "charging":
                transition = "charging->ready"
        else:
            if previous != "charging":
                self.ready_at[slot] = int(server_now) + max(0, int(total_cd_ms))
                transition = "ready->charging" if previous == "ready" else "charging-start"
            elif not self.ready_at.get(slot):
                self.ready_at[slot] = int(server_now) + max(0, int(total_cd_ms))
            ready_at = int(self.ready_at.get(slot) or 0)
            remaining = max(0, ready_at - int(server_now))
        self.states[slot] = state
        return int(self.ready_at.get(slot) or 0), remaining, transition


def recognize_frame_brightness(
    frame: Any,
    profile: HudProfile,
    *,
    operator: Any = None,
    ocr: Any = None,
    tracker: SkillTransitionTracker | None = None,
    server_now: int = 0,
    templates: dict[int, Any] | None = None,
) -> Any:
    """按每槽 p90 亮度判 ready/charging，状态跳变生成 ready_at。"""
    from core.hud_ocr import read_skill_bar_texts, read_text_roi_texts
    from core.hud_pipeline import RecognitionFrame, SlotDiagnostic, _slot_config
    from core.hud_recognition import SlotRecognition, charged_remaining_ms
    from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE

    tracker = tracker or SkillTransitionTracker()
    rois = profile.slot_rois()
    result = RecognitionFrame(
        operator_id=operator.id if operator else "",
        operator_name=operator.display_name if operator else "",
    )
    try:
        texts_per_slot = read_skill_bar_texts(ocr, frame, profile) if ocr is not None else [[], [], []]
    except Exception:  # noqa: BLE001
        texts_per_slot = [[], [], []]
    result.texts = texts_per_slot
    text_texts: list[list[str]] = [[], [], []]
    if ocr is not None:
        try:
            for index, roi in enumerate(profile.text_rois()):
                text_texts[index] = read_text_roi_texts(ocr, frame, roi, scale=3)
        except Exception:  # noqa: BLE001
            text_texts = [[], [], []]
    threshold = int(profile.brightness_threshold)
    from core.hud_band import charge_remaining_ms, measure_band_ratio
    from core.skill_icons import load_skill_icon_templates

    ready_templates = templates if templates is not None else (
        load_skill_icon_templates(operator.id) if operator is not None else {}
    )
    for index, slot in enumerate((SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)):
        roi = rois[index]
        crop = frame[roi.y : roi.bottom, roi.x : roi.right] if hasattr(frame, "__getitem__") else None
        p90, bright_ratio = p90_brightness(crop)
        texts = texts_per_slot[index] if index < len(texts_per_slot) else []
        row_texts = text_texts[index] if index < len(text_texts) else []
        meta = _slot_config(operator, index)
        total_cd = int(meta.total_cd_ms or 0) if meta is not None else 0
        max_charges = max(1, min(9, int(meta.max_charges if meta is not None else 1)))
        seconds = parse_duration_ms(row_texts)
        pct = parse_percent(row_texts) if index == 0 else None
        charge = parse_charge(texts)
        charges = 0
        band_ratio_value = 0.0
        text_reason = ""
        if index == 0:
            if seconds is not None:
                state = "charging"
                remaining = int(seconds)
                ready_at = int(server_now) + remaining
                transition = "text-seconds"
                tracker.states[0] = "charging"
                tracker.ready_at[0] = ready_at
                text_reason = "文字秒数"
            elif pct is not None:
                if pct >= 100:
                    state, remaining, ready_at, transition = "ready", 0, 0, "pct-ready"
                    tracker.states[0] = "ready"
                    tracker.ready_at[0] = 0
                else:
                    state = "charging"
                    remaining = charged_remaining_ms(int(pct), total_cd, profile.ult_pct_meaning)
                    ready_at = int(server_now) + remaining
                    transition = "pct"
                    tracker.states[0] = "charging"
                    tracker.ready_at[0] = ready_at
                text_reason = "百分比"
            else:
                state = "ready" if p90 >= threshold else "charging"
                ready_at, remaining, transition = tracker.update(0, state, total_cd, server_now)
                text_reason = "未读到文字，回退 p90"
            charges = 1 if state != "unknown" else 0
        else:
            charges = max(0, min(max_charges, int(charge))) if charge is not None else tracker.charges.get(index, 0)
            if seconds is not None:
                state = "charging"
                remaining = int(seconds)
                ready_at = int(server_now) + remaining
                transition = "text-seconds"
                tracker.states[index] = "charging"
                tracker.ready_at[index] = ready_at
                text_reason = "文字秒数"
            elif charge is not None and charges < max_charges:
                band = measure_band_ratio(crop, ready_templates.get(index))
                band_ratio_value = band.area_ratio if band is not None else 0.0
                if band is not None:
                    state = "charging"
                    remaining = charge_remaining_ms(band, total_cd, max_charges)
                    ready_at = int(server_now) + remaining
                    transition = "charge-band"
                    text_reason = f"灰带充能 f={band_ratio_value:.2f}"
                    tracker.states[index] = "charging"
                    tracker.ready_at[index] = ready_at
                else:
                    state = "ready" if p90 >= threshold else "charging"
                    ready_at, remaining, transition = tracker.update(index, state, total_cd, server_now)
                    text_reason = "无就绪模板，回退 p90"
            elif charge is not None and charges >= max_charges:
                state, remaining, ready_at, transition = "ready", 0, 0, "charge-full"
                tracker.states[index] = "ready"
                tracker.ready_at[index] = 0
                text_reason = "充能已满"
            else:
                state = "ready" if p90 >= threshold else "charging"
                ready_at, remaining, transition = tracker.update(index, state, total_cd, server_now)
                text_reason = "未读到文字，回退 p90"
            tracker.charges[index] = charges
        result.slots[slot] = SlotRecognition(
            slot,
            state,
            remaining_ms=remaining,
            ready_at=ready_at,
            percent=float(pct or 0.0),
            charges=charges,
            max_charges=1 if index == 0 else max_charges,
            source="brightness",
            raw_texts=tuple(texts),
        )
        result.diagnostics.append(
            SlotDiagnostic(
                slot=index,
                roi=(roi.x, roi.y, roi.width, roi.height),
                texts=list(texts),
                parsed={"percent": pct, "charge": charge, "seconds_ms": seconds},
                mask_ratio=0.0,
                p90=round(p90, 2),
                bright_ratio=round(bright_ratio, 4),
                band_ratio=round(band_ratio_value, 4),
                transition=transition,
                text_texts=list(row_texts),
                text_reason=text_reason,
                state=state,
                remaining_ms=int(remaining),
                reason=(
                    f"p90={p90:.1f} {'>= ' if p90 >= threshold else '< '}阈值 {threshold}，"
                    f"亮比例={bright_ratio:.3f}，{text_reason or transition or 'steady'}"
                ),
                expanded_roi=None,
            )
        )
    return result
