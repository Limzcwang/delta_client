"""H4/H5 画板底图充满、宽高比锁定、坐标/透明层/图标工具栏测试（PySide6，离屏）。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent, QPixmap
    from PySide6.QtWidgets import QApplication, QToolButton

    from ui.canvas_view import MAP_HEIGHT, MAP_WIDTH, CanvasSurface, CanvasView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class CanvasAspectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.widgets: list = []

    def tearDown(self) -> None:
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.app.processEvents()

    def _view(self, width: int, height: int) -> CanvasView:
        view = CanvasView()
        self.widgets.append(view)
        view.resize(width, height)
        view.show()
        self.app.processEvents()
        return view

    def _surface(self, width: int = 500, height: int = 1000) -> CanvasSurface:
        surface = CanvasSurface()
        self.widgets.append(surface)
        surface.resize(width, height)
        surface.show()
        self.app.processEvents()
        return surface

    def test_map_loaded_and_canvas_aspect_matches_map(self) -> None:
        view = self._view(700, 620)
        self.assertFalse(view.surface.map_pixmap.isNull(), "内置底图必须加载成功")
        self.assertEqual(
            (MAP_WIDTH, MAP_HEIGHT),
            (view.surface.map_pixmap.width(), view.surface.map_pixmap.height()),
        )
        for width, height in ((900, 500), (420, 680), (600, 600), (1105, 1260)):
            view.resize(width, height)
            self.app.processEvents()
            surface = view.surface
            self.assertAlmostEqual(
                MAP_WIDTH / MAP_HEIGHT,
                surface.width() / max(1, surface.height()),
                places=2,
            )
            self.assertLessEqual(surface.width(), view.host.width() + 1)
            self.assertLessEqual(surface.height(), view.host.height() + 1)
            # 画布内部就是图片：canvas_rect 铺满控件
            self.assertEqual(surface.rect(), surface.canvas_rect().toRect())

    def test_canvas_edges_are_map_pixels(self) -> None:
        view = self._view(700, 620)
        surface = view.surface
        pixmap = QPixmap(50, 100)
        pixmap.fill(QColor("#FF00FF"))
        surface.map_pixmap = pixmap
        surface.map_size = (50, 100)
        for width, height in ((900, 500), (420, 680), (600, 600)):
            view.resize(width, height)
            self.app.processEvents()
            image = surface.grab().toImage()
            w, h = max(1, surface.width() - 1), max(1, surface.height() - 1)
            for x, y in ((0, 0), (w, 0), (0, h), (w, h)):
                color = image.pixelColor(x, y)
                self.assertEqual(
                    (255, 0, 255),
                    (color.red(), color.green(), color.blue()),
                    f"{width}x{height} 画布角 ({x},{y}) 不是底图像素",
                )

    def test_coordinates_use_canvas_and_outside_ignored(self) -> None:
        surface = self._surface(500, 1000)
        center = surface._to_normalized(QPointF(250, 500))
        self.assertAlmostEqual(0.5, center[0])
        self.assertAlmostEqual(0.5, center[1])
        self.assertEqual((0.0, 0.0), surface._to_normalized(QPointF(0, 0)))
        corner = surface._to_normalized(QPointF(500, 1000))
        self.assertAlmostEqual(1.0, corner[0])
        self.assertAlmostEqual(1.0, corner[1])
        self.assertIsNone(surface._to_normalized(QPointF(-1, 10)))
        self.assertIsNone(surface._to_normalized(QPointF(501, 10)))
        outside = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(-1, 10),
            QPointF(-1, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        surface.mousePressEvent(outside)
        self.assertFalse(surface._drawing, "画布外按下不能产生绘制")

    def test_resize_keeps_stroke_relative_position(self) -> None:
        surface = self._surface(500, 1000)
        point = surface._to_widget(surface.canvas_rect(), 0.5, 0.75)
        self.assertAlmostEqual(250.0, point.x())
        self.assertAlmostEqual(750.0, point.y())
        surface.resize(300, 600)
        self.app.processEvents()
        point = surface._to_widget(surface.canvas_rect(), 0.5, 0.75)
        self.assertAlmostEqual(150.0, point.x())
        self.assertAlmostEqual(450.0, point.y())

    def test_eraser_clears_layer_not_map_and_clear_keeps_map(self) -> None:
        surface = self._surface(500, 1000)
        point = (250, 500)
        baseline = surface.grab().toImage().pixelColor(*point)
        surface.draw_stroke([(0.5, 0.5)], "#FFFFFF", 24, "pen")
        drawn = surface.grab().toImage().pixelColor(*point)
        self.assertEqual(1, surface.document.count)
        self.assertGreater(drawn.lightness(), baseline.lightness(), "白笔画应覆盖底图")

        surface.draw_stroke([(0.5, 0.5)], "#FFFFFF", 32, "eraser")
        erased = surface.grab().toImage().pixelColor(*point)
        self.assertEqual(
            (baseline.red(), baseline.green(), baseline.blue()),
            (erased.red(), erased.green(), erased.blue()),
            "橡皮应清除透明层，底图像素恢复",
        )

        surface.clear()
        self.assertEqual(0, surface.document.count)
        cleared = surface.grab().toImage().pixelColor(*point)
        self.assertEqual(
            (baseline.red(), baseline.green(), baseline.blue()),
            (cleared.red(), cleared.green(), cleared.blue()),
            "清空只清笔画层，底图不变",
        )
        self.assertFalse(surface.map_pixmap.isNull())

    def test_toolbar_icon_buttons_and_highlight(self) -> None:
        view = self._view(420, 600)
        self.assertEqual(5, len(view.tool_buttons))
        for button in view.tool_buttons:
            self.assertFalse(button.icon().isNull(), f"{button.toolTip()} 缺少图标")
            self.assertGreaterEqual(button.height(), 40)
            self.assertTrue(button.toolTip())
        self.assertTrue(view.pen_button.isChecked())
        self.assertTrue(view.pen_button.isCheckable())
        self.assertTrue(view.eraser_button.isCheckable())
        view.eraser_button.click()
        self.assertTrue(view.eraser_button.isChecked())
        self.assertFalse(view.pen_button.isChecked())
        self.assertFalse(hasattr(view, "width_button"))
        self.assertEqual("Ctrl+Z", view.undo_button.shortcut().toString())


if __name__ == "__main__":
    unittest.main()
