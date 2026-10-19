"""H5 画板随底图比例 / 画布内 0–1 坐标换算（纯逻辑）。"""

from __future__ import annotations

import unittest

from core.canvas_geometry import (
    AspectSize,
    canvas_to_normalized,
    fit_aspect_size,
    normalized_to_canvas,
)


class AspectSizeTests(unittest.TestCase):
    def test_landscape_and_portrait_views(self) -> None:
        # 1105×1260 底图在 1000×1000 可用区：以高为准
        size = fit_aspect_size(1000, 1000, 1105, 1260)
        self.assertAlmostEqual(1000.0, size.height)
        self.assertAlmostEqual(1000 * 1105 / 1260, size.width)
        self.assertAlmostEqual(1105 / 1260, size.width / size.height, places=6)

        # 宽屏：以高为准
        wide = fit_aspect_size(2000, 500, 1105, 1260)
        self.assertAlmostEqual(500.0, wide.height)
        self.assertAlmostEqual(500 * 1105 / 1260, wide.width)

        # 竖屏：以宽为准
        tall = fit_aspect_size(500, 2000, 1105, 1260)
        self.assertAlmostEqual(500.0, tall.width)
        self.assertAlmostEqual(500 * 1260 / 1105, tall.height)

    def test_same_ratio_uses_exact_space(self) -> None:
        size = fit_aspect_size(1105, 1260, 1105, 1260)
        self.assertEqual(AspectSize(1105.0, 1260.0), size)
        half = fit_aspect_size(552.5, 630, 1105, 1260)
        self.assertEqual(AspectSize(552.5, 630.0), half)

    def test_never_exceeds_available_space(self) -> None:
        for available in ((100, 1000), (1000, 100), (300, 300), (1920, 1080)):
            with self.subTest(available=available):
                size = fit_aspect_size(*available, 1105, 1260)
                self.assertLessEqual(size.width, available[0] + 1e-9)
                self.assertLessEqual(size.height, available[1] + 1e-9)
                self.assertAlmostEqual(1105 / 1260, size.width / size.height, places=6)

    def test_invalid_zero(self) -> None:
        self.assertEqual(AspectSize(0, 0), fit_aspect_size(0, 100, 10, 10))
        self.assertEqual(AspectSize(0, 0), fit_aspect_size(100, 0, 10, 10))
        self.assertEqual(AspectSize(0, 0), fit_aspect_size(100, 100, 0, 10))


class CanvasCoordinateTests(unittest.TestCase):
    def test_center_corners_roundtrip(self) -> None:
        width, height = 552.5, 630.0
        self.assertEqual((0.0, 0.0), canvas_to_normalized(0, 0, width, height))
        self.assertEqual((1.0, 1.0), canvas_to_normalized(width, height, width, height))
        center = canvas_to_normalized(width / 2, height / 2, width, height)
        self.assertAlmostEqual(0.5, center[0])
        self.assertAlmostEqual(0.5, center[1])
        pixel = normalized_to_canvas(*center, width, height)
        self.assertAlmostEqual(width / 2, pixel[0])
        self.assertAlmostEqual(height / 2, pixel[1])

    def test_resize_keeps_relative_position(self) -> None:
        for width, height in ((300, 342), (600, 684), (900, 1026)):
            point = normalized_to_canvas(0.25, 0.75, width, height)
            back = canvas_to_normalized(point[0], point[1], width, height)
            self.assertAlmostEqual(0.25, back[0])
            self.assertAlmostEqual(0.75, back[1])

    def test_outside_canvas_returns_none(self) -> None:
        self.assertIsNone(canvas_to_normalized(-1, 10, 500, 1000))
        self.assertIsNone(canvas_to_normalized(501, 10, 500, 1000))
        self.assertIsNone(canvas_to_normalized(10, -1, 500, 1000))
        self.assertIsNone(canvas_to_normalized(10, 1001, 500, 1000))
        self.assertIsNone(canvas_to_normalized(10, 10, 0, 100))

    def test_normalized_to_canvas_clamps(self) -> None:
        self.assertEqual((0.0, 0.0), normalized_to_canvas(-1, -2, 500, 1000))
        self.assertEqual((500.0, 1000.0), normalized_to_canvas(2, 3, 500, 1000))


if __name__ == "__main__":
    unittest.main()
