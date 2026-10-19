"""E3b2：干员头像模板匹配（灰度 + 多尺度 TM_CCOEFF_NORMED，遮掉位置编号）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.hud_profile import Roi
from core.operators import OperatorCatalog

DEFAULT_THRESHOLD = 0.70
SCALES = (0.90, 0.95, 1.00, 1.05, 1.10)


def mask_position_number(image: Any, width: int = 20, height: int = 24) -> Any:
    """模板/目标左上角位置编号填黑，减少 1/2/3 干扰。"""
    if image is None:
        return image
    try:
        image[0:height, 0:width] = 0
    except Exception:  # noqa: BLE001
        pass
    return image


def match_operator_template(
    frame: Any,
    avatar_roi: Roi,
    templates: dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[str, float]:
    """在头像 ROI 内对每个模板做灰度多尺度匹配；返回 (operator_id, score)。"""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return "", 0.0
    if frame is None or not templates:
        return "", 0.0
    try:
        target = frame[avatar_roi.y : avatar_roi.bottom, avatar_roi.x : avatar_roi.right]
    except Exception:  # noqa: BLE001
        return "", 0.0
    if target is None or target.size == 0:
        return "", 0.0
    target_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
    best_id, best_score = "", 0.0
    for operator_id, template in templates.items():
        if template is None or template.size == 0:
            continue
        tpl = mask_position_number(template.copy())
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        for scale in SCALES:
            h = max(1, int(tpl_gray.shape[0] * scale))
            w = max(1, int(tpl_gray.shape[1] * scale))
            if h > target_gray.shape[0] or w > target_gray.shape[1]:
                continue
            resized = cv2.resize(tpl_gray, (w, h))
            result = cv2.matchTemplate(target_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            if score > best_score:
                best_id, best_score = operator_id, float(score)
    return (best_id, best_score) if best_score >= threshold else ("", best_score)


def load_templates(catalog: OperatorCatalog) -> dict[str, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return {}
    templates: dict[str, Any] = {}
    for operator in catalog:
        path = Path(operator.avatar_path())
        if not path.is_file():
            continue
        image = cv2.imread(str(path))
        if image is not None:
            templates[operator.id] = image
    return templates


def recognize_operator(
    frame: Any,
    avatar_roi: Roi,
    catalog: OperatorCatalog,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[str, float]:
    return match_operator_template(frame, avatar_roi, load_templates(catalog), threshold)
