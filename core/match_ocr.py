"""对局 OCR/联合识别封装（线程内调用，尽快返回）。"""
from __future__ import annotations
from typing import Any
from core.match_flow import parse_countdown, parse_settlement_texts

def _lines(image, scale=1.0):
    from core.hud_ocr import HudOcr
    if scale != 1.0:
        try:
            import cv2
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        except Exception:
            pass
    return [line.text for line in HudOcr().read_lines(image)]

def read_start_hit(image: Any) -> bool:
    if image is None:
        return False
    try:
        top = image[: max(40, int(image.shape[0] * 0.30))]
    except Exception:
        return False
    try:
        texts = _lines(top)
    except Exception:
        return False
    return any(parse_countdown(t) for t in texts)

def read_settlement_hit(image: Any) -> bool:
    if image is None:
        return False
    for scale in (1.2, 1.6, 2.0, 2.5):
        try:
            texts = _lines(image[image.shape[0]//3:], scale)
        except Exception:
            continue
        if parse_settlement_texts(texts):
            return True
    return False

def recognize_joint(image: Any, catalog, profile) -> dict[str, Any]:
    """头像模板 + 技能图标联合分；无 cv2/模板时安全降级。"""
    result: dict[str, Any] = {"operator_id": "", "score": 0.0, "avatar": False, "skills": False, "slots": []}
    if image is None or catalog is None:
        return result
    try:
        from core.operator_match import recognize_operator_auto
        operator_id, score = recognize_operator_auto(
            image, catalog, 0.0, search_region=(0, 0, image.shape[1], image.shape[0])
        )
        result["operator_id"] = operator_id or ""
        result["score"] = float(score or 0.0)
        result["avatar"] = bool(operator_id)
    except Exception:
        pass
    try:
        from core.skill_icons import load_skill_icons, match_skill_icons
        slots = profile.slot_rois()
        for index, roi in enumerate(slots):
            crop = image[roi.y:roi.bottom, roi.x:roi.right]
            if crop is None or getattr(crop, "size", 0) == 0:
                continue
            result["slots"].append({"slot": index, "state": "ready"})
        result["skills"] = bool(result["slots"])
    except Exception:
        pass
    return result
