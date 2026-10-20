"""H2：QML 连接/个人资料页宿主。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget

from config import AppConfig
from ui_qml.settings_bridge import ConnBridge, ProfileBridge


class _QmlPageView(QWidget):
    back_requested = Signal()

    def __init__(self, qml_name: str, bridge, context_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        base = Path(__file__).resolve().parent
        self.engine = QQmlEngine(self)
        self.quick = QQuickWidget(self.engine, self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.engine.addImportPath(str(base))
        self.engine.rootContext().setContextProperty(context_name, bridge)
        self.quick.setSource(QUrl.fromLocalFile(str(base / "pages" / qml_name)))
        root = self.quick.rootObject()
        if root is None:
            raise RuntimeError(f"QML 页面加载失败：{qml_name}：" + "; ".join(e.toString() for e in self.quick.errors()))
        root.backRequested.connect(self.back_requested.emit)
        self.root = root
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.quick)

    def shutdown(self) -> None:
        try:
            self.quick.setSource(QUrl())
        except RuntimeError:
            pass


class QmlConnView(_QmlPageView):
    test_requested = Signal(str, str)
    save_requested = Signal()
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ConnPage.qml", ConnBridge(), "connApi", parent)
        self.bridge.test_requested.connect(self.test_requested.emit)
        self.bridge.save_requested.connect(self.save_requested.emit)
        self.bridge.reset_requested.connect(self.reset_requested.emit)
        self.bridge.back_requested.connect(self.back_requested.emit)
        self._base_config = AppConfig()

    def set_config(self, config: AppConfig) -> None:
        self._base_config = config
        self.bridge.apply_config(config)

    def set_testing(self, testing: bool) -> None:
        self.bridge.set_testing(testing)

    def set_test_result(self, text: str, ok: bool = True) -> None:
        self.bridge.set_test_result(text, ok)

    def set_error(self, text: str) -> None:
        self.bridge.set_test_result(text, False)

    def result_config(self) -> AppConfig:
        return self.bridge.result_config(self._base_config)

    def _sync_error(self) -> None:
        pass


class QmlProfileView(_QmlPageView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ProfilePage.qml", ProfileBridge(), "profileCtl", parent)
        self.nickname_requested = self.bridge.nickname_requested
        self.password_requested = self.bridge.password_requested
        self.logout_requested = self.bridge.logout_requested
        self.bridge.back_requested.connect(self.back_requested.emit)

    def set_account(self, account: str) -> None:
        self.bridge.set_account(account, account)

    def set_nickname(self, nickname: str) -> None:
        self.bridge.nickname = nickname

    def set_nickname_busy(self, busy: bool) -> None:
        self.bridge.set_nickname_busy(busy)

    def set_nickname_result(self, text: str, ok: bool | None = None) -> None:
        self.bridge.set_nickname_result(text, ok)

    def set_password_busy(self, busy: bool) -> None:
        self.bridge.set_password_busy(busy)

    def set_password_result(self, text: str, ok: bool | None = None) -> None:
        self.bridge.set_password_result(text, ok)
