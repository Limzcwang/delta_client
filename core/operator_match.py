"""E3b2：干员头像模板匹配（灰度 + 多尺度 TM_CCOEFF_NORMED，遮掉位置编号）。"""

from __future__ import annotations

import math
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


def _green_number_mask(image: Any, width: int = 24, height: int = 28) -> Any:
    """头像左上角 24×28 内的绿色数字掩码（BGR）。"""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    if image is None or getattr(image, "size", 0) == 0:
        return None
    region = image[0:height, 0:width]
    if region.ndim != 3:
        return None
    b = region[:, :, 0].astype(np.int16)
    g = region[:, :, 1].astype(np.int16)
    r = region[:, :, 2].astype(np.int16)
    mask = ((g - r) > 25) & ((g - b) > 15) & (g > 70)
    if not mask.any():
        return None
    out = np.zeros(region.shape[:2], dtype=np.uint8)
    out[mask] = 255
    return out


def _clean_green_number(image: Any, *, inpaint: bool = True) -> Any:
    """只清理左上角检测到的绿色编号；检测不到时原样返回，避免乱改画面。"""
    mask = _green_number_mask(image)
    if mask is None:
        return image
    try:
        import cv2  # type: ignore[import-not-found]

        if inpaint:
            cleaned = image.copy()
            cleaned[0 : mask.shape[0], 0 : mask.shape[1]] = cv2.inpaint(
                image[0 : mask.shape[0], 0 : mask.shape[1]], mask, 3, cv2.INPAINT_TELEA
            )
            return cleaned
        image[0 : mask.shape[0], 0 : mask.shape[1]][mask > 0] = 0
        return image
    except Exception:  # noqa: BLE001
        return image


def _template_mask(template_gray: Any, scale: float = 1.0) -> Any:
    try:
        import numpy as np  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    h, w = template_gray.shape[:2]
    mask = np.ones((h, w), dtype=np.uint8) * 255
    mask[0 : min(h, max(1, int(24 * scale))), 0 : min(w, max(1, int(20 * scale)))] = 0
    return mask


def _prepare_number_region(image: Any) -> Any:
    """无绿色编号时与模板一致填黑；有编号时用 inpaint 清理。"""
    if image is None:
        return image
    mask = _green_number_mask(image)
    if mask is None:
        return mask_position_number(image.copy())
    # 先 inpaint 去掉数字，再把模板对应的左上区域统一填黑，保证和干净模板一致。
    cleaned = _clean_green_number(image.copy(), inpaint=True)
    return mask_position_number(cleaned)


def _score_patch(patch: Any, template_gray: Any, mask: Any = None) -> float:
    try:
        import cv2  # type: ignore[import-not-found]

        if patch is None or patch.size == 0 or template_gray is None:
            return 0.0
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if patch.ndim == 3 else patch
        if gray.shape[0] < template_gray.shape[0] or gray.shape[1] < template_gray.shape[1]:
            return 0.0
        result = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED, mask=mask)
        _, score, _, _ = cv2.minMaxLoc(result)
        score = float(score)
        return score if math.isfinite(score) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


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
    target = _prepare_number_region(target)
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
            score = float(score)
            if not math.isfinite(score):  # NaN/Inf：模板/窗口无方差
                score = 0.0
            current = best_by_operator.get(operator_id)
            if current is None or score > current["score"]:
                best_by_operator[operator_id] = {
                    "operator_id": operator_id,
                    "score": float(score),
                    "box": (x + int(location[0]), y + int(location[1]), tw, th),
                    "scale": scale,
                }
    # 精匹配：在候选 box ±6px 内，清理绿色编号后重算；再与「双填黑」回退取较高分。
    for candidate in best_by_operator.values():
        operator_id = candidate["operator_id"]
        template = templates.get(operator_id)
        if template is None or getattr(template, "size", 0) == 0:
            continue
        tpl = mask_position_number(template.copy())
        tpl_gray = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY) if tpl.ndim == 3 else tpl
        scale = float(candidate.get("scale", 1.0))
        th = max(1, int(tpl_gray.shape[0] * scale))
        tw = max(1, int(tpl_gray.shape[1] * scale))
        resized = cv2.resize(tpl_gray, (tw, th))
        bx, by = int(candidate["box"][0]), int(candidate["box"][1])
        best_score = float(candidate["score"])
        best_box = (bx, by, tw, th)
        pad = 6
        x0, y0 = max(0, bx - pad), max(0, by - pad)
        x1, y1 = min(width, bx + tw + pad), min(height, by + th + pad)
        region = frame[y0:y1, x0:x1]
        if region.size:
            for inpaint in (True, False):
                processed = _prepare_number_region(region) if inpaint else _clean_green_number(region.copy(), inpaint=False)
                gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY) if processed.ndim == 3 else processed
                if gray.shape[0] < th or gray.shape[1] < tw:
                    continue
                result = cv2.matchTemplate(
                    gray, resized, cv2.TM_CCOEFF_NORMED, mask=_template_mask(resized, scale)
                )
                _, score, _, location = cv2.minMaxLoc(result)
                score = float(score) if math.isfinite(float(score)) else 0.0
                if score > best_score:
                    best_score = score
                    best_box = (x0 + int(location[0]), y0 + int(location[1]), tw, th)
        candidate["score"] = best_score
        candidate["box"] = best_box

    top3 = sorted(best_by_operator.values(), key=lambda item: item["score"], reverse=True)[:3]
    if not top3 or top3[0]["score"] < threshold:
        return "", float(top3[0]["score"] if top3 else 0.0), None, top3
    best = top3[0]
    return best["operator_id"], best["score"], best["box"], top3
