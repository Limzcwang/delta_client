"""H4 底图 letterbox / 归一化坐标换算（纯逻辑）。"""

from __future__ import annotations

import unittest

from core.canvas_geometry import (
    FitRect,
    fit_rect,
    normalized_to_widget,
    widget_to_normalized,
)


class FitRectTests(unittest.TestCase):
    def test_vertical_map_letterbox(self) -> None:
        # 1105×1260 竖图放进 400×300：以高为准，左右留黑边
        rect = fit_rect(400, 300, 1105, 1260)
        self.assertAlmostEqual(300.0, rect.height)
        self.assertAlmostEqual(300 * 1105 / 1260, rect.width)
        self.assertGreater(rect.left, 0)
        self.assertAlmostEqual(0.0, rect.top)
        self.assertAlmostEqual(rect.width / rect.height, 1105 / 1260, places=6)

    def test_horizontal_image_letterbox(self) -> None:
        rect = fit_rect(400, 300, 1920, 1080)
        self.assertAlmostEqual(400.0, rect.width)
        self.assertAlmostEqual(225.0, rect.height)
        self.assertAlmostEqual(0.0, rect.left)
        self.assertAlmostEqual(37.5, rect.top)
        self.assertAlmostEqual(16 / 9, rect.width / rect.height, places=6)

    def test_square_image(self) -> None:
        rect = fit_rect(300, 500, 100, 100)
        self.assertAlmostEqual(300.0, rect.width)
        self.assertAlmostEqual(300.0, rect.height)
        self.assertAlmostEqual(100.0, rect.top)
        self.assertAlmostEqual(0.0, rect.left)

    def test_small_viewport(self) -> None:
        rect = fit_rect(100, 100, 1105, 1260)
        self.assertAlmostEqual(100.0, rect.height)
        self.assertAlmostEqual(100 * 1105 / 1260, rect.width)
        self.assertGreater(rect.left, 0)

    def test_invalid_empty(self) -> None:
        for args in ((0, 100, 10, 10), (100, 0, 10, 10), (100, 100, 0, 10), (100, 100, 10, 0)):
            with self.subTest(args=args):
                rect = fit_rect(*args)
                self.assertEqual(FitRect(0, 0, 0, 0), rect)
                self.assertIsNone(widget_to_normalized(0, 0, rect))


class CoordinateRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rect = fit_rect(800, 600, 1105, 1260)  # 竖图 letterbox

    def test_center_and_roundtrip(self) -> None:
        center = widget_to_normalized(
            self.rect.left + self.rect.width / 2, self.rect.top + self.rect.height / 2, self.rect
        )
        self.assertIsNotNone(center)
        self.assertAlmostEqual(0.5, center[0])
        self.assertAlmostEqual(0.5, center[1])
        px, py = normalized_to_widget(center[0], center[1], self.rect)
        self.assertAlmostEqual(self.rect.left + self.rect.width / 2, px)
        self.assertAlmostEqual(self.rect.top + self.rect.height / 2, py)

    def test_corners_and_clamp(self) -> None:
        self.assertEqual((0.0, 0.0), widget_to_normalized(self.rect.left, self.rect.top, self.rect))
        corner = widget_to_normalized(self.rect.right, self.rect.bottom, self.rect)
        self.assertAlmostEqual(1.0, corner[0])
        self.assertAlmostEqual(1.0, corner[1])
        # 归一化值越界时 clamp 到 0–1
        x, y = normalized_to_widget(-1, 2, self.rect)
        self.assertAlmostEqual(self.rect.left, x)
        self.assertAlmostEqual(self.rect.bottom, y)

    def test_letterbox_outside_returns_none(self) -> None:
        # 竖图左右黑边内、图片区域外
        self.assertIsNone(widget_to_normalized(self.rect.left / 2, 100, self.rect))
        self.assertIsNone(widget_to_normalized(self.rect.right + 5, 100, self.rect))
        self.assertIsNone(widget_to_normalized(100, self.rect.top - 1, self.rect))
        self.assertIsNone(widget_to_normalized(100, self.rect.bottom + 1, self.rect))


if __name__ == "__main__":
    unittest.main()
