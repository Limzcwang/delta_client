"""H0：用 QQuickWidget 在 Widgets 主窗口中承载 QML 大厅页。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtQml import QQmlEngine, qmlRegisterSingletonType
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ui_qml.bridge import LobbyBridge

_CURRENT_LOBBY_BRIDGE: LobbyBridge | None = None
_LOBBY_SINGLETON_REGISTERED = False


def _lobby_singleton(_engine):
    return _CURRENT_LOBBY_BRIDGE


class QmlLobbyView(QWidget):
    """QML 大厅页宿主；数据为静态 mock，仅用于 H0 视觉/性能对比。"""

    refresh_requested = Signal()
    create_requested = Signal()
    join_requested = Signal(str)
    settings_requested = Signal()
    profile_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base = Path(__file__).resolve().parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        global _CURRENT_LOBBY_BRIDGE, _LOBBY_SINGLETON_REGISTERED
        self.bridge = LobbyBridge()
        _CURRENT_LOBBY_BRIDGE = self.bridge
        self.bridge.refresh_requested.connect(self.refresh_requested.emit)
        self.bridge.create_requested.connect(self.create_requested.emit)
        self.bridge.join_requested.connect(self.join_requested.emit)
        self.bridge.settings_requested.connect(self.settings_requested.emit)
        self.bridge.profile_requested.connect(self.profile_requested.emit)
        self.engine = QQmlEngine(self)
        self.quick = QQuickWidget(self.engine, self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.setClearColor(Qt.GlobalColor.transparent)
        engine = self.engine
        engine.addImportPath(str(self._base))
        engine.rootContext().setContextProperty("lobbyApi", self.bridge)
        engine.rootContext().setContextProperty("roomsModel", self.bridge.public_model)
        engine.rootContext().setContextProperty("myRoomsModel", self.bridge.my_model)
        source = self._base / "pages" / "LobbyPage.qml"
        self.quick.setSource(QUrl.fromLocalFile(str(source)))
        root = self.quick.rootObject()
        if root is None:
            errors = "; ".join(error.toString() for error in self.quick.errors())
            raise RuntimeError(f"QML 大厅加载失败：{errors}")
        self.root = root
        layout.addWidget(self.quick)

    def set_user(self, display_name: str) -> None:
        self.bridge.set_user(display_name)

    def set_mode(self, is_mock: bool, server_url: str) -> None:
        self.bridge.set_mode(is_mock, server_url)

    def set_status(self, text: str) -> None:
        self.bridge.set_status(text)

    def set_rooms(self, rooms) -> None:
        self.bridge.public_model.set_rooms(rooms)
        if rooms and not self.bridge.selectedCode:
            first = str(getattr(rooms[0], "code", "") or "")
            if first:
                self.bridge.select_room(first)

    def set_my_rooms(self, rooms) -> None:
        self.bridge.my_model.set_rooms(rooms)

    def shutdown(self) -> None:
        try:
            self.quick.setSource(QUrl())
        except RuntimeError:
            pass


__all__ = ["QmlLobbyView"]
