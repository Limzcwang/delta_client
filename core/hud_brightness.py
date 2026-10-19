"""技能栏亮度判定 + 状态跳变 ready_at 估算。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.hud_profile import HudProfile
from core.hud_recognition import parse_charge, parse_percent

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
) -> Any:
    """按每槽 p90 亮度判 ready/charging，状态跳变生成 ready_at。"""
    from core.hud_ocr import read_skill_bar_texts
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
    threshold = int(profile.brightness_threshold)
    for index, slot in enumerate((SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)):
        roi = rois[index]
        crop = frame[roi.y : roi.bottom, roi.x : roi.right] if hasattr(frame, "__getitem__") else None
        p90, bright_ratio = p90_brightness(crop)
        texts = texts_per_slot[index] if index < len(texts_per_slot) else []
        meta = _slot_config(operator, index)
        total_cd = int(meta.total_cd_ms or 0) if meta is not None else 0
        max_charges = max(1, min(9, int(meta.max_charges if meta is not None else 1)))
        pct = parse_percent(texts) if index == 0 else None
        if index == 0 and pct is not None:
            if pct >= 100:
                state = "ready"
                remaining = 0
                ready_at = 0
                transition = "pct-ready"
                tracker.states[0] = "ready"
                tracker.ready_at[0] = 0
            else:
                state = "charging"
                remaining = charged_remaining_ms(int(pct), total_cd, profile.ult_pct_meaning)
                ready_at = int(server_now) + remaining
                transition = "pct"
                tracker.states[0] = "charging"
                tracker.ready_at[0] = ready_at
        else:
            state = "ready" if p90 >= threshold else "charging"
            ready_at, remaining, transition = tracker.update(index, state, total_cd, server_now)
        charge = parse_charge(texts)
        if index == 0:
            charges = 1 if state != "unknown" else 0
        else:
            if charge is not None:
                charges = max(0, min(max_charges, int(charge)))
            elif state == "ready":
                charges = max_charges
            else:
                charges = tracker.charges.get(index, 0)
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
                parsed={"percent": pct, "charge": charge},
                mask_ratio=0.0,
                state=state,
                remaining_ms=int(remaining),
                reason=(
                    f"p90={p90:.1f} {'>= ' if p90 >= threshold else '< '}阈值 {threshold}，"
                    f"亮比例={bright_ratio:.3f}，{transition or 'steady'}"
                ),
                expanded_roi=None,
            )
        )
        # 附加诊断字段（dataclass 未声明时通过临时属性仍是可读的；导出使用 to_dict 扩展）
        result.diagnostics[-1].p90 = round(p90, 2)
        result.diagnostics[-1].bright_ratio = round(bright_ratio, 4)
        result.diagnostics[-1].transition = transition
    return result
