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

    def test_qml_settings_pages_load(self) -> None:
        try:
            from ui_qml.settings_host import QmlConnView, QmlProfileView
        except Exception:  # noqa: BLE001
            self.skipTest("QtQuick QML 不可用")
        try:
            conn = QmlConnView()
            profile = QmlProfileView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        try:
            conn.resize(1120, 720)
            profile.resize(1120, 720)
            self.assertIsNotNone(conn.root)
            self.assertIsNotNone(profile.root)
            profile.root.setProperty("passwordExpanded", True)
            self.assertTrue(profile.root.property("passwordExpanded"))
        finally:
            conn.close()
            profile.close()
            conn.deleteLater()
            profile.deleteLater()

    def test_conn_bridge_config_binding(self) -> None:
        try:
            from ui_qml.settings_host import QmlConnView
            from config import AppConfig
        except Exception:  # noqa: BLE001
            self.skipTest("QtQuick QML 不可用")
        try:
            view = QmlConnView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        try:
            cfg = AppConfig(server_url="https://example.test:9443", ws_url="wss://example.test/ws", use_mock=True, persist_token=True)
            view.set_config(cfg)
            self.assertEqual("https://example.test:9443", view.bridge.server)
            self.assertEqual("wss://example.test/ws", view.bridge.ws)
            self.assertTrue(view.bridge.useMock)
            self.assertTrue(view.bridge.saveToken)
            view.bridge.server = "http://127.0.0.1:8000"
            self.assertEqual("http://127.0.0.1:8000", view.result_config().server_url)
            view.bridge.set_test_result("✓ 连接成功 118ms", True)
            self.assertIn("成功", view.bridge.resultText)
        finally:
            view.close()
            view.deleteLater()

    def test_profile_bridge_nickname(self) -> None:
        try:
            from ui_qml.settings_host import QmlProfileView
        except Exception:  # noqa: BLE001
            self.skipTest("QtQuick QML 不可用")
        try:
            view = QmlProfileView()
        except RuntimeError as exc:
            self.skipTest(f"QtQuick QML 插件不可用：{exc}")
        try:
            view.set_account("account")
            view.set_nickname("昵称A")
            self.assertEqual("account", view.bridge.account)
            self.assertEqual("昵称A", view.bridge.nickname)
            view.set_nickname_result("昵称已更新", True)
            self.assertEqual("昵称已更新", view.bridge.nicknameResult)
            # 新密码 8-64 位 + 两次一致；不一致时不发请求
            seen = []
            view.bridge.password_requested.connect(lambda old, new: seen.append((old, new)))
            view.bridge.change_password("oldpass1", "newpass1", "newpass2")
            self.assertEqual([], seen)
            self.assertIn("不一致", view.bridge.passwordResult)
        finally:
            view.close()
            view.deleteLater()

    def test_login_bridge_error_and_history(self) -> None:
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
            view.bridge.submit("user", "password")
            self.assertTrue(view.bridge.loading)
            view.bridge.set_error("账号或密码错误")
            self.assertFalse(view.bridge.loading)
            self.assertEqual("账号或密码错误", view.bridge.errorText)
            view.set_saved_logins([SavedLoginInfo("alpha", 1, 2, 1, True, False)])
            view.bridge.toggle_history()
            self.assertTrue(view.bridge.historyVisible)
            view.bridge.clear_history()
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
