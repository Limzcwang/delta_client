"""H1：QML 登录页 + 历史账号列表宿主。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui_qml.bridge import LoginBridge


class QmlLoginView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base = Path(__file__).resolve().parent
        self.bridge = LoginBridge()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.quick = QQuickWidget()
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        engine = self.quick.engine()
        engine.addImportPath(str(self._base))
        engine.rootContext().setContextProperty("loginApi", self.bridge)
        engine.rootContext().setContextProperty("historyModel", self.bridge.history_model)
        self.quick.setSource(QUrl.fromLocalFile(str(self._base / "pages" / "LoginPage.qml")))
        root = self.quick.rootObject()
        if root is None:
            raise RuntimeError("QML 登录页加载失败：" + "; ".join(e.toString() for e in self.quick.errors()))
        self.root = root
        layout.addWidget(self.quick)

    def set_saved_logins(self, entries) -> None:
        self.bridge.set_entries(entries)

    def apply_saved_login(self, username: str, password: str, *, expired: bool = False) -> None:
        self.bridge.apply_saved_login(username, password, expired=expired)

    def set_busy(self, busy: bool) -> None:
        self.bridge.set_busy(busy)

    def show_error(self, text: str) -> None:
        self.bridge.set_error(text)

    def show_success(self, text: str) -> None:
        self.bridge.show_success(text)

    def set_mode(self, mode: str) -> None:
        while self.bridge.registerMode != (mode == "register"):
            self.bridge.toggle_mode()

    def set_server_text(self, server_url: str, mode_label: str) -> None:
        pass

    def focus_first(self) -> None:
        pass

    def shutdown(self) -> None:
        try:
            self.quick.setSource(QUrl())
        except RuntimeError:
            pass
