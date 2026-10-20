"""E4 悬浮窗：穿透/编辑/跟随/无游戏/位置持久化测试。"""

from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    from core.skills import SkillState
    from ui.skill_overlay import OverlayController, SkillOverlay

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@dataclass
class FakeWindow:
    client_rect: tuple[int, int, int, int] = (100, 100, 1600, 900)
    is_minimized: bool = False



def _widget_visible_safe(widget):
    try:
        return bool(widget.isVisible())
    except RuntimeError:
        return False

@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.overlay = SkillOverlay()
        self.overlay.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.overlay.close()
        self.overlay.deleteLater()
        self.app.processEvents()

    def test_default_transparent_and_opacity(self) -> None:
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertAlmostEqual(0.30, self.overlay.opacity, delta=0.05)
        self.assertAlmostEqual(0.30, self.overlay._base_opacity)
        self.overlay.set_opacity(0.55)
        self.assertAlmostEqual(0.55, self.overlay.opacity, delta=0.05)

    def test_edit_mode_toggles_input(self) -> None:
        flags_before = self.overlay.windowFlags()
        self.overlay.set_edit_mode(True)
        # E1：不重建原生窗口，Qt flags 保持不变，穿透由原生样式/属性切换。
        self.assertEqual(flags_before, self.overlay.windowFlags())
        self.assertFalse(self.overlay._click_through)
        self.assertAlmostEqual(1.0, self.overlay.opacity, delta=0.05)
        self.overlay.set_edit_mode(False)
        self.assertTrue(self.overlay._click_through)
        self.assertEqual(flags_before, self.overlay.windowFlags())

    def test_follow_and_no_game(self) -> None:
        window = [FakeWindow()]
        ctl = OverlayController(
            self.overlay, lambda: window[0], lambda: (1920, 1080)
        )
        ctl.start()
        self.assertTrue(ctl.attached)
        self.assertEqual("已附加", ctl.last_reason)
        self.assertLess(self.overlay.x(), 1600)
        self.assertGreater(self.overlay.y(), 100)
        window[0] = None
        ctl.follow()
        self.assertFalse(ctl.attached)
        self.assertFalse(self.overlay.isVisible())
        self.assertIn("等待游戏窗口", ctl.last_reason)
        window[0] = FakeWindow(is_minimized=True)
        ctl.follow()
        self.assertFalse(self.overlay.isVisible())
        self.assertIn("最小化", ctl.last_reason)
        ctl.stop()

    def test_fullscreen_client_rect_still_attaches(self) -> None:
        window = [FakeWindow(client_rect=(0, 0, 1920, 1080))]
        ctl = OverlayController(self.overlay, lambda: window[0], lambda: (1920, 1080))
        try:
            with mock.patch("ui.skill_overlay._apply_win32_topmost", return_value=True) as topmost:
                ctl.start()
            self.assertTrue(ctl.attached)
            self.assertNotIn("独占", ctl.last_reason)
            self.assertTrue(self.overlay.isVisible())
            topmost.assert_called()
        finally:
            ctl.stop()

    def test_topmost_only_on_state_or_geometry_change(self) -> None:
        window = [FakeWindow(client_rect=(0, 0, 1920, 1080))]
        ctl = OverlayController(self.overlay, lambda: window[0], lambda: (1920, 1080))
        try:
            with mock.patch("ui.skill_overlay._apply_win32_topmost", return_value=True) as topmost:
                ctl.start()
                calls_after_start = topmost.call_count
                self.assertGreaterEqual(calls_after_start, 1)
                ctl.follow()
                ctl.follow()
                self.assertEqual(calls_after_start, topmost.call_count)  # 同几何不重复 SetWindowPos
                window[0] = FakeWindow(client_rect=(0, 0, 1600, 900))
                ctl.follow()
                self.assertGreater(topmost.call_count, calls_after_start)  # 几何变化才调用
                self.overlay.set_edit_mode(True)
                before = topmost.call_count
                ctl.follow()
                self.assertEqual(before, topmost.call_count)
        finally:
            ctl.stop()

    def test_pause_stops_and_resume_restarts_timer(self) -> None:
        window = [FakeWindow()]
        ctl = OverlayController(self.overlay, lambda: window[0], lambda: (1920, 1080))
        try:
            ctl.start()
            self.assertTrue(ctl._timer.isActive())
            ctl.pause("settings")
            self.assertTrue(ctl.paused)
            self.assertFalse(ctl._timer.isActive())
            self.assertFalse(self.overlay.isVisible())
            ctl.resume(delay_ms=0)
            self.assertFalse(ctl.paused)
            self.assertTrue(ctl._timer.isActive())
            self.assertTrue(self.overlay.isVisible())
        finally:
            ctl.stop()

    def test_modal_guard_does_not_touch_native_window(self) -> None:
        window = [FakeWindow()]
        ctl = OverlayController(self.overlay, lambda: window[0], lambda: (1920, 1080))
        try:
            ctl.start()
            with mock.patch("ui.skill_overlay.QApplication.activeModalWidget", return_value=object()):
                with mock.patch("ui.skill_overlay._apply_win32_topmost") as topmost, mock.patch.object(
                    self.overlay, "hide", wraps=self.overlay.hide
                ) as hide:
                    ctl.follow(force=True)
                    ctl.follow(force=True)
                    topmost.assert_not_called()
                    self.assertEqual(1, hide.call_count)
            self.assertIn("模态", ctl.last_reason)
            self.assertFalse(self.overlay.isVisible())
            ctl.follow(force=True)
            self.assertTrue(self.overlay.isVisible())
        finally:
            ctl.stop()

    def test_invalid_widget_is_not_native_called(self) -> None:
        from ui.skill_overlay import _widget_alive

        class Dead:
            def isVisible(self):
                raise RuntimeError("deleted")

        self.assertFalse(_widget_visible_safe(Dead()))

    def test_fixed_position_after_edit(self) -> None:
        window = [FakeWindow()]
        ctl = OverlayController(self.overlay, lambda: window[0], lambda: (1920, 1080))
        ctl.start()
        ctl.fixed_position = (345, 222)
        ctl.follow()
        self.assertEqual(QPoint(345, 222), self.overlay.pos())
        ctl.stop()

    def test_states_and_scale(self) -> None:
        state = SkillState.from_ws(
            {
                "user_id": "1",
                "nickname": "我",
                "operator": "红狼",
                "captured_at": 1,
                "skills": [
                    {"slot": 0, "state": "charging", "pct": 16, "ready_at": 50_000},
                    {"slot": 1, "state": "ready"},
                    {"slot": 2, "state": "unknown"},
                ],
            }
        )
        self.overlay.set_states([state])
        self.assertEqual([state], self.overlay.states)
        old_width = self.overlay.width()
        self.overlay.set_scale(1.5)
        self.assertGreaterEqual(self.overlay.width(), old_width)
        self.assertGreaterEqual(self.overlay.height(), 48)

    def test_drag_emits_position(self) -> None:
        positions = []
        self.overlay.position_changed.connect(lambda x, y: positions.append((x, y)))
        self.overlay.set_edit_mode(True)
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPoint(10, 10),
            QPoint(10, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPoint(30, 30),
            QPoint(30, 30),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPoint(30, 30),
            QPoint(30, 30),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.overlay.mousePressEvent(press)
        self.overlay.mouseMoveEvent(move)
        self.overlay.mouseReleaseEvent(release)
        self.assertEqual(1, len(positions))


if __name__ == "__main__":
    unittest.main()
