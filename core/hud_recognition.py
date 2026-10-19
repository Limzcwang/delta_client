"""E3b：HUD 识别纯逻辑（百分比/秒数/充能/遮罩比例/槽位结果）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SKILL_CHARGING, SKILL_READY, SKILL_UNKNOWN

_PERCENT_RE = re.compile(r"(\d{1,3})\s*%")
_SECONDS_RE = re.compile(r"(\d{1,4})\s*(?:秒|s|S)")
_INT_RE = re.compile(r"^\s*(\d{1,3})\s*$")


def parse_percent(texts: Iterable[str]) -> int | None:
    """从 OCR 文本中取百分比（0–100）；多个候选取最靠右/最后的数字。"""
    values: list[int] = []
    for text in texts:
        for match in _PERCENT_RE.finditer(str(text)):
            value = int(match.group(1))
            if 0 <= value <= 100:
                values.append(value)
    return values[-1] if values else None


def parse_seconds(texts: Iterable[str]) -> int | None:
    """读取「15秒/15s」；返回毫秒。"""
    values: list[int] = []
    for text in texts:
        for match in _SECONDS_RE.finditer(str(text)):
            value = int(match.group(1))
            if 0 < value <= 3600:
                values.append(value)
    return values[-1] * 1000 if values else None


def parse_duration_ms(texts: Iterable[str]) -> int | None:
    """解析 NN秒、N分M秒、N分、M:SS；返回毫秒。"""
    for text in texts:
        value = str(text)
        match = re.search(r"(\d{1,2})\s*分\s*(\d{1,2})\s*秒", value)
        if match:
            return (int(match.group(1)) * 60 + int(match.group(2))) * 1000
        match = re.search(r"(\d{1,2})\s*分", value)
        if match:
            return int(match.group(1)) * 60 * 1000
        match = re.search(r"(\d{1,4})\s*秒", value)
        if match:
            return int(match.group(1)) * 1000
        match = re.search(r"(\d{1,2}):(\d{2})", value)
        if match:
            return (int(match.group(1)) * 60 + int(match.group(2))) * 1000
    return None


def parse_charge(texts: Iterable[str]) -> int | None:
    """读取单独的小数字充能数（如 ``2``）；忽略百分比/秒数文本。"""
    values: list[int] = []
    for text in texts:
        cleaned = str(text).strip()
        if "%" in cleaned or "秒" in cleaned or cleaned.lower().endswith("s"):
            continue
        match = _INT_RE.match(cleaned)
        if match:
            values.append(int(match.group(1)))
    return values[-1] if values else None


def mask_ratio(image: Any, dark_threshold: int = 70, x: int = 0, y: int = 0, width: int = 0, height: int = 0) -> float:
    """图标矩形内暗色遮罩面积占比（0–1）；接受 numpy 数组/二维序列。"""
    if image is None:
        return 0.0
    try:
        rows = len(image)
        cols = len(image[0]) if rows else 0
    except TypeError:
        return 0.0
    if rows <= 0 or cols <= 0:
        return 0.0
    x0 = max(0, min(int(x), cols - 1))
    y0 = max(0, min(int(y), rows - 1))
    x1 = max(x0 + 1, min(cols, x0 + width if width else cols))
    y1 = max(y0 + 1, min(rows, y0 + height if height else rows))
    dark = 0
    total = 0
    for row in range(y0, y1):
        line = image[row]
        for col in range(x0, x1):
            pixel = line[col]
            try:
                if hasattr(pixel, "__len__") and len(pixel) >= 3:
                    value = (
                        0.299 * float(pixel[0])
                        + 0.587 * float(pixel[1])
                        + 0.114 * float(pixel[2])
                    )
                else:
                    value = float(pixel)
            except (TypeError, ValueError):
                continue
            total += 1
            if value < dark_threshold:
                dark += 1
    return dark / total if total else 0.0


def charged_remaining_ms(percent: int, total_cd_ms: int, meaning: str = "charged") -> int:
    """percent=已充能：remaining=(100-pct)/100*CD；兼容 remaining 语义。"""
    total = max(0, int(total_cd_ms))
    if meaning == "remaining":
        remaining_pct = percent
    else:
        remaining_pct = 100 - percent
    return max(0, int(round(total * remaining_pct / 100.0)))


@dataclass(frozen=True)
class SlotRecognition:
    slot: int
    state: str = SKILL_UNKNOWN
    remaining_ms: int = 0
    ready_at: int = 0
    percent: float = 0.0
    charges: int = 0
    max_charges: int = 0
    source: str = ""
    raw_texts: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        item: dict[str, Any] = {"slot": self.slot, "state": self.state}
        if self.ready_at > 0:
            item["ready_at"] = int(self.ready_at)
        if self.state != SKILL_UNKNOWN:
            if self.remaining_ms:
                item["remaining_ms"] = int(self.remaining_ms)
            if self.slot == 0:
                item["pct"] = float(self.percent)
            if self.max_charges:
                item["charges"] = int(self.charges)
                item["max_charges"] = int(self.max_charges)
        return item


def recognize_ultimate(
    texts: Sequence[str],
    total_cd_ms: int,
    *,
    meaning: str = "charged",
) -> SlotRecognition:
    pct = parse_percent(texts)
    if pct is None:
        return SlotRecognition(SLOT_ULTIMATE, SKILL_UNKNOWN, raw_texts=tuple(texts))
    if pct >= 100:
        return SlotRecognition(SLOT_ULTIMATE, SKILL_READY, percent=100.0, raw_texts=tuple(texts))
    return SlotRecognition(
        SLOT_ULTIMATE,
        SKILL_CHARGING,
        remaining_ms=charged_remaining_ms(pct, total_cd_ms, meaning),
        percent=float(pct),
        source="ocr_percent",
        raw_texts=tuple(texts),
    )


def recognize_secondary(
    slot: int,
    texts: Sequence[str],
    total_cd_ms: int,
    max_charges: int,
    *,
    ratio: float = 0.0,
) -> SlotRecognition:
    seconds_ms = parse_seconds(texts)
    charge = parse_charge(texts)
    if seconds_ms is not None:
        return SlotRecognition(
            slot,
            SKILL_CHARGING if seconds_ms > 0 else SKILL_READY,
            remaining_ms=seconds_ms,
            charges=charge or 0,
            max_charges=max_charges,
            source="ocr_seconds",
            raw_texts=tuple(texts),
        )
    if charge is not None:
        if max_charges and charge >= max_charges:
            return SlotRecognition(slot, SKILL_READY, charges=charge, max_charges=max_charges, raw_texts=tuple(texts))
        if total_cd_ms > 0 and ratio > 0:
            return SlotRecognition(
                slot,
                SKILL_CHARGING,
                remaining_ms=max(0, int(round(ratio * total_cd_ms))),
                charges=charge,
                max_charges=max_charges,
                source="mask_ratio",
                raw_texts=tuple(texts),
            )
        # 只有充能数、没有秒数/遮罩比例：不猜剩余时间，交给 unknown
        return SlotRecognition(slot, SKILL_UNKNOWN, raw_texts=tuple(texts))
    if total_cd_ms > 0 and ratio > 0:
        return SlotRecognition(
            slot,
            SKILL_CHARGING,
            remaining_ms=max(0, int(round(ratio * total_cd_ms))),
            max_charges=max_charges,
            source="mask_ratio",
            raw_texts=tuple(texts),
        )
    return SlotRecognition(slot, SKILL_UNKNOWN, raw_texts=tuple(texts))
