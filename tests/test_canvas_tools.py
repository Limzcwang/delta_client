"""画板尺寸浮层：画笔圆点/橡皮方块、宽度映射、角标、重开。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

    from ui.canvas_view import CanvasView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class CanvasSizePopoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.views: list[CanvasView] = []

    def tearDown(self) -> None:
        for view in self.views:
            view.close()
            view.deleteLater()
        self.app.processEvents()

    def _view(self) -> CanvasView:
        view = CanvasView()
        self.views.append(view)
        view.resize(420, 700)
        view.show()
        self.app.processEvents()
        return view

    def test_toolbar_has_six_buttons_and_badges(self) -> None:
        view = self._view()
        self.assertEqual(5, len(view.tool_buttons))
        self.assertFalse(hasattr(view, "width_button"))
        self.assertEqual("3", view.pen_button.size_badge.text())
        self.assertEqual("12", view.eraser_button.size_badge.text())

    def test_pen_popover_circles_and_width_mapping(self) -> None:
        view = self._view()
        view.pen_button.click()
        self.app.processEvents()
        popover = view.size_popover
        self.assertTrue(popover.isVisible())
        self.assertEqual(3, len(popover.option_buttons))
        self.assertEqual([8, 14, 22], [button.diameter for button in popover.option_buttons])
        self.assertTrue(all(button.shape == "circle" for button in popover.option_buttons))
        self.assertTrue(popover.option_buttons[0].isChecked())
        popover.option_buttons[1].click()
        self.app.processEvents()
        self.assertEqual(6, view.surface.stroke_width)
        self.assertEqual("6", view.pen_button.size_badge.text())
        self.assertFalse(popover.isVisible())

    def test_eraser_popover_squares_and_width_mapping(self) -> None:
        view = self._view()
        view.eraser_button.click()
        self.app.processEvents()
        popover = view.size_popover
        self.assertTrue(popover.isVisible())
        self.assertEqual([10, 18, 28], [button.diameter for button in popover.option_buttons])
        self.assertTrue(all(button.shape == "square" for button in popover.option_buttons))
        popover.option_buttons[-1].click()
        self.app.processEvents()
        self.assertEqual(32, view.surface.stroke_width)
        self.assertEqual("32", view.eraser_button.size_badge.text())
        self.assertTrue(view.eraser_button.isChecked())

    def test_click_selected_tool_reopens_popover(self) -> None:
        view = self._view()
        view.pen_button.click()
        self.app.processEvents()
        self.assertTrue(view.size_popover.isVisible())
        view.size_popover.hide()
        view.pen_button.click()
        self.app.processEvents()
        self.assertTrue(view.size_popover.isVisible())
        self.assertEqual("pen", view.size_popover.tool)

    def test_widths_stay_in_protocol_range(self) -> None:
        view = self._view()
        for width in view.PEN_WIDTHS + view.ERASER_WIDTHS:
            self.assertTrue(1 <= width <= 32)
        self.assertEqual((3, 6, 12), view.PEN_WIDTHS)
        self.assertEqual((12, 24, 32), view.ERASER_WIDTHS)


if __name__ == "__main__":
    unittest.main()
