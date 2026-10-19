"""E3b2：RapidOCR/OpenCV 适配（惰性导入，识别失败返回空）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.hud_profile import HudProfile, Roi


@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float
    box: tuple[tuple[int, int], ...] = ()


class HudOcr:
    """封装 RapidOCR；首次识别时才导入/加载模型，避免拖慢启动。"""

    def __init__(self) -> None:
        self._engine = None

    def available(self) -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401

            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]

            self._engine = RapidOCR()
        return self._engine

    def read_lines(self, image: Any) -> list[OcrLine]:
        if image is None:
            return []
        try:
            result, _ = self._ensure()(image)
        except Exception:  # noqa: BLE001
            return []
        lines: list[OcrLine] = []
        for item in result or []:
            try:
                text = str(item[1])
                score = float(item[2])
                box = tuple((int(point[0]), int(point[1])) for point in item[0])
                lines.append(OcrLine(text=text, score=score, box=box))
            except Exception:  # noqa: BLE001
                continue
        return lines


def crop(image: Any, roi: Roi) -> Any:
    if image is None:
        return None
    try:
        return image[roi.y : roi.bottom, roi.x : roi.right]
    except Exception:  # noqa: BLE001
        return None


def read_roi_texts(ocr: HudOcr, image: Any, roi: Roi, min_score: float = 0.4) -> list[str]:
    lines = ocr.read_lines(crop(image, roi))
    return [line.text for line in lines if line.score >= min_score]


def read_skill_bar_texts(ocr: HudOcr, image: Any, profile: HudProfile) -> list[list[str]]:
    """按 3 个槽位 ROI 分别 OCR；每个槽返回原始文本列表。"""
    return [read_roi_texts(ocr, image, roi, profile.ocr_threshold) for roi in profile.slot_rois()]


def read_all_texts(ocr: HudOcr, image: Any, profile: HudProfile) -> list[str]:
    return read_roi_texts(ocr, image, profile.skill_bar, profile.ocr_threshold)


def import_cv2():
    try:
        import cv2  # type: ignore[import-not-found]

        return cv2
    except Exception:  # noqa: BLE001
        return None
