"""H0：用 QQuickWidget 在 Widgets 主窗口中承载 QML 大厅页。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget


class QmlLobbyView(QWidget):
    """QML 大厅页宿主；数据为静态 mock，仅用于 H0 视觉/性能对比。"""

    settings_requested = Signal()
    profile_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base = Path(__file__).resolve().parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.quick = QQuickWidget()
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.setClearColor(Qt.GlobalColor.transparent)
        self.quick.engine().addImportPath(str(self._base))
        source = self._base / "pages" / "LobbyPage.qml"
        self.quick.setSource(QUrl.fromLocalFile(str(source)))
        root = self.quick.rootObject()
        if root is None:
            errors = "; ".join(error.toString() for error in self.quick.errors())
            raise RuntimeError(f"QML 大厅加载失败：{errors}")
        self.root = root
        layout.addWidget(self.quick)

    def set_user(self, display_name: str) -> None:
        # H0 静态 mock；后续接入真实数据时通过 QML property 更新。
        pass

    def set_mode(self, is_mock: bool, server_url: str) -> None:
        pass

    def shutdown(self) -> None:
        try:
            self.quick.setSource(QUrl())
        except RuntimeError:
            pass


__all__ = ["QmlLobbyView"]
