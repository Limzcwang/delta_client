"""H2：QML 连接/个人资料页宿主。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget


class _QmlPageView(QWidget):
    back_requested = Signal()

    def __init__(self, qml_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        base = Path(__file__).resolve().parent
        self.engine = QQmlEngine(self)
        self.quick = QQuickWidget(self.engine, self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.engine.addImportPath(str(base))
        self.quick.setSource(QUrl.fromLocalFile(str(base / "pages" / qml_name)))
        root = self.quick.rootObject()
        if root is None:
            raise RuntimeError(f"QML 页面加载失败：{qml_name}：" + "; ".join(e.toString() for e in self.quick.errors()))
        root.backRequested.connect(self.back_requested.emit)
        self.root = root
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.quick)


class QmlConnView(_QmlPageView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ConnPage.qml", parent)


class QmlProfileView(_QmlPageView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("ProfilePage.qml", parent)
