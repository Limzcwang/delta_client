"""P8：设置保存不切页、进房技能过滤、悬浮窗编辑箭头/无窗口。"""

from __future__ import annotations

import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import numpy as _np  # noqa: F401
    HAS_NUMPY = True
except Exception:  # noqa: BLE001
    HAS_NUMPY = False
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QDialog

    from config import AppConfig
    from core.models import Member, Room
    from core.skills import SkillState
    from state.session import Session
    from ui.main_window import MainWindow
    from ui.skill_overlay import SkillOverlay

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


class _DummyCoro:
    def close(self):
        pass


class _Signals:
    def connect(self, *_args, **_kwargs):
        pass


class _FakeWs:
    connected = True

    def __init__(self):
        self.off_count = 0
        self.canvas_sends = 0

    def send_skill_off(self, *args):
        self.off_count += 1
        return _DummyCoro()

    def send_canvas_op(self, *args):
        self.canvas_sends += 1
        return _DummyCoro()


class _FakeApi:
    def join_room(self, *args):
        return _DummyCoro()

    def get_canvas(self, code):
        return _DummyCoro()

    def close(self):
        return _DummyCoro()


class _FakeSettingsDialog:
    def __init__(self, config):
        self.config = config
        self.tabs = SimpleNamespace(setCurrentIndex=lambda _i: None, count=lambda: 3)
        for name in (
            "config_check_requested", "operator_recognition_requested", "test_requested",
            "nickname_save_requested", "password_change_requested", "hotkey_test_requested",
        ):
            setattr(self, name, _Signals())
        self._is_accepted = True

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def setWindowModality(self, *_args):
        pass

    def setAttribute(self, *_args):
        pass

    def windowFlags(self):
        return Qt.WindowType.Dialog

    def setWindowFlags(self, *_args):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted

    def config_result(self):
        return self.config


@unittest.skipUnless(HAS_QT, "PySide6 未安装")
class RoomOverlayFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        session = Session(persist_token=False)
        session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(AppConfig(use_mock=True, persist_token=False, overlay_auto_show=False), session)
        window._current_room = Room(id="1", code="ABC123", name="test")
        window._room_password = None
        window._membership_confirmed = True
        window._ws_generation = 1
        window._ws = _FakeWs()
        window.api = _FakeApi()
        window._safe_submit = lambda coro, on_success=None, on_error=None: (coro.close() if hasattr(coro, "close") else None)
        return window

    def _close(self, window):
        window.bridge.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_settings_save_stays_in_room(self) -> None:
        window = self._window()
        try:
            window._apply_overlay_config = lambda: None
            window._apply_auto_config = lambda: None
            window._register_hotkeys = lambda: None
            window._close_api = lambda *a, **k: None
            window._build_api = lambda: window.api
            window.stack.setCurrentWidget(window.room_view)
            with mock.patch("ui.main_window.SettingsDialog", lambda *a, **k: _FakeSettingsDialog(window.config)), mock.patch(
                "ui.main_window.save_config", return_value="cfg.json"
            ), mock.patch("ui.main_window.QMessageBox.warning"), mock.patch.object(window, "_on_leave_room") as leave:
                window._open_settings()
                leave.assert_not_called()
                self.assertIs(window.stack.currentWidget(), window.room_view)
        finally:
            self._close(window)

    @unittest.skipUnless(HAS_NUMPY, "完整 Qt/原生窗口测试需要 build venv")
    def test_modal_open_does_not_spam_main_window_paint(self) -> None:
        window = self._window()
        counts = {"paint": 0, "activation": 0, "state": 0}

        class Filter(QObject):
            def eventFilter(self, obj, event):
                if obj is window:
                    if event.type() == QEvent.Type.Paint:
                        counts["paint"] += 1
                    elif event.type() == QEvent.Type.ActivationChange:
                        counts["activation"] += 1
                    elif event.type() == QEvent.Type.WindowStateChange:
                        counts["state"] += 1
                return False

        class SlowDialog(_FakeSettingsDialog):
            def exec(self):
                QTest.qWait(700)
                return QDialog.DialogCode.Rejected

        filt = Filter()
        window.installEventFilter(filt)
        try:
            window.show()
            self.app.processEvents()
            with mock.patch("ui.main_window.SettingsDialog", lambda *a, **k: SlowDialog(window.config)):
                window._open_settings()
            QTest.qWait(150)
            self.assertLess(counts["paint"], 60)
            self.assertLess(counts["activation"], 4)
        finally:
            window.removeEventFilter(filt)
            self._close(window)

    def test_auto_show_starts_overlay_when_logged_in(self) -> None:
        window = self._window()
        try:
            window.config = replace(window.config, overlay_auto_show=True)
            window._find_game_window = lambda: None
            calls = []
            window.overlay_controller.start = lambda: calls.append("start")
            window.overlay_controller.follow = lambda force=False: calls.append("follow")
            window._apply_overlay_config()
            self.assertIn("start", calls)
            self.assertIn("follow", calls)
        finally:
            self._close(window)

    def test_auto_hide_and_manual_hide_suppression(self) -> None:
        window = self._window()
        try:
            window.config = replace(window.config, overlay_auto_show=True)
            fake = SimpleNamespace(pid=1, title="三角洲行动", client_rect=(0, 0, 1600, 900), is_minimized=False)
            window._resolve_game_window = lambda **k: SimpleNamespace(window=fake, candidates=[], reason="ok")
            window._overlay_manual_hidden = False
            window._auto_game_present = False
            def fake_start():
                window.overlay_controller.enabled = True
                window.overlay.show()
            window.overlay_controller.start = fake_start
            window.overlay_controller.follow = lambda force=False: None
            window.overlay_controller.stop = lambda: setattr(window.overlay_controller, "enabled", False)
            window._tick_auto_overlay()
            self.assertTrue(window.overlay_controller.enabled)
            self.assertIn("隐藏悬浮窗", window.room_view.overlay_toggle_button.text())
            window._toggle_overlay()  # 手动隐藏
            self.assertTrue(window._overlay_manual_hidden)
            window._tick_auto_overlay()
            self.assertFalse(window.overlay_controller.enabled)  # 本次游戏内不再自动弹
            window._resolve_game_window = lambda **k: SimpleNamespace(window=None, candidates=[], reason="none")
            window._tick_auto_overlay()
            window._resolve_game_window = lambda **k: SimpleNamespace(window=fake, candidates=[], reason="ok")
            window._tick_auto_overlay()
            self.assertTrue(window.overlay_controller.enabled)  # 重新进入游戏重置
        finally:
            self._close(window)

    def test_tray_menu_actions_trigger_overlay(self) -> None:
        window = self._window()
        try:
            if not hasattr(window, "tray_toggle_action"):
                self.skipTest("系统托盘不可用")
            calls = []
            window._toggle_overlay = lambda: calls.append("toggle")
            window._toggle_overlay_edit = lambda: calls.append("edit")
            window.tray_toggle_action.trigger()
            window.tray_edit_action.trigger()
            self.assertEqual(["toggle", "edit"], calls)
        finally:
            self._close(window)

    def test_auto_tick_hides_when_window_lost(self) -> None:
        window = self._window()
        try:
            window.config = replace(window.config, overlay_auto_show=True)
            window.overlay_controller.enabled = True
            window.overlay.show()
            window._overlay_visible = True
            window._resolve_game_window = lambda **k: SimpleNamespace(window=None, candidates=[], reason="none")
            window._auto_game_present = True
            window._tick_auto_overlay()
            self.assertFalse(window.overlay_controller.enabled)
            self.assertFalse(window.overlay.isVisible())
            self.assertIn("显示悬浮窗", window.room_view.overlay_toggle_button.text())
        finally:
            self._close(window)

    def test_no_hotkey_attributes_remain(self) -> None:
        window = self._window()
        try:
            self.assertFalse(hasattr(window, "hotkeys"))
            self.assertFalse(hasattr(window, "_toggle_shortcut"))
            self.assertFalse(hasattr(window, "_edit_shortcut"))
            self.assertEqual("显示悬浮窗", window.room_view.overlay_toggle_button.text())
            self.assertEqual("编辑悬浮窗", window.room_view.overlay_edit_button.text())
        finally:
            self._close(window)

    def test_room_fallback_buttons_trigger_overlay_actions(self) -> None:
        window = self._window()
        try:
            calls = []
            window._toggle_overlay = lambda: calls.append("toggle")
            window._toggle_overlay_edit = lambda: calls.append("edit")
            window.room_view.overlay_toggle_button.click()
            window.room_view.overlay_edit_button.click()
            self.assertEqual(["toggle", "edit"], calls)
        finally:
            self._close(window)

    def test_edit_mode_no_hide_show_and_drag(self) -> None:
        overlay = SkillOverlay()
        try:
            overlay.show()
            overlay.set_opacity(0.30)
            with mock.patch.object(overlay, "hide", wraps=overlay.hide) as hide, mock.patch.object(
                overlay, "show", wraps=overlay.show
            ) as show:
                overlay.set_edit_mode(True)
                hide.assert_not_called()
                show.assert_not_called()
            self.assertTrue(overlay.edit_mode)
            self.assertAlmostEqual(1.0, overlay.opacity, delta=0.01)
            handle = overlay.drag_handle_rect().center()
            press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, handle, handle, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            overlay.mousePressEvent(press)
            start = (overlay.x(), overlay.y())
            point = QPoint(handle.x() + 25, handle.y() + 18)
            move = QMouseEvent(QMouseEvent.Type.MouseMove, point, point, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            overlay.mouseMoveEvent(move)
            self.assertNotEqual(start, (overlay.x(), overlay.y()))
            positions = []
            overlay.position_changed.connect(lambda x, y: positions.append((x, y)))
            release = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, point, point, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
            overlay.mouseReleaseEvent(release)
            self.assertTrue(positions)
            overlay.set_edit_mode(False)
            self.assertAlmostEqual(0.30, overlay.opacity, delta=0.02)
        finally:
            overlay.close()
            overlay.deleteLater()
            self.app.processEvents()

    def test_room_joined_hides_self_and_sends_off(self) -> None:
        window = self._window()
        try:
            window._skill_share_enabled = False
            window._on_ws_message(1, {
                "type": "room_joined",
                "room": {"id": "1", "code": "ABC123", "name": "test"},
                "members": [{"id": "12", "nickname": "我"}, {"id": "13", "nickname": "队友"}],
                "skill_states": [
                    {"user_id": "12", "nickname": "我", "captured_at": 1},
                    {"user_id": "13", "nickname": "队友", "captured_at": 1},
                ],
            })
            self.assertEqual(1, window._ws.off_count)
            self.assertIsNone(window._skills.get("12"))
            self.assertIsNotNone(window._skills.get("13"))
            self.assertNotIn("12", window.room_view.skill_panel._rows)
            self.assertIn("13", window.room_view.skill_panel._rows)
        finally:
            self._close(window)

    def test_share_off_once_per_room_and_resets_between_rooms(self) -> None:
        window = self._window()
        fake = _FakeWs()
        try:
            window._start_ws = lambda room: None
            window._refresh_members_http = lambda *a, **k: None
            window._load_chat_history = lambda *a, **k: None
            window._refresh_operator_config = lambda *a, **k: None
            window._apply_auto_config = lambda: None
            window._ws_generation = 1
            room_a = Room(id="a", code="AAAAA", name="A")
            window._enter_room(room_a)
            window._ws = fake
            msg_a = {"type": "room_joined", "room": {"id": "a", "code": "AAAAA", "name": "A"}}
            window._on_ws_message(1, msg_a)
            self.assertEqual(1, fake.off_count)
            window._on_ws_message(1, msg_a)
            self.assertEqual(1, fake.off_count)  # 同房重连幂等
            room_b = Room(id="b", code="BBBBB", name="B")
            window._enter_room(room_b)
            window._ws = fake
            window._on_ws_message(1, {"type": "room_joined", "room": {"id": "b", "code": "BBBBB", "name": "B"}})
            self.assertEqual(2, fake.off_count)
        finally:
            self._close(window)

    def test_no_game_does_not_show_overlay(self) -> None:
        window = self._window()
        try:
            window.overlay.hide()
            with mock.patch.object(window, "_find_game_window", return_value=None):
                window._toggle_overlay()
                self.assertFalse(window.overlay.isVisible())
                window._toggle_overlay_edit()
                self.assertFalse(window.overlay.edit_mode)
                self.assertFalse(window.overlay.isVisible())
        finally:
            self._close(window)

    def test_overlay_edit_opacity_and_cross_handle(self) -> None:
        overlay = SkillOverlay()
        try:
            overlay.show()
            overlay.set_opacity(0.30)
            overlay.set_edit_mode(True)
            self.assertAlmostEqual(1.0, overlay.opacity, delta=0.01)
            self.assertTrue(hasattr(overlay, "drag_handle_rect"))
            handle = overlay.drag_handle_rect()
            self.assertEqual(28, handle.width())
            self.assertEqual(28, handle.height())
            up = handle.center()
            press = QMouseEvent(QMouseEvent.Type.MouseButtonPress, up, up, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            overlay.mousePressEvent(press)
            start_x, start_y = overlay.x(), overlay.y()
            move_point = QPoint(up.x() + 30, up.y() + 24)
            move = QMouseEvent(QMouseEvent.Type.MouseMove, move_point, move_point, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            overlay.mouseMoveEvent(move)
            self.assertNotEqual(start_x, overlay.x())
            self.assertNotEqual(start_y, overlay.y())
            overlay.set_edit_mode(False)
            self.assertAlmostEqual(0.30, overlay.opacity, delta=0.02)
        finally:
            overlay.close()
            overlay.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
