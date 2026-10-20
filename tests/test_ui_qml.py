"""H0：QQuickWidget QML 大厅加载 smoke。"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

try:
    from PySide6.QtWidgets import QApplication

    from ui_qml.host import QmlLobbyView

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6/QtQuick 未安装")
class QmlLobbySmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qml_lobby_loads(self) -> None:
        try:
            view = QmlLobbyView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        try:
            view.resize(1120, 720)
            view.show()
            self.app.processEvents()
            self.assertIsNotNone(view.root)
            self.assertGreaterEqual(view.root.width(), 100)
            self.assertGreaterEqual(view.root.height(), 100)
            self.app.processEvents()
        finally:
            view.close()
            view.deleteLater()

    def test_cli_flag_accepts_qml_lobby(self) -> None:
        from main import build_parser

        self.assertEqual("qml-lobby", build_parser().parse_args(["--ui", "qml-lobby"]).ui)
        self.assertEqual("widgets", build_parser().parse_args([]).ui)


if __name__ == "__main__":
    unittest.main()
