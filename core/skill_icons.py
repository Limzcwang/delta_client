"""技能图标模板匹配（图标优先识别）。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.hud_profile import Roi

logger = logging.getLogger(__name__)
DEFAULT_ICON_THRESHOLD = 0.70
ICON_SCALES = (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15)
CHARGE_MASK_SIZE = 28


def mask_charge_corner(image: Any, size: int = CHARGE_MASK_SIZE) -> Any:
    """右上角充能数字填 0；模板和目标一致，避免数字变化掉分。"""
    if image is None:
        return image
    try:
        array = image.copy()
        height, width = array.shape[:2]
        mask_h = min(int(size), height)
        mask_w = min(int(size), width)
        array[0:mask_h, width - mask_w : width] = 0
        return array
    except Exception:  # noqa: BLE001
        return image


def skill_icon_dir() -> Path:
    import os
    import sys

    override = str(os.environ.get("DELTA_SKILL_ICONS_DIR", "") or "").strip()
    if override:
        return Path(override).expanduser()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "assets" / "operators" / "skills"


def skill_icon_path(operator_id: str, slot: int) -> Path:
    return skill_icon_dir() / f"{operator_id}_{int(slot)}.png"


def load_skill_icon_templates(operator_id: str, directory: str | Path | None = None) -> dict[int, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return {}
    base = Path(directory) if directory is not None else skill_icon_dir()
    templates: dict[int, Any] = {}
    for slot in range(3):
        path = base / f"{operator_id}_{slot}.png"
        if not path.is_file():
            continue
        try:
            image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception:  # noqa: BLE001
            image = None
        if image is not None:
            templates[slot] = image
    return templates


def match_icon_score(frame: Any, roi: Roi, template: Any, threshold: float = DEFAULT_ICON_THRESHOLD) -> tuple[float, bool]:
    """在槽 ROI 内对指定图标模板做灰度多尺度匹配。"""
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return 0.0, False
    if frame is None or template is None:
        return 0.0, False
    try:
        target = frame[roi.y : roi.bottom, roi.x : roi.right]
        if target is None or getattr(target, "size", 0) == 0:
            return 0.0, False
        target_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY) if target.ndim == 3 else target
        target_gray = mask_charge_corner(target_gray)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template
        template_gray = mask_charge_corner(template_gray)
        best = 0.0
        for scale in ICON_SCALES:
            h = max(1, int(template_gray.shape[0] * scale))
            w = max(1, int(template_gray.shape[1] * scale))
            if h > target_gray.shape[0] or w > target_gray.shape[1]:
                continue
            resized = cv2.resize(template_gray, (w, h))
            result = cv2.matchTemplate(target_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            best = max(best, float(score))
        return best, best >= float(threshold)
    except Exception as exc:  # noqa: BLE001
        logger.debug("技能图标匹配失败：%s", exc)
        return 0.0, False
