"""H1「我的房间」列表：按 room id diff 更新、行内退出/关闭按钮。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import MyRoom

_EMPTY_TEXT = "还没有加入任何房间，去公共房间看看吧"


class MyRoomsView(QWidget):
    """大厅「我的房间」标签页。

    - ``role=owner`` 显示「关闭房间」（走 DELETE，需房名确认）；
    - 其它成员显示「退出」（走 leave）；
    - 刷新按 id diff，不重建整表；正在退出/关闭的行保持禁用状态，不被打断。
    """

    leave_requested = Signal(str)  # room key (id 优先)
    close_requested = Signal(str)

    COLUMNS = 5

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rooms: list[MyRoom] = []
        self._busy: set[str] = set()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(0)

        self.table = QTableWidget(0, self.COLUMNS)
        self.table.setHorizontalHeaderLabels(["房间名", "房间号", "人数", "类型", "操作"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.hide()

        self.empty_label = QLabel(_EMPTY_TEXT)
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)

        root.addWidget(self.table, stretch=1)
        root.addWidget(self.empty_label, stretch=1)

    # ---------- 对外 ----------
    @property
    def rooms(self) -> list[MyRoom]:
        return list(self._rooms)

    def room(self, key: str) -> MyRoom | None:
        for room in self._rooms:
            if room.key == str(key):
                return room
        return None

    def set_rooms(self, rooms: list[MyRoom]) -> None:
        """按 room id diff 更新；保留选中/滚动与正在进行的按钮状态。"""
        selected_key = self._selected_key()
        scroll_value = self.table.verticalScrollBar().value()
        desired = list(rooms)
        desired_keys = [room.key for room in desired]

        row = 0
        while row < self.table.rowCount():
            key = self._row_key(row)
            if not key or key not in desired_keys:
                self.table.removeRow(row)
            else:
                row += 1

        for index, room in enumerate(desired):
            current = self._find_row(room.key)
            if current is None:
                self.table.insertRow(index)
                self._write_row(index, room)
            elif current != index:
                # 顺序变化（少见）：重建此行，其它行保持不动
                self.table.removeRow(current)
                self.table.insertRow(index)
                self._write_row(index, room)
            else:
                self._write_row(index, room)

        while self.table.rowCount() > len(desired):
            self.table.removeRow(self.table.rowCount() - 1)

        self._rooms = desired
        self._sync_empty_state()
        if selected_key:
            row = self._find_row(selected_key)
            if row is not None:
                self.table.selectRow(row)
        self.table.verticalScrollBar().setValue(
            min(scroll_value, self.table.verticalScrollBar().maximum())
        )

    def remove_room(self, key: str) -> None:
        row = self._find_row(str(key))
        if row is not None:
            self.table.removeRow(row)
        self._rooms = [room for room in self._rooms if room.key != str(key)]
        self._busy.discard(str(key))
        self._sync_empty_state()

    def set_room_busy(self, key: str, busy: bool) -> None:
        key = str(key)
        if busy:
            self._busy.add(key)
        else:
            self._busy.discard(key)
        row = self._find_row(key)
        if row is not None:
            button = self.table.cellWidget(row, self.COLUMNS - 1)
            room = self.room(key)
            if isinstance(button, QPushButton) and room is not None:
                self._update_button(button, room)

    # ---------- 内部 ----------
    def _row_key(self, row: int) -> str:
        item = self.table.item(row, 0)
        if item is None:
            return ""
        data = item.data(Qt.ItemDataRole.UserRole)
        return str(data) if data else ""

    def _find_row(self, key: str) -> int | None:
        for row in range(self.table.rowCount()):
            if self._row_key(row) == str(key):
                return row
        return None

    def _selected_key(self) -> str:
        row = self.table.currentRow()
        if 0 <= row < self.table.rowCount():
            return self._row_key(row)
        return ""

    def _write_row(self, row: int, room: MyRoom) -> None:
        values = [
            room.display_name,
            room.code or "-",
            str(room.member_count),
            "🔒 私有" if room.is_private else "公开",
        ]
        for column, text in enumerate(values):
            item = self.table.item(row, column)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, column, item)
            item.setText(text)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, room.key)
            if column in (1, 2, 3):
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        button = self.table.cellWidget(row, self.COLUMNS - 1)
        if not isinstance(button, QPushButton):
            button = QPushButton()
            button.setProperty("room_key", room.key)
            button.clicked.connect(lambda _checked=False, btn=button: self._on_action(btn))
            self.table.setCellWidget(row, self.COLUMNS - 1, button)
        button.setProperty("room_key", room.key)
        self._update_button(button, room)

    def _update_button(self, button: QPushButton, room: MyRoom) -> None:
        busy = room.key in self._busy
        if room.is_owner:
            button.setText("关闭中…" if busy else "关闭房间")
        else:
            button.setText("退出中…" if busy else "退出")
        button.setEnabled(not busy)

    def _on_action(self, button: QPushButton) -> None:
        key = str(button.property("room_key") or "")
        room = self.room(key)
        if room is None or key in self._busy:
            return
        if room.is_owner:
            self.close_requested.emit(key)
        else:
            self.leave_requested.emit(key)

    def _sync_empty_state(self) -> None:
        has_rooms = bool(self._rooms)
        self.table.setVisible(has_rooms)
        self.empty_label.setVisible(not has_rooms)
