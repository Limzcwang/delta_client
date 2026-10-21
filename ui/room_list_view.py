"""房间大厅：公共房间列表 + 创建/加入/退出入口（F：5s 自动刷新按 id diff 更新）。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Room
from core.room_list import room_key
from ui.my_rooms_view import MyRoomsView



class _RoomRowDelegate(QStyledItemDelegate):
    """选中行：16% 琥珀底 + 仅首列 3px 左竖条（无列分隔线）。"""

    def paint(self, painter, option, index) -> None:  # noqa: N802
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        # 房间列表不要 hover 变色；鼠标状态一律清掉，选中态保留。
        opt.state &= ~QStyle.StateFlag.State_MouseOver
        if selected:
            opt.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus)
            opt.showDecorationSelected = False
        super().paint(painter, opt, index)
        if selected and index.column() == 0:
            painter.fillRect(
                QRect(option.rect.left(), option.rect.top() + 1, 3, option.rect.height() - 2),
                QColor("#f5a800"),
            )


class _LobbyTabs(QWidget):
    """自定义文件夹 Tab（QPushButton+QStackedWidget），避免 Fusion TabBar 白基线。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._buttons: list[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(2)
        bar.addStretch(1)
        self._bar_layout = bar
        root.addLayout(bar)
        separator = QFrame()
        separator.setObjectName("TabSeparator")
        separator.setFixedHeight(1)
        root.addWidget(separator)
        root.addWidget(self._stack, 1)

    def addTab(self, widget: QWidget, label: str) -> int:
        index = self._stack.addWidget(widget)
        button = QPushButton(label)
        button.setObjectName("LobbyTab")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group.addButton(button, index)
        button.clicked.connect(lambda _checked=False, i=index: self.setCurrentIndex(i))
        # 插到 stretch 前面
        self._bar_layout.insertWidget(self._bar_layout.count() - 1, button)
        self._buttons.append(button)
        self._labels.append(label)
        if index == 0:
            self.setCurrentIndex(0)
        return index

    def count(self) -> int:
        return len(self._labels)

    def tabText(self, index: int) -> str:
        return self._labels[index] if 0 <= index < len(self._labels) else ""

    def setTabText(self, index: int, text: str) -> None:
        if 0 <= index < len(self._labels):
            self._labels[index] = str(text)
            self._buttons[index].setText(str(text))

    def currentIndex(self) -> int:
        return self._stack.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        if not (0 <= index < len(self._labels)):
            return
        self._stack.setCurrentIndex(index)
        self._buttons[index].setChecked(True)

    def widget(self, index: int) -> QWidget | None:
        return self._stack.widget(index)


_ROOM_TYPES = ("常规", "机密", "绝密")


def room_type_label(room: Room) -> str:
    """从接口字段/房间名提取设计稿房间类型；无可识别类型返回空串。"""
    raw = getattr(room, "raw", {}) or {}
    for key in ("mode", "room_mode", "type", "room_type", "difficulty", "game_mode"):
        value = str(raw.get(key) or "").strip()
        if value in _ROOM_TYPES:
            return value
    name = str(getattr(room, "name", "") or "")
    for value in _ROOM_TYPES:
        if value in name:
            return value
    return ""


class RoomListView(QWidget):
    refresh_requested = Signal()
    create_requested = Signal()
    join_requested = Signal(str)  # 房间号，空字符串表示让用户自己输入
    logout_requested = Signal()
    settings_requested = Signal()
    profile_requested = Signal()

    COLUMNS = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rooms: list[Room] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 18, 26, 14)
        root.setSpacing(14)

        # 表头：标题/副标题 + LIVE + 用户 + 连接设置/个人资料
        header = QHBoxLayout()
        header.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        title = QLabel("房间大厅")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel("选择公共房间，或用房间号加入私有房间")
        self.subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.mode_badge = QLabel("LIVE")
        self.mode_badge.setObjectName("BadgeLive")
        header.addWidget(self.mode_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.user_label = QLabel("当前用户：-")
        self.user_label.setObjectName("Muted")
        header.addWidget(self.user_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        sep = QFrame()
        sep.setObjectName("VSeparator")
        sep.setFixedWidth(1)
        sep.setFixedHeight(22)
        header.addWidget(sep)
        self.settings_button = QPushButton("连接设置")
        self.settings_button.setObjectName("Ghost")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        self.profile_button = QPushButton("个人资料")
        self.profile_button.setObjectName("Outline")
        self.profile_button.clicked.connect(self.profile_requested.emit)
        header.addWidget(self.settings_button)
        header.addWidget(self.profile_button)
        root.addLayout(header)

        # 工具栏
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.refresh_button = QPushButton("刷新列表")
        self.refresh_button.setObjectName("Ghost")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.create_button = QPushButton("创建房间")
        self.create_button.setObjectName("Primary")
        self.create_button.clicked.connect(self.create_requested.emit)
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.create_button)
        actions.addStretch(1)
        # 保留旧入口但不进入新视觉布局（加入改为双击行）
        self.join_button = QPushButton("加入房间")
        self.join_button.clicked.connect(self._emit_join)
        self.join_button.hide()
        self.logout_button = QPushButton("退出登录")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.logout_button.hide()
        root.addLayout(actions)

        self.table = QTableWidget(0, self.COLUMNS)
        self.table.setHorizontalHeaderLabels(["房间号", "房间名", "人数", "类型"])
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.horizontalHeader().setFixedHeight(42)
        for column in (2, 3):
            item = self.table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 80)
        self.table.setMinimumHeight(380)
        self.table.setMaximumHeight(380)
        self.table.setItemDelegate(_RoomRowDelegate(self.table))
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.cellDoubleClicked.connect(self._on_double_click)

        self.public_tab = QWidget()
        public_layout = QVBoxLayout(self.public_tab)
        public_layout.setContentsMargins(0, 0, 0, 0)
        public_layout.addWidget(self.table)
        self.my_rooms = MyRoomsView()
        self.tabs = _LobbyTabs()
        self.tabs.addTab(self.public_tab, "公共房间")
        self.tabs.addTab(self.my_rooms, "我的房间")
        root.addWidget(self.tabs, stretch=0)
        root.addStretch(1)

        # 底部状态统一由 MainWindow.statusBar 展示，页面内不重复。

        self.status_label = QLabel("尚未加载房间")
        self.status_label.setObjectName("Muted")
        self.status_label.hide()
        self.auto_hint = QLabel("")
        self.auto_hint.hide()
        self.note_label = QLabel("")
        self.note_label.hide()

    # ---------- 对外 ----------
    def set_user(self, display_name: str) -> None:
        """F：展示昵称（账号只在个人资料页对自己可见）。"""
        self.user_label.setText(f"当前用户：{display_name or '-'}")

    def set_mode(self, is_mock: bool, server_url: str) -> None:
        self.mode_badge.setText("MOCK" if is_mock else "LIVE")
        self.mode_badge.setObjectName("BadgeMock" if is_mock else "BadgeLive")
        self._repolish(self.mode_badge)
        mode_note = "内置演示后端（不联网）" if is_mock else server_url
        self.subtitle.setText(f"服务器：{mode_note}  ·  双击行可直接加入")

    def set_auto_refresh_hint(self, text: str) -> None:
        self.auto_hint.setText(str(text))

    def update_rooms(self, rooms: list[Room]) -> None:
        """F-c3：按 room_key diff 更新；保留选中行与滚动位置，不整页重建。"""
        selected_key = self._selected_key()
        scroll_value = self.table.verticalScrollBar().value()
        desired = list(rooms)
        desired_keys = [room_key(room) for room in desired]

        # 1) 删除已不存在的行（从下往上，避免索引漂移）
        row = 0
        while row < self.table.rowCount():
            key = self._row_key(row)
            if not key or key not in desired_keys:
                self.table.removeRow(row)
            else:
                row += 1

        # 2) 按新顺序就地更新/插入
        for index, room in enumerate(desired):
            key = room_key(room)
            current = self._find_row(key)
            if current is None:
                self.table.insertRow(index)
                self._write_row(index, room)
            else:
                if current != index:
                    items = [self.table.takeItem(current, column) for column in range(self.COLUMNS)]
                    self.table.removeRow(current)
                    self.table.insertRow(index)
                    for column, item in enumerate(items):
                        if item is not None:
                            self.table.setItem(index, column, item)
                self._write_row(index, room)

        # 3) 清理多余行（理论上步骤 1/2 已对齐）
        while self.table.rowCount() > len(desired):
            self.table.removeRow(self.table.rowCount() - 1)

        self._rooms = desired
        if not desired:
            self.status_label.setText("暂无公开房间，点「创建房间」开一个吧")

        # 4) 恢复选中与滚动位置
        if selected_key:
            row = self._find_row(selected_key)
            if row is not None:
                self.table.selectRow(row)
        self.table.verticalScrollBar().setValue(min(scroll_value, self.table.verticalScrollBar().maximum()))

    def set_rooms(self, rooms: list[Room]) -> None:
        """兼容旧调用（首次加载也走 diff，不会整页重建）。"""
        self.update_rooms(rooms)

    def set_loading(self, loading: bool) -> None:
        self.refresh_button.setEnabled(not loading)
        self.join_button.setEnabled(not loading)
        self.create_button.setEnabled(not loading)

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(str(text))
        self.status_label.setStyleSheet("color: #ff9b8f;" if error else "")

    def set_login_status(self, text: str) -> None:
        """兼容旧调用：状态统一由主窗口状态栏展示。"""

    def set_server_status(self, text: str) -> None:
        """兼容旧调用：状态统一由主窗口状态栏展示。"""

    def selected_code(self) -> str:
        row = self.table.currentRow()
        if 0 <= row < len(self._rooms):
            return self._rooms[row].code
        return ""

    # ---------- 内部 ----------
    def _row_key(self, row: int) -> str:
        item = self.table.item(row, 0)
        if item is None:
            return ""
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data else ""

    def _find_row(self, key: str) -> int | None:
        for row in range(self.table.rowCount()):
            if self._row_key(row) == key:
                return row
        return None

    def _selected_key(self) -> str:
        row = self.table.currentRow()
        if 0 <= row < self.table.rowCount():
            return self._row_key(row)
        return ""

    def _write_row(self, row: int, room: Room) -> None:
        values = [
            room.code or "-",
            (room.display_name + (f" · {room_type_label(room)}" if room_type_label(room) else "")),
            str(room.member_count),
            "私有" if room.has_password else "公开",
        ]
        for column, text in enumerate(values):
            item = self.table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, column, item)
            item.setText(text)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, room_key(room))
            if column in (0, 2, 3):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _emit_join(self) -> None:
        self.join_requested.emit(self.selected_code())

    def _on_double_click(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._rooms):
            self.join_requested.emit(self._rooms[row].code)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
