"""房间大厅：公共房间列表 + 创建/加入/退出入口。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import Room


class RoomListView(QWidget):
    refresh_requested = Signal()
    create_requested = Signal()
    join_requested = Signal(str)  # 房间号，空字符串表示让用户自己输入
    logout_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rooms: list[Room] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 20)
        root.setSpacing(14)

        # 顶部标题栏
        header = QHBoxLayout()
        header.setSpacing(12)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("房间大厅")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel("选择公共房间，或用房间号加入私有房间")
        self.subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.mode_badge = QLabel("MOCK")
        self.mode_badge.setObjectName("BadgeMock")
        header.addWidget(self.mode_badge, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.user_label = QLabel("当前用户：-")
        self.user_label.setObjectName("Muted")
        header.addWidget(self.user_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        # 操作按钮
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.refresh_button = QPushButton("刷新列表")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.create_button = QPushButton("创建房间")
        self.create_button.setObjectName("Primary")
        self.create_button.clicked.connect(self.create_requested.emit)
        self.join_button = QPushButton("加入房间")
        self.join_button.clicked.connect(self._emit_join)
        self.logout_button = QPushButton("退出登录")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.settings_button = QPushButton("连接设置")
        self.settings_button.setObjectName("Link")
        self.settings_button.clicked.connect(self.settings_requested.emit)

        actions.addWidget(self.refresh_button)
        actions.addWidget(self.create_button)
        actions.addWidget(self.join_button)
        actions.addStretch(1)
        actions.addWidget(self.settings_button)
        actions.addWidget(self.logout_button)
        root.addLayout(actions)

        # 房间表格
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["房间号", "房间名", "人数", "类型"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.table, stretch=1)

        # 底部状态
        footer = QHBoxLayout()
        self.status_label = QLabel("尚未加载房间")
        self.status_label.setObjectName("Muted")
        note = QLabel("私有房间不会出现在公共列表，需要输入 5 位房间号和密码加入")
        note.setObjectName("Hint")
        footer.addWidget(self.status_label, stretch=1)
        footer.addWidget(note)
        root.addLayout(footer)

    # ---------- 对外 ----------
    def set_user(self, username: str) -> None:
        self.user_label.setText(f"当前用户：{username or '-'}")

    def set_mode(self, is_mock: bool, server_url: str) -> None:
        self.mode_badge.setText("MOCK 模式" if is_mock else "LIVE 模式")
        self.mode_badge.setObjectName("BadgeMock" if is_mock else "BadgeLive")
        self._repolish(self.mode_badge)
        mode_note = "内置演示后端（不联网）" if is_mock else server_url
        self.subtitle.setText(f"服务器：{mode_note}  ·  双击行可直接加入")

    def set_rooms(self, rooms: list[Room]) -> None:
        self._rooms = list(rooms)
        self.table.setRowCount(0)
        for row, room in enumerate(self._rooms):
            self.table.insertRow(row)
            values = [
                room.code or "-",
                room.display_name,
                str(room.member_count),
                "🔒 私有" if room.has_password else "公开",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column in (0, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        if not self._rooms:
            self.status_label.setText("暂无公开房间，点「创建房间」开一个吧")

    def set_loading(self, loading: bool) -> None:
        self.refresh_button.setEnabled(not loading)
        self.join_button.setEnabled(not loading)
        self.create_button.setEnabled(not loading)
        if loading:
            self.status_label.setText("正在加载房间列表…")

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(str(text))
        self.status_label.setStyleSheet("color: #ff9b8f;" if error else "")

    def selected_code(self) -> str:
        row = self.table.currentRow()
        if 0 <= row < len(self._rooms):
            return self._rooms[row].code
        return ""

    # ---------- 内部 ----------
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
