"""H4 画板底图/透明层/图标工具栏测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QMouseEvent
    from PySide6.QtWidgets import QApplication, QToolButton

    from ui.canvas_view import MAP_HEIGHT, MAP_WIDTH, CanvasSurface, CanvasView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class CanvasMapTests(unittest.TestCase):
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

    def _surface(self, width: int = 400, height: int = 520) -> CanvasSurface:
        surface = CanvasSurface()
        self.widgets.append(surface)
        surface.resize(width, height)
        surface.show()
        self.app.processEvents()
        return surface

    def test_map_loaded_and_aspect_fit(self) -> None:
        surface = self._surface()
        self.assertFalse(surface.map_pixmap.isNull(), "内置底图必须加载成功")
        self.assertEqual((MAP_WIDTH, MAP_HEIGHT), (surface.map_pixmap.width(), surface.map_pixmap.height()))
        rect = surface.canvas_rect()
        self.assertAlmostEqual(MAP_WIDTH / MAP_HEIGHT, rect.width() / rect.height(), places=6)
        # 竖图在横视口内左右 letterbox
        self.assertGreater(rect.top(), 0)
        self.assertAlmostEqual(surface.width(), rect.width(), places=3)
        self.assertLessEqual(rect.width(), surface.width())

        for width, height in ((300, 700), (700, 300), (500, 500)):
            surface.resize(width, height)
            self.app.processEvents()
            rect = surface.canvas_rect()
            self.assertAlmostEqual(
                MAP_WIDTH / MAP_HEIGHT, rect.width() / rect.height(), places=6
            )
            self.assertGreaterEqual(rect.left(), 0)
            self.assertGreaterEqual(rect.top(), 0)
            self.assertLessEqual(rect.right(), width + 0.01)
            self.assertLessEqual(rect.bottom(), height + 0.01)

    def test_coordinates_use_image_rect_and_outside_ignored(self) -> None:
        surface = self._surface()
        rect = surface.canvas_rect()
        center = surface._to_normalized(
            QPointF(rect.left() + rect.width() / 2, rect.top() + rect.height() / 2)
        )
        self.assertAlmostEqual(0.5, center[0])
        self.assertAlmostEqual(0.5, center[1])
        self.assertIsNone(surface._to_normalized(QPointF(rect.left() / 2, 10)))
        outside = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(rect.left() / 2, 10),
            QPointF(rect.left() / 2, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        surface.mousePressEvent(outside)
        self.assertFalse(surface._drawing, "图片区域外按下不能产生绘制")

    def test_eraser_clears_layer_not_map_and_clear_keeps_map(self) -> None:
        surface = self._surface(500, 600)
        rect = surface.canvas_rect()
        point = (rect.left() + rect.width() / 2, rect.top() + rect.height() / 2)
        baseline = surface.grab().toImage().pixelColor(int(point[0]), int(point[1]))

        surface.draw_stroke([(0.5, 0.5)], "#FFFFFF", 24, "pen")
        drawn = surface.grab().toImage().pixelColor(int(point[0]), int(point[1]))
        self.assertEqual(1, surface.document.count)
        self.assertGreater(drawn.lightness(), baseline.lightness(), "白笔画应覆盖底图")

        surface.draw_stroke([(0.5, 0.5)], "#FFFFFF", 32, "eraser")
        erased = surface.grab().toImage().pixelColor(int(point[0]), int(point[1]))
        self.assertEqual(
            (baseline.red(), baseline.green(), baseline.blue()),
            (erased.red(), erased.green(), erased.blue()),
            "橡皮应清除透明层，底图像素恢复",
        )

        surface.clear()
        self.assertEqual(0, surface.document.count)
        cleared = surface.grab().toImage().pixelColor(int(point[0]), int(point[1]))
        self.assertEqual(
            (baseline.red(), baseline.green(), baseline.blue()),
            (cleared.red(), cleared.green(), cleared.blue()),
            "清空只清笔画层，底图不变",
        )
        self.assertFalse(surface.map_pixmap.isNull())

    def test_toolbar_icon_buttons_and_highlight(self) -> None:
        view = CanvasView()
        self.widgets.append(view)
        view.resize(420, 600)
        view.show()
        self.app.processEvents()
        buttons = view.findChildren(QToolButton)
        self.assertGreaterEqual(len(buttons), 7)
        for button in buttons:
            self.assertFalse(button.icon().isNull(), f"{button.toolTip()} 缺少图标")
            self.assertGreaterEqual(button.height(), 40)
            self.assertTrue(button.toolTip())
        self.assertTrue(view.pen_button.isChecked())
        self.assertTrue(view.pen_button.isCheckable())
        self.assertTrue(view.eraser_button.isCheckable())
        view.eraser_button.click()
        self.assertTrue(view.eraser_button.isChecked())
        self.assertFalse(view.pen_button.isChecked())
        old_width = view.surface.stroke_width
        view.width_button.click()
        self.assertNotEqual(old_width, view.surface.stroke_width)
        self.assertIn(str(view.surface.stroke_width), view.width_button.toolTip())
        self.assertEqual("Ctrl+Z", view.undo_button.shortcut().toString())


if __name__ == "__main__":
    unittest.main()


