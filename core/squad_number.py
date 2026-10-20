"""HUD 自己头像左上角队伍编号 OCR：只接受 1/2/3。"""

from __future__ import annotations

import re
from typing import Any, Iterable

from core.hud_ocr import HudOcr, crop
from core.hud_profile import HudProfile, Roi

SQUAD_NUMBERS = (1, 2, 3)
_PATTERN = re.compile(r"^[1-3]$")


def number_roi(profile: HudProfile) -> Roi:
    roi = profile.self_avatar_roi
    return Roi(roi.x, roi.y, max(1, roi.width // 3), max(1, roi.height // 3))


def crop_self_avatar_number(frame: Any, profile: HudProfile) -> Any:
    return crop(frame, number_roi(profile))


def upscale(image: Any, factor: int = 4) -> Any:
    """4× 最近邻放大，优先 cv2；无 cv2 时用 numpy。"""
    if image is None:
        return None
    try:
        import cv2  # type: ignore[import-not-found]

        return cv2.resize(
            image,
            (max(1, image.shape[1] * factor), max(1, image.shape[0] * factor)),
            interpolation=cv2.INTER_CUBIC,
        )
    except Exception:  # noqa: BLE001
        try:
            import numpy as np

            return np.repeat(np.repeat(image, factor, axis=0), factor, axis=1)
        except Exception:  # noqa: BLE001
            return image


def parse_squad_number(texts: Iterable[str]) -> int | None:
    """只接受完整单字符 1/2/3；0/4-9/多位数均视为失败。"""
    for raw in texts:
        text = str(raw or "").strip()
        if _PATTERN.fullmatch(text):
            return int(text)
    return None


def recognize_squad_number(ocr: HudOcr | Any, frame: Any, profile: HudProfile) -> int | None:
    crop_image = crop_self_avatar_number(frame, profile)
    if crop_image is None:
        return None
    scaled = upscale(crop_image, 4)
    try:
        lines = ocr.read_lines(scaled)
    except Exception:  # noqa: BLE001
        return None
    return parse_squad_number(getattr(line, "text", "") for line in lines)
