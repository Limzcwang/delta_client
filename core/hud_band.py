"""充能技能灰带比例：当前槽位 vs 就绪模板的暗化面积。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BandStats:
    area_ratio: float
    row_ratio: float = 0.0
    column_ratio: float = 0.0
    direction: str = "area"


def measure_band_ratio(current: Any, ready_template: Any, dark_delta: int = 20) -> BandStats | None:
    """返回灰带面积占比及行/列投影占比；模板不可用时 None。"""
    if current is None or ready_template is None:
        return None
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]

        target = current
        template = ready_template
        if not hasattr(target, "shape"):
            target = np.asarray(target)
        if not hasattr(template, "shape"):
            template = np.asarray(template)
        if target.size == 0 or template.size == 0:
            return None
        if target.ndim == 3:
            target = cv2.cvtColor(target, cv2.COLOR_BGR2GRAY)
        if template.ndim == 3:
            template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        if target.shape != template.shape:
            template = cv2.resize(template, (target.shape[1], target.shape[0]))
        diff = template.astype(float) - target.astype(float)
        mask = diff > float(dark_delta)
        total = int(mask.size)
        if total <= 0:
            return BandStats(0.0)
        area = float(mask.sum()) / total
        rows = float(mask.any(axis=1).sum()) / max(1, mask.shape[0])
        cols = float(mask.any(axis=0).sum()) / max(1, mask.shape[1])
        return BandStats(area_ratio=area, row_ratio=rows, column_ratio=cols)
    except Exception:  # noqa: BLE001
        return None


def charge_remaining_ms(band: BandStats | None, total_cd_ms: int, max_charges: int, fallback_ratio: float = 0.0) -> int:
    """f=0 刚开始恢复，f=1 恢复完成；remaining=(1-f)*单次充能 CD。"""
    charges = max(1, int(max_charges))
    charge_cd = max(0, int(total_cd_ms)) / charges
    ratio = band.area_ratio if band is not None else float(fallback_ratio)
    ratio = max(0.0, min(1.0, ratio))
    return int(round((1.0 - ratio) * charge_cd))
