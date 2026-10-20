"""0.1.4：登录前/登出后悬浮窗不可见，热键提示。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from config import AppConfig
    from state.session import Session
    from ui.main_window import MainWindow

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class OverlayAuthGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, logged_in: bool = False, enabled: bool = True):
        config = AppConfig(
            use_mock=True,
            persist_token=False,
            server_migrated=False,
            overlay_enabled=enabled,
            shortcut_toggle="Ctrl+Shift+F9",
            shortcut_edit="Ctrl+Shift+F10",
        )
        session = Session(persist_token=False)
        if logged_in:
            session.set_login("token", {"id": "12", "username": "DeltaQA01"})
        window = MainWindow(config, session)
        window.overlay_controller.window_provider = lambda: None
        return window

    def _close(self, window) -> None:
        window.bridge.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_login_page_never_shows_overlay_even_if_enabled(self) -> None:
        window = self._window(logged_in=False, enabled=True)
        try:
            self.assertFalse(window.overlay_controller.enabled)
            self.assertFalse(window.overlay.isVisible())
        finally:
            self._close(window)

    def test_hotkey_on_login_page_is_silent_and_keeps_hidden(self) -> None:
        window = self._window(logged_in=False, enabled=True)
        try:
            window._on_global_hotkey("toggle")
            window._on_global_hotkey("edit")
            self.assertEqual("", window._last_hotkey_notice)
            self.assertEqual(set(), window.hotkeys.registered_actions)
            self.assertFalse(window.overlay.isVisible())
        finally:
            self._close(window)

    def test_hotkey_logged_in_without_game_is_silent(self) -> None:
        window = self._window(logged_in=True, enabled=False)
        try:
            window._find_game_window = lambda: None
            window._on_global_hotkey("toggle")
            self.assertEqual("", window._last_hotkey_notice)
            self.assertFalse(window.overlay.isVisible())
        finally:
            self._close(window)

    def test_hotkey_logged_in_with_game_shows_overlay_then_logout_hides(self) -> None:
        from types import SimpleNamespace

        window = self._window(logged_in=True, enabled=False)
        try:
            fake = SimpleNamespace(client_rect=(0, 0, 1600, 900), is_minimized=False)
            window._find_game_window = lambda: fake
            window.overlay_controller.window_provider = lambda: fake
            window._on_global_hotkey("toggle")
            self.assertTrue(window.overlay_controller.enabled)
            self.assertTrue(window.overlay.isVisible())
            window._show_login()
            self.assertFalse(window.overlay.isVisible())
            self.assertFalse(window.overlay_controller.enabled)
        finally:
            self._close(window)

    def test_login_registers_and_logout_unregisters_hotkeys(self) -> None:
        from unittest import mock

        window = self._window(logged_in=True, enabled=False)
        try:
            with mock.patch("ui.global_hotkeys.register_hotkey", return_value=True):
                window._show_rooms()
                self.assertEqual({"toggle", "edit"}, window.hotkeys.registered_actions)
            window._show_login()
            self.assertEqual(set(), window.hotkeys.registered_actions)
        finally:
            self._close(window)

    def test_logout_hides_and_stops_overlay(self) -> None:
        window = self._window(logged_in=True, enabled=True)
        try:
            window._show_login()
            self.assertFalse(window.overlay_controller.enabled)
            self.assertFalse(window.overlay.isVisible())
        finally:
            self._close(window)


if __name__ == "__main__":
    unittest.main()
