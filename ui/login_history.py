"""登录页历史账号下拉弹层（非模态 popup）。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from state.saved_logins import SavedLoginInfo

ROW_HEIGHT = 38
MAX_VISIBLE_ROWS = 5
MAX_WIDTH = 420


class ElidedLabel(QLabel):
    """中间省略的完整账号标签；tooltip 保留全称。"""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.full_text = str(text)
        self.setToolTip(self.full_text)
        self.setMinimumWidth(0)
        self.setText(self.full_text)

    def _update_elide(self) -> None:
        width = max(24, self.width())
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        self._update_elide()

    def set_full_text(self, text: str) -> None:
        self.full_text = str(text)
        self.setToolTip(self.full_text)
        self._update_elide()


class HistoryRow(QWidget):
    """单条历史账号：账号 / 最近登录 / 锁标记 / 删除。"""

    row_clicked = Signal(str)

    def __init__(self, entry: SavedLoginInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("HistoryRow")
        self.setFixedHeight(ROW_HEIGHT)
        self.setMinimumHeight(ROW_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)
        layout.setSpacing(8)
        self.account_label = ElidedLabel(entry.username)
        self.account_label.setObjectName("HistoryAccount")
        self.account_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.time_label = QLabel(entry.last_used_text)
        self.time_label.setObjectName("HistoryTime")
        self.time_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lock_label = QLabel("🔒" if entry.has_password else "")
        self.lock_label.setObjectName("HistoryLock")
        self.lock_label.setToolTip(entry.status_text)
        self.lock_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.delete_button = QToolButton()
        self.delete_button.setObjectName("HistoryDelete")
        self.delete_button.setText("✕")
        self.delete_button.setToolTip("删除该账号")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.setFixedSize(26, 26)
        layout.addWidget(self.account_label, stretch=1)
        layout.addWidget(self.time_label)
        layout.addWidget(self.lock_label)
        layout.addWidget(self.delete_button)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.row_clicked.emit(self.entry.username)
        super().mousePressEvent(event)


class LoginHistoryPopup(QFrame):
    """输入框下方历史账号列表；Esc/点击外部关闭，键盘可导航。"""

    selected = Signal(str)
    delete_requested = Signal(str)
    clear_requested = Signal()

    def __init__(self, entries: list[SavedLoginInfo], parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("LoginHistoryPopup")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._entries: list[SavedLoginInfo] = []
        self._width = 360
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.list = QListWidget()
        self.list.setObjectName("LoginHistoryList")
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(0)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list.itemClicked.connect(self._on_clicked)
        self.list.itemActivated.connect(self._on_clicked)
        self.list.installEventFilter(self)
        layout.addWidget(self.list)
        self.clear_button = QPushButton("清空历史")
        self.clear_button.setObjectName("HistoryClear")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_button)
        self.set_entries(entries)
        self._sync_height()

    @property
    def entries(self) -> list[SavedLoginInfo]:
        return list(self._entries)

    @property
    def row_height(self) -> int:
        return ROW_HEIGHT

    def set_entries(self, entries: list[SavedLoginInfo]) -> None:
        self._entries = list(entries)
        self.list.clear()
        for entry in self._entries:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, entry.username)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            item.setToolTip(entry.username)
            self.list.addItem(item)
            row = HistoryRow(entry)
            row.row_clicked.connect(self.selected.emit)
            row.delete_button.clicked.connect(
                lambda _checked=False, name=entry.username: self._delete(name)
            )
            self.list.setItemWidget(item, row)
        self._sync_height()
        if self._entries:
            self.list.setCurrentRow(0)

    def set_popup_width(self, width: int) -> None:
        self._width = max(260, min(MAX_WIDTH, int(width)))
        self.setFixedWidth(self._width)
        self.list.setFixedWidth(self._width - 12)

    def _sync_height(self) -> None:
        visible = min(MAX_VISIBLE_ROWS, len(self._entries))
        self.list.setFixedHeight(max(1, visible) * ROW_HEIGHT)
        self.adjustSize()
        if self._entries:
            self.list.setCurrentRow(0)

    def show_for(self, anchor: QWidget) -> None:
        self.set_popup_width(max(anchor.width(), 360))
        self._sync_height()
        point = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            if point.x() + self.width() > available.right():
                point.setX(max(available.left(), available.right() - self.width()))
            if point.y() + self.height() > available.bottom():
                point.setY(max(available.top(), anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 2))
        self.move(point)
        self.show()
        self.raise_()
        self.activateWindow()
        self.list.setFocus()
        if self._entries:
            self.list.setCurrentRow(0)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        username = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if username:
            self.selected.emit(username)
            self.hide()

    def _delete(self, username: str) -> None:
        self.delete_requested.emit(username)
        self._entries = [entry for entry in self._entries if entry.username != username]
        self.set_entries(self._entries)
        if not self._entries:
            self.hide()

    def _on_clear(self) -> None:
        self.clear_requested.emit()
        self.hide()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.list and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list.currentItem()
                if item is not None:
                    self._on_clicked(item)
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
