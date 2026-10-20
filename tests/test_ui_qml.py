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

    def test_lobby_model_bindings_100_rows(self) -> None:
        try:
            from ui_qml.host import QmlLobbyView
            from core.models import Room
        except Exception:  # noqa: BLE001
            self.skipTest("QtQuick QML 不可用")
        try:
            view = QmlLobbyView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        rooms = [
            Room.from_api({"id": f"r{i}", "code": f"R{i:04d}", "name": f"房间 {i}", "member_count": i % 8 + 1, "has_password": i % 3 == 0})
            for i in range(100)
        ]
        try:
            view.set_rooms(rooms)
            view.resize(1120, 720)
            view.show()
            self.app.processEvents()
            self.assertEqual(100, view.bridge.public_model.rowCount())
            self.assertEqual("R0000", view.bridge.selectedCode)
        finally:
            view.close()
            view.deleteLater()

    def test_login_history_bridge(self) -> None:
        try:
            from ui_qml.login_host import QmlLoginView
            from state.saved_logins import SavedLoginInfo
        except Exception:  # noqa: BLE001
            self.skipTest("QtQuick QML 不可用")
        try:
            view = QmlLoginView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        try:
            view.set_saved_logins([
                SavedLoginInfo("alpha", 1, 2, 1, True, False),
                SavedLoginInfo("a" * 60, 1, 2, 1, False, False),
            ])
            self.assertEqual(2, view.bridge.history_model.rowCount())
            self.assertEqual(2, len(view.bridge.historyEntries))
            view.bridge.toggle_history()
            self.assertTrue(view.bridge.historyVisible)
        finally:
            view.close()
            view.deleteLater()

    def test_cli_flag_accepts_qml_lobby(self) -> None:
        from main import build_parser

        self.assertEqual("qml-lobby", build_parser().parse_args(["--ui", "qml-lobby"]).ui)
        self.assertEqual("widgets", build_parser().parse_args([]).ui)
        self.assertEqual("qml", build_parser().parse_args(["--ui", "qml"]).ui)


if __name__ == "__main__":
    unittest.main()
