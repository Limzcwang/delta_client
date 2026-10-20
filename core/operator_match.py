"""E3b2：干员头像模板匹配（灰度 + 多尺度 TM_CCOEFF_NORMED，遮掉位置编号）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.hud_profile import Roi
from core.operators import OperatorCatalog

DEFAULT_THRESHOLD = 0.70
AUTO_THRESHOLD = 0.65
DEFAULT_AVATAR_SEARCH = (0, 1200, 260, 240)
AUTO_SCALES = tuple(round(0.5 + 0.05 * index, 2) for index in range(27))  # 0.50..1.80
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


def recognize_operator_auto(
    frame: Any,
    catalog: OperatorCatalog,
    threshold: float = AUTO_THRESHOLD,
    search_region: tuple[int, int, int, int] = DEFAULT_AVATAR_SEARCH,
    templates: dict[str, Any] | None = None,
) -> tuple[str, float, dict[str, Any] | None, list[dict[str, Any]]]:
    """在左下角区域滑窗扫描 17 个头像模板；返回 id/score/box/top3。"""
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return "", 0.0, None, []
    if frame is None:
        return "", 0.0, None, []
    templates = templates if templates is not None else load_templates(catalog)
    if not templates:
        return "", 0.0, None, []
    try:
        height, width = int(frame.shape[0]), int(frame.shape[1])
        x, y, w, h = (int(v) for v in search_region)
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))
        target = frame[y : y + h, x : x + w]
        target_gray = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY) if target.ndim == 3 else target
    except Exception:  # noqa: BLE001
        return "", 0.0, None, []
    best_by_operator: dict[str, dict[str, Any]] = {}
    for operator_id, template in templates.items():
        if template is None or getattr(template, "size", 0) == 0:
            continue
        try:
            tpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template
        except Exception:  # noqa: BLE001
            continue
        for scale in AUTO_SCALES:
            th = max(1, int(tpl_gray.shape[0] * scale))
            tw = max(1, int(tpl_gray.shape[1] * scale))
            if th > target_gray.shape[0] or tw > target_gray.shape[1]:
                continue
            resized = cv2.resize(tpl_gray, (tw, th))
            result = cv2.matchTemplate(target_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, score, _, location = cv2.minMaxLoc(result)
            current = best_by_operator.get(operator_id)
            if current is None or score > current["score"]:
                best_by_operator[operator_id] = {
                    "operator_id": operator_id,
                    "score": float(score),
                    "box": (x + int(location[0]), y + int(location[1]), tw, th),
                    "scale": scale,
                }
    top3 = sorted(best_by_operator.values(), key=lambda item: item["score"], reverse=True)[:3]
    if not top3 or top3[0]["score"] < threshold:
        return "", float(top3[0]["score"] if top3 else 0.0), None, top3
    best = top3[0]
    return best["operator_id"], best["score"], best["box"], top3
