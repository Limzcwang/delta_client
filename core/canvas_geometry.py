"""H4/H5：画板底图宽高比适配与画布内 0–1 坐标换算（纯逻辑）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AspectSize:
    """画布控件在可用空间内的等比尺寸（画布宽高比 = 底图宽高比）。"""

    width: float
    height: float


def fit_aspect_size(
    available_width: float,
    available_height: float,
    image_width: float,
    image_height: float,
) -> AspectSize:
    """按 ``min(可用宽/图宽, 可用高/图高)`` 等比缩放，返回画布控件尺寸。

    画布控件本身就是图片比例，内部不再做 letterbox/cover；宿主剩余空间留白。
    """
    available_width = max(0.0, float(available_width))
    available_height = max(0.0, float(available_height))
    image_width = max(0.0, float(image_width))
    image_height = max(0.0, float(image_height))
    if available_width <= 0 or available_height <= 0 or image_width <= 0 or image_height <= 0:
        return AspectSize(0.0, 0.0)
    scale = min(available_width / image_width, available_height / image_height)
    return AspectSize(image_width * scale, image_height * scale)


def canvas_to_normalized(
    x: float, y: float, canvas_width: float, canvas_height: float
) -> tuple[float, float] | None:
    """画布控件像素 -> 0–1；控件外返回 None（图外不绘制）。"""
    canvas_width = float(canvas_width)
    canvas_height = float(canvas_height)
    if canvas_width <= 0 or canvas_height <= 0:
        return None
    if not (0.0 <= float(x) <= canvas_width and 0.0 <= float(y) <= canvas_height):
        return None
    return (
        min(max(float(x) / canvas_width, 0.0), 1.0),
        min(max(float(y) / canvas_height, 0.0), 1.0),
    )


def normalized_to_canvas(
    x: float, y: float, canvas_width: float, canvas_height: float
) -> tuple[float, float]:
    """0–1 -> 画布控件像素；越界 clamp。"""
    nx = min(max(float(x), 0.0), 1.0)
    ny = min(max(float(y), 0.0), 1.0)
    return (nx * float(canvas_width), ny * float(canvas_height))
