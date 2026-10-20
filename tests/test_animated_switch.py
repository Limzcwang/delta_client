"""ToggleSwitch / AnimatedSwitch：状态、键盘、动画终点。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ui.animated_switch import AnimatedSwitch
from ui.switch_row import SwitchRow

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtQuickWidgets import QQuickWidget

    HAS_QML = True
except Exception:  # noqa: BLE001
    HAS_QML = False


class SwitchRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_state_and_toggled_sync(self) -> None:
        row = SwitchRow("标题", "说明", False)
        seen: list[bool] = []
        row.toggled.connect(seen.append)
        self.assertFalse(row.isChecked())
        row.setChecked(True)
        self.assertTrue(row.isChecked())
        self.assertEqual([True], seen)
        row.setChecked(False)
        self.assertEqual([True, False], seen)

    def test_keyboard_and_animation(self) -> None:
        row = SwitchRow("标题", checked=False)
        row.show()
        row.switch.setFocus()
        QTest.keyClick(row.switch, Qt.Key.Key_Space)
        self.assertTrue(row.isChecked())
        self.assertEqual(150, row.switch._anim.duration())
        QTest.qWait(180)
        self.assertAlmostEqual(1.0, row.switch.knob)


class AnimatedSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_click_toggles(self) -> None:
        w = AnimatedSwitch()
        w.show()
        QTest.mouseClick(w, Qt.MouseButton.LeftButton)
        self.assertTrue(w.isChecked())
        self.app.processEvents()
        QTest.qWait(180)
        self.assertAlmostEqual(1.0, w.knob)

    def test_keyboard_space_and_enter(self) -> None:
        w = AnimatedSwitch()
        w.show()
        w.setFocus()
        QTest.keyClick(w, Qt.Key.Key_Space)
        self.assertTrue(w.isChecked())
        QTest.keyClick(w, Qt.Key.Key_Return)
        self.assertFalse(w.isChecked())

    def test_animation_duration_and_endpoint(self) -> None:
        w = AnimatedSwitch()
        self.assertEqual(150, w._anim.duration())
        w.setChecked(True)
        self.assertNotAlmostEqual(1.0, w.knob)
        QTest.qWait(180)
        self.assertAlmostEqual(1.0, w.knob)
        w.setChecked(False)
        QTest.qWait(180)
        self.assertAlmostEqual(0.0, w.knob)

    def test_disabled_ignores_click(self) -> None:
        w = AnimatedSwitch()
        w.setEnabled(False)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton)
        self.assertFalse(w.isChecked())


@unittest.skipUnless(HAS_QML, "QtQuick QML 不可用")
class SwitchConfigSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_connection_page_config_sync(self) -> None:
        from config import AppConfig
        from ui.settings_pages import ConnectionPage

        page = ConnectionPage(AppConfig(use_mock=False, persist_token=False))
        try:
            page.mock_check.setChecked(True)
            page.save_token_check.setChecked(True)
            cfg = page.result_config()
            self.assertTrue(cfg.use_mock)
            self.assertTrue(cfg.persist_token)
            page.set_config(AppConfig(use_mock=False, persist_token=False))
            self.assertFalse(page.mock_check.isChecked())
            self.assertFalse(page.save_token_check.isChecked())
        finally:
            page.close()
            page.deleteLater()


@unittest.skipUnless(HAS_QML, "QtQuick QML 不可用")
class ToggleSwitchQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _view(self):
        w = QQuickWidget()
        w.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        w.setSource(QUrl.fromLocalFile("ui_qml/components/ToggleSwitch.qml"))
        w.resize(40, 22)
        w.show()
        self.app.processEvents()
        root = w.rootObject()
        self.assertIsNotNone(root, [e.toString() for e in w.errors()])
        return w, root

    def test_checked_and_click(self) -> None:
        w, root = self._view()
        try:
            self.assertFalse(root.property("checked"))
            root.setProperty("checked", True)
            self.assertTrue(root.property("checked"))
            QTest.mouseClick(w, Qt.MouseButton.LeftButton)
            self.assertFalse(root.property("checked"))
        finally:
            w.close()

    def test_keyboard_space(self) -> None:
        w, root = self._view()
        try:
            w.setFocus()
            QTest.keyClick(w, Qt.Key.Key_Space)
            self.assertTrue(root.property("checked"))
        finally:
            w.close()
