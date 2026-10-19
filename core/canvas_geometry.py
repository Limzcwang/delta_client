"""H4：画板底图 letterbox 与归一化坐标换算（纯逻辑，便于单测）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FitRect:
    """图片在视口中的等比显示区域（letterbox 后）。"""

    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


def fit_rect(
    viewport_width: float, viewport_height: float, image_width: float, image_height: float
) -> FitRect:
    """等比缩放并居中（letterbox）：完整显示图片、保持宽高比、不裁切/不拉伸。"""
    viewport_width = max(0.0, float(viewport_width))
    viewport_height = max(0.0, float(viewport_height))
    image_width = max(0.0, float(image_width))
    image_height = max(0.0, float(image_height))
    if viewport_width <= 0 or viewport_height <= 0 or image_width <= 0 or image_height <= 0:
        return FitRect(0.0, 0.0, 0.0, 0.0)
    scale = min(viewport_width / image_width, viewport_height / image_height)
    width = image_width * scale
    height = image_height * scale
    left = (viewport_width - width) / 2.0
    top = (viewport_height - height) / 2.0
    return FitRect(left, top, width, height)


def widget_to_normalized(
    x: float, y: float, rect: FitRect
) -> tuple[float, float] | None:
    """视口像素 -> 0–1（以图片区域为基准）；图片区域外返回 None。"""
    if rect.width <= 0 or rect.height <= 0:
        return None
    if not rect.contains(float(x), float(y)):
        return None
    nx = (float(x) - rect.left) / rect.width
    ny = (float(y) - rect.top) / rect.height
    return (min(max(nx, 0.0), 1.0), min(max(ny, 0.0), 1.0))


def normalized_to_widget(x: float, y: float, rect: FitRect) -> tuple[float, float]:
    """0–1（以图片区域为基准）-> 视口像素；越界 clamp。"""
    nx = min(max(float(x), 0.0), 1.0)
    ny = min(max(float(y), 0.0), 1.0)
    return (rect.left + nx * rect.width, rect.top + ny * rect.height)
