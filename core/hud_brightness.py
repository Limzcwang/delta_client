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
    charge_t0: dict[int, int] = field(default_factory=dict)
    last_charges: dict[int, int] = field(default_factory=dict)
    bright_b0: dict[int, float] = field(default_factory=dict)
    band_progress: dict[int, float] = field(default_factory=dict)
    pending_state: dict[int, str] = field(default_factory=dict)
    pending_state_count: dict[int, int] = field(default_factory=dict)
    pending_charge: dict[int, int] = field(default_factory=dict)
    pending_charge_count: dict[int, int] = field(default_factory=dict)
    full_pending: dict[int, bool] = field(default_factory=dict)

    def reset(self) -> None:
        self.states.clear()
        self.ready_at.clear()
        self.charges.clear()
        self.charge_t0.clear()
        self.last_charges.clear()
        self.bright_b0.clear()
        self.band_progress.clear()
        self.pending_state.clear()
        self.pending_state_count.clear()
        self.pending_charge.clear()
        self.pending_charge_count.clear()
        self.full_pending.clear()

    def observe_brightness(
        self, slot: int, raw_state: str, total_cd_ms: int, server_now: int, debounce: int = 2
    ) -> tuple[int, int, str, str]:
        """亮度事件去抖：连续 debounce 帧确认后才提交状态跳变。"""
        stable = self.states.get(slot)
        if stable is None:
            self.states[slot] = raw_state
            if raw_state == "ready":
                self.ready_at[slot] = 0
                return 0, 0, "ready", ""
            self.ready_at[slot] = int(server_now) + max(0, int(total_cd_ms))
            return self.ready_at[slot], max(0, int(total_cd_ms)), "charging", ""
        if raw_state == stable:
            self.pending_state[slot] = raw_state
            self.pending_state_count[slot] = 0
            if stable == "ready":
                return 0, 0, "ready", ""
            ready_at = int(self.ready_at.get(slot) or 0)
            return ready_at, max(0, ready_at - int(server_now)), "charging", ""
        self.pending_state[slot] = raw_state
        self.pending_state_count[slot] = self.pending_state_count.get(slot, 0) + 1
        if self.pending_state_count[slot] < max(1, int(debounce)):
            ready_at = int(self.ready_at.get(slot) or 0)
            return ready_at, max(0, ready_at - int(server_now)) if stable == "charging" else 0, stable, ""
        event = ""
        self.pending_state_count[slot] = 0
        self.states[slot] = raw_state
        if raw_state == "charging":
            if stable == "ready":
                event = "cast"
            self.ready_at[slot] = int(server_now) + max(0, int(total_cd_ms))
            return self.ready_at[slot], max(0, int(total_cd_ms)), "charging", event
        self.ready_at[slot] = 0
        return 0, 0, "ready", "recover" if stable == "charging" else ""

    def observe_charge(
        self,
        slot: int,
        raw_charges: int,
        max_charges: int,
        charge_cd_ms: int,
        total_cd_ms: int,
        server_now: int,
        debounce: int = 2,
        text_remaining_ms: int | None = None,
    ) -> tuple[int, int, int, str, str]:
        """充能事件去抖：返回 (charges, ready_at, remaining, state, event)。"""
        stable = self.last_charges.get(slot)
        raw = max(0, min(int(max_charges), int(raw_charges)))
        if stable is None:
            self.last_charges[slot] = raw
            self.charges[slot] = raw
            if text_remaining_ms is not None:
                if int(text_remaining_ms) <= 0:
                    self.states[slot] = "ready"
                    self.ready_at[slot] = int(server_now)
                    return raw, int(server_now), 0, "ready", "text-ready"
                ready_at, remaining, transition = self.update_charge(
                    slot, raw, max_charges, charge_cd_ms, server_now, text_remaining_ms=text_remaining_ms
                )
                return raw, ready_at, remaining, "charging", transition
            if raw >= max_charges:
                self.states[slot] = "ready"
                self.ready_at[slot] = 0
                return raw, 0, 0, "ready", ""
            self.states[slot] = "charging"
            self.ready_at[slot] = int(server_now) + max(0, int(charge_cd_ms))
            return raw, self.ready_at[slot], max(0, int(charge_cd_ms)), "charging", ""
        if raw != stable:
            if text_remaining_ms is None:
                self.pending_charge[slot] = raw
                self.pending_charge_count[slot] = self.pending_charge_count.get(slot, 0) + 1
                if self.pending_charge_count[slot] < max(1, int(debounce)):
                    ready_at = int(self.ready_at.get(slot) or 0)
                    state = self.states.get(slot, "charging")
                    return stable, ready_at, max(0, ready_at - int(server_now)), state, ""
            self.pending_charge_count[slot] = 0
        else:
            self.pending_charge_count[slot] = 0
        previous = stable
        self.last_charges[slot] = raw
        self.charges[slot] = raw
        if text_remaining_ms is not None:
            if int(text_remaining_ms) <= 0:
                self.states[slot] = "ready"
                self.ready_at[slot] = int(server_now)
                self.full_pending[slot] = False
                return raw, int(server_now), 0, "ready", "text-ready"
            ready_at, remaining, _transition = self.update_charge(
                slot, raw, max_charges, charge_cd_ms, server_now, text_remaining_ms=text_remaining_ms
            )
            return raw, ready_at, remaining, "charging", "text"
        if raw < previous:
            duration = int(total_cd_ms) if raw == 0 else int(charge_cd_ms)
            self.charge_t0[slot] = int(server_now)
            self.ready_at[slot] = int(server_now) + max(0, duration)
            self.states[slot] = "charging"
            self.full_pending[slot] = False
            return raw, self.ready_at[slot], max(0, duration), "charging", "cast"
        if raw > previous:
            duration = int(charge_cd_ms)
            self.charge_t0[slot] = int(server_now)
            self.ready_at[slot] = int(server_now) + max(0, duration)
            self.states[slot] = "charging"
            # 1->2：先保守判 charging，下一帧仍保持 max 才 ready
            self.full_pending[slot] = raw >= max_charges
            return raw, self.ready_at[slot], max(0, duration), "charging", "recover"
        if raw >= max_charges:
            if self.full_pending.get(slot):
                self.full_pending[slot] = False
                self.states[slot] = "ready"
                self.ready_at[slot] = 0
                return raw, 0, 0, "ready", "recover"
            self.states[slot] = "ready"
            self.ready_at[slot] = 0
            return raw, 0, 0, "ready", ""
        ready_at = int(self.ready_at.get(slot) or 0)
        state = self.states.get(slot, "charging")
        return raw, ready_at, max(0, ready_at - int(server_now)), state, ""

    def update_band(
        self,
        slot: int,
        bright_count: int,
        charge_cd_ms: int,
        server_now: int,
        charges: int,
        max_charges: int,
    ) -> tuple[str | None, int, int, float]:
        """B/B0 灰带：返回 (state|None, remaining, ready_at, progress)。"""
        current = float(max(0, int(bright_count)))
        if charges >= max_charges:
            self.bright_b0[slot] = current
            self.band_progress[slot] = 1.0
            return "ready", 0, 0, 1.0
        b0 = self.bright_b0.get(slot)
        if b0 is None or b0 <= 0:
            self.bright_b0[slot] = current
            return None, 0, 0, 0.0
        ratio = current / b0
        if ratio >= 0.9:
            self.band_progress[slot] = 1.0
            return "ready", 0, 0, 1.0
        if ratio > 0.1:
            progress = max(0.0, min(1.0, 1.0 - ratio))
            remaining = max(0, int(round(ratio * max(0, int(charge_cd_ms)))))
            ready_at = int(server_now) + remaining
            self.band_progress[slot] = progress
            return "charging", remaining, ready_at, progress
        return None, 0, 0, 0.0

    def update_charge(
        self,
        slot: int,
        charges: int,
        max_charges: int,
        charge_cd_ms: int,
        server_now: int,
        *,
        text_remaining_ms: int | None = None,
    ) -> tuple[int, int, str]:
        """充能技能：文字值重同步，否则 charges 变化/保持 t0 计时。"""
        charges = max(0, min(int(max_charges), int(charges)))
        previous = self.last_charges.get(slot)
        now = int(server_now)
        if text_remaining_ms is not None:
            ready_at = now + max(0, int(text_remaining_ms))
            self.charge_t0[slot] = now
            self.last_charges[slot] = charges
            self.charges[slot] = charges
            self.states[slot] = "charging" if text_remaining_ms > 0 else "ready"
            self.ready_at[slot] = 0 if text_remaining_ms <= 0 else ready_at
            return self.ready_at[slot], max(0, int(text_remaining_ms)), "text-resync"
        if charges >= max_charges:
            self.last_charges[slot] = charges
            self.charges[slot] = charges
            self.states[slot] = "ready"
            self.ready_at[slot] = 0
            return 0, 0, "charge-full"
        if previous is None:
            self.charge_t0[slot] = now
            transition = "charge-init"
        elif charges < previous:
            self.charge_t0[slot] = now
            transition = "charge-decrease"
        elif charges > previous:
            self.charge_t0[slot] = now
            transition = "charge-increase"
        else:
            transition = "charge-steady"
        self.last_charges[slot] = charges
        self.charges[slot] = charges
        t0 = self.charge_t0.get(slot, now)
        ready_at = t0 + max(0, int(charge_cd_ms))
        remaining = max(0, ready_at - now)
        self.states[slot] = "charging"
        self.ready_at[slot] = ready_at
        return ready_at, remaining, transition

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
    use_band: bool = False,
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
    from core.hud_band import bright_pixel_count, charge_remaining_ms, measure_band_ratio
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
        charge_cd = int(meta.effective_charge_cd_ms) if meta is not None else 0
        seconds = parse_duration_ms(row_texts)
        pct = parse_percent(row_texts) if index == 0 else None
        charge = parse_charge(texts)
        charges = 0
        band_ratio_value = 0.0
        text_reason = ""
        if index == 0:
            if seconds is not None:
                remaining = max(0, int(seconds))
                state = "ready" if remaining <= 0 else "charging"
                ready_at = int(server_now) if state == "ready" else int(server_now) + remaining
                transition = "text-ready" if state == "ready" else "text-seconds"
                tracker.states[0] = state
                tracker.ready_at[0] = 0 if state == "ready" else ready_at
                text_reason = "文字0秒→就绪" if state == "ready" else "文字秒数"
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
                raw_state = "ready" if p90 >= threshold else "charging"
                ready_at, remaining, state, event = tracker.observe_brightness(
                    0, raw_state, total_cd, server_now, debounce=2
                )
                transition = event or ("brightness-steady" if state == "charging" else "brightness-ready")
                text_reason = "亮度事件(去抖)" if event else "亮度保持"
            charges = 1 if state != "unknown" else 0
        elif charge is not None:
            charges, ready_at, remaining, state, event = tracker.observe_charge(
                index,
                charge,
                max_charges,
                charge_cd,
                total_cd,
                server_now,
                debounce=2,
                text_remaining_ms=seconds,
            )
            transition = event or "charge-steady"
            if seconds is not None:
                text_reason = "0充能文字重同步" if charges == 0 else "文字秒数"
            elif event == "cast":
                text_reason = "充能减少→释放事件"
            elif event == "recover":
                text_reason = "充能恢复→就绪"
            else:
                text_reason = "充能数保持/估算"
        elif seconds is not None:
            charges = tracker.charges.get(index, 0)
            remaining = max(0, int(seconds))
            state = "ready" if remaining <= 0 else "charging"
            ready_at = int(server_now) if state == "ready" else int(server_now) + remaining
            transition = "text-ready" if state == "ready" else "text-seconds"
            tracker.states[index] = state
            tracker.ready_at[index] = 0 if state == "ready" else ready_at
            text_reason = "文字0秒→就绪" if state == "ready" else "文字秒数（charge未知）"
        else:
            raw_state = "ready" if p90 >= threshold else "charging"
            ready_at, remaining, state, event = tracker.observe_brightness(
                index, raw_state, total_cd, server_now, debounce=2
            )
            transition = event or ("brightness-steady" if state == "charging" else "brightness-ready")
            text_reason = "亮度事件(去抖)" if event else "亮度保持"
            charges = 1 if state != "unknown" else 0
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
                ready_at_source=(
                    "text" if seconds is not None
                    else ("pct" if pct is not None else ("estimate" if transition in ("cast", "charge-decrease", "charge-init") else "state"))
                ),
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
