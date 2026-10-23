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

def read_start_details(image: Any) -> dict[str, Any]:
    detail = {"hit": False, "lines": [], "hits": 0, "attempts": 0, "threshold": 0, "result": "miss"}
    if image is None:
        detail["result"] = "no_frame"
        return detail
    try:
        top = image[: max(40, int(image.shape[0] * 0.30))]
        texts = _lines(top)
    except Exception:
        detail["result"] = "ocr_error"
        return detail
    detail["lines"] = [{"text": str(t), "box": []} for t in texts]
    detail["attempts"] = 1
    detail["threshold"] = 1
    hits = sum(1 for text in texts if parse_countdown(text))
    detail["hits"] = hits
    detail["hit"] = bool(hits)
    detail["result"] = "hit" if hits else "miss"
    return detail

def read_start_hit(image: Any) -> bool:
    return bool(read_start_details(image)["hit"])

def read_settlement_details(image: Any) -> dict[str, Any]:
    detail = {"hit": False, "scans": 0, "hits": 0, "threshold": 1, "result": "miss", "lines": []}
    if image is None:
        detail["result"] = "no_frame"
        return detail
    for scale in (1.2, 1.6, 2.0, 2.5):
        detail["scans"] += 1
        try:
            texts = _lines(image[image.shape[0]//3:], scale)
        except Exception:
            continue
        detail["lines"] = [{"text": str(t), "box": []} for t in texts]
        if parse_settlement_texts(texts):
            detail["hit"] = True; detail["hits"] += 1; detail["result"] = "hit"; break
    return detail

def read_settlement_hit(image: Any) -> bool:
    return bool(read_settlement_details(image)["hit"])

def recognize_joint(image: Any, catalog, profile) -> dict[str, Any]:
    """头像模板 + 技能图标联合分；无 cv2/模板时安全降级。"""
    result: dict[str, Any] = {"operator_id": "", "score": 0.0, "avatar": False, "skills": False,
                              "slots": [], "top3": [], "skill_bar": {"found": False, "roi": {}}}
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
        if operator_id:
            result["top3"] = [{"id": str(operator_id), "score": float(score or 0.0)}]
    except Exception:
        pass
    try:
        from core.skill_icons import load_skill_icons, match_skill_icons
        slots = profile.slot_rois()
        result["skill_bar"] = {"found": True, "roi": profile.skill_bar.to_dict()}
        for index, roi in enumerate(slots):
            crop = image[roi.y:roi.bottom, roi.x:roi.right]
            if crop is None or getattr(crop, "size", 0) == 0:
                continue
            result["slots"].append({"slot": index, "state": "ready", "charges": 0, "max_charges": 1, "pct": None})
        result["skills"] = bool(result["slots"])
    except Exception:
        pass
    return result
