"""房间内页面：成员列表 + 聊天（本地回显/WS）+ 画板占位（C2 不实现）。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.chat import STATUS_FAILED, STATUS_PENDING, ChatEntry
from core.models import Member, Room
from ui.canvas_view import CanvasView
from ui.skill_panel import SkillPanel


class RoomView(QWidget):
    leave_requested = Signal()
    chat_submitted = Signal(str)
    history_requested = Signal()
    retry_requested = Signal(str)  # client_msg_id
    room_settings_requested = Signal()
    kick_requested = Signal(str, str)  # (user_id, nickname)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._username = ""
        self._user_id = ""
        self._room: Room | None = None
        self._members: list[Member] = []
        self._owner_id = ""
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 16)
        root.setSpacing(12)

        # 顶部信息栏
        top = QHBoxLayout()
        top.setSpacing(12)
        self.leave_button = QPushButton("← 离开房间")
        self.leave_button.clicked.connect(self.leave_requested.emit)
        top.addWidget(self.leave_button)

        self.room_name = QLabel("房间")
        self.room_name.setObjectName("PageTitle")
        self.room_code = QLabel("")
        self.room_code.setObjectName("Muted")
        top.addWidget(self.room_name)
        top.addWidget(self.room_code)
        self.copy_button = QPushButton("复制房间号")
        self.copy_button.setObjectName("Link")
        self.copy_button.clicked.connect(self._copy_code)
        top.addWidget(self.copy_button)

        # F：仅房主可见
        self.room_settings_button = QPushButton("房间设置")
        self.room_settings_button.setObjectName("Link")
        self.room_settings_button.clicked.connect(self.room_settings_requested.emit)
        self.room_settings_button.hide()
        top.addWidget(self.room_settings_button)

        self.owner_label = QLabel("")
        self.owner_label.setObjectName("Hint")
        top.addWidget(self.owner_label)

        top.addStretch(1)
        self.connection_badge = QLabel("○ 离线")
        self.connection_badge.setObjectName("ConnOffline")
        self.connection_badge.setToolTip("WebSocket 实时连接状态")
        top.addWidget(self.connection_badge)
        root.addLayout(top)

        # 主体：成员 | 聊天 | 画板/技能（画板优先扩张）
        body = QHBoxLayout()
        body.setSpacing(12)
        self.members_panel = self._build_members_panel()
        self.chat_panel = self._build_chat_panel()
        self.side_tabs = self._build_side_panel()
        body.addWidget(self.members_panel, stretch=0)
        body.addWidget(self.chat_panel, stretch=0)
        body.addWidget(self.side_tabs, stretch=1)
        root.addLayout(body, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        root.addWidget(self.status_label)

    def _build_members_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(190)
        panel.setMaximumWidth(260)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.members_title = QLabel("成员 (0)")
        self.members_title.setObjectName("SectionTitle")
        layout.addWidget(self.members_title)

        self.member_list = QListWidget()
        self.member_list.setObjectName("MemberList")
        self.member_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.member_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.member_list.setWordWrap(False)
        self.member_list.setSpacing(1)
        self.member_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.member_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.member_list.customContextMenuRequested.connect(self._show_member_menu)
        layout.addWidget(self.member_list, stretch=1)

        hint = QLabel("成员优先来自 WS room_joined；WS 丢失时用 HTTP 房间详情兜底")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return panel

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(480)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("聊天")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.chat_list = QListWidget()
        self.chat_list.setWordWrap(True)
        self.chat_list.itemDoubleClicked.connect(self._on_chat_double_clicked)
        self.chat_list.verticalScrollBar().valueChanged.connect(self._on_chat_scrolled)
        layout.addWidget(self.chat_list, stretch=1)

        hint = QLabel("向上滚动加载更早消息；发送失败的消息双击可重试")
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入消息，Enter 发送（1-2000 字）")
        self.chat_input.returnPressed.connect(self._emit_chat)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self._emit_chat)
        input_row.addWidget(self.chat_input, stretch=1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)
        return panel

    def _build_side_panel(self) -> QWidget:
        self.side_tabs = QTabWidget()
        self.side_tabs.setMinimumWidth(400)
        self.side_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas_panel = self._build_canvas_panel()
        self.skill_panel = SkillPanel()
        self.side_tabs.addTab(self.canvas_panel, "画板")
        self.side_tabs.addTab(self.skill_panel, "技能")
        return self.side_tabs

    def _build_canvas_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.canvas = CanvasView()
        layout.addWidget(self.canvas, stretch=1)

        note = QLabel("截屏与识别只会在本机进行")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    # ---------- 对外 ----------
    def set_room(self, room: Room) -> None:
        self._room = room
        self._owner_id = room.owner_id
        self.room_name.setText(room.display_name)
        self.room_code.setText(f"房间号 {room.code}" if room.code else "")
        if self._members:
            self._render_members()
        self._refresh_owner_controls()

    def set_user(self, display_name: str, user_id: str = "") -> None:
        """F：房间内展示昵称；user_id 用于房主/自己标识。"""
        self._username = display_name
        if user_id:
            self._user_id = str(user_id)
        if self._members:
            self._render_members()
        self._refresh_owner_controls()

    def set_members(self, members: list[Member]) -> None:
        self._members = list(members)
        self._render_members()

    def add_member(self, member: Member) -> None:
        if any(existing.id == member.id and existing.username == member.username for existing in self._members):
            return
        self._members.append(member)
        self._render_members()

    def update_member(self, user_id: str, nickname: str) -> None:
        """F：本地修改昵称后立即更新成员列表展示。"""
        changed = False
        for index, member in enumerate(list(self._members)):
            if str(member.id) == str(user_id):
                self._members[index] = replace(member, nickname=nickname)
                changed = True
        if changed:
            self.set_members(self._members)

    def remove_member(self, member: Member) -> None:
        for index, existing in enumerate(list(self._members)):
            if existing.id == member.id or (member.username and existing.username == member.username):
                self._members.pop(index)
                break
        self._render_members()

    def set_connection_state(self, state: str, detail: str = "") -> None:
        mapping = {
            "connected": ("● 已连接", "ConnConnected"),
            "connecting": ("◌ 连接中…", "ConnPending"),
            "authenticating": ("◌ 认证中…", "ConnPending"),
            "waiting": ("◌ 等待重连…", "ConnPending"),
            "reconnecting": ("◌ 重连中…", "ConnPending"),
            "auth_error": ("● 认证失败", "ConnError"),
            "error": ("● 连接失败", "ConnError"),
            "stopped": ("○ 已断开", "ConnOffline"),
            "offline": ("○ 离线（本地回显）", "ConnOffline"),
        }
        text, object_name = mapping.get(state, ("○ 未知状态", "ConnOffline"))
        self.connection_badge.setText(text)
        self.connection_badge.setObjectName(object_name)
        self.connection_badge.setToolTip(detail or text)
        style = self.connection_badge.style()
        style.unpolish(self.connection_badge)
        style.polish(self.connection_badge)

    def set_chat_entries(self, entries: list[ChatEntry], *, stick_to_bottom: bool = False) -> None:
        """按时间线整体渲染聊天列表（保持滚动位置/吸底）。"""
        bar = self.chat_list.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        old_value, old_max = bar.value(), bar.maximum()

        self.chat_list.clear()
        for entry in entries:
            item = QListWidgetItem(entry.display_text())
            item.setToolTip(entry.display_text())
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"client_msg_id": entry.client_msg_id, "status": entry.status},
            )
            if entry.system:
                item.setForeground(QColor("#8b98a8"))
            elif entry.status == STATUS_FAILED:
                item.setForeground(QColor("#ff7b6b"))
            elif entry.status == STATUS_PENDING:
                item.setForeground(QColor("#aebbc9"))
            elif entry.outgoing or (self._username and entry.sender_name == self._username):
                item.setForeground(QColor("#ffd071"))
            self.chat_list.addItem(item)

        if stick_to_bottom or at_bottom:
            QTimer.singleShot(0, self.chat_list.scrollToBottom)
        elif old_value > 0:
            # 历史插入头部后保持视口位置
            bar.setValue(min(old_value + (bar.maximum() - old_max), bar.maximum()))

    def clear_chat(self) -> None:
        self.chat_list.clear()

    def append_chat_input(self, text: str) -> None:
        """恢复输入框内容（发送失败重试用）。"""
        if not self.chat_input.text().strip():
            self.chat_input.setText(text)

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(str(text))
        self.status_label.setStyleSheet("color: #ff9b8f;" if error else "")

    def focus_chat_input(self) -> None:
        self.chat_input.setFocus()

    # ---------- 内部 ----------
    def _on_chat_scrolled(self, value: int) -> None:
        if value == 0 and self.chat_list.count() > 0:
            self.history_requested.emit()

    def _on_chat_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        if data.get("status") == STATUS_FAILED and data.get("client_msg_id"):
            self.retry_requested.emit(str(data["client_msg_id"]))

    def _render_members(self) -> None:
        self.member_list.clear()
        for member in self._members:
            marker = "●" if member.online else "○"
            suffixes = []
            is_owner_member = bool(
                self._owner_id and str(member.id) == str(self._owner_id)
            )
            is_self = bool(self._user_id and str(member.id) == str(self._user_id))
            if is_owner_member:
                suffixes.append("房主")
            if is_self:
                suffixes.append("我")
            suffix = f"  [{'/'.join(suffixes)}]" if suffixes else ""
            text = f"{marker}  {member.display_name}{suffix}"
            item = QListWidgetItem(text)
            # 固定行高 + 右侧省略：长昵称不再撑宽/挤压；40px 保证文字可见
            item.setSizeHint(QSize(0, 40))
            item.setToolTip(f"{member.display_name}{suffix}")
            if is_owner_member:
                item.setForeground(QColor("#ffb61f"))
            else:
                item.setForeground(QColor("#6fdc8c" if member.online else "#778696"))
            item.setData(
                Qt.ItemDataRole.UserRole,
                {"id": str(member.id), "nickname": member.display_name},
            )
            self.member_list.addItem(item)
        self.members_title.setText(f"成员 ({len(self._members)})")
        self._refresh_owner_controls()

    def _is_current_owner(self) -> bool:
        return bool(
            self._user_id and self._owner_id and str(self._user_id) == str(self._owner_id)
        )

    def _target_is_self(self, user_id: str) -> bool:
        return bool(self._user_id and str(user_id) == str(self._user_id))

    def build_member_menu(self, item: QListWidgetItem) -> QMenu:
        """H3：成员行右键菜单；当前只有「移出房间」（无行内按钮）。"""
        data = item.data(Qt.ItemDataRole.UserRole) or {}
        user_id = str(data.get("id") or "")
        nickname = str(data.get("nickname") or "")
        menu = QMenu(self)
        action = menu.addAction("移出房间")
        enabled = bool(
            self._is_current_owner()
            and user_id
            and not self._target_is_self(user_id)
            and user_id != str(self._owner_id)
        )
        action.setEnabled(enabled)
        action.setToolTip("仅房主可移出其他成员" if not enabled else "")
        action.triggered.connect(
            lambda _checked=False, uid=user_id, name=nickname: self.kick_requested.emit(uid, name)
        )
        return menu

    def _show_member_menu(self, pos) -> None:  # noqa: ANN001 - Qt QPoint
        item = self.member_list.itemAt(pos)
        if item is None:
            return
        menu = self.build_member_menu(item)
        menu.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        menu.exec(self.member_list.viewport().mapToGlobal(pos))
        menu.deleteLater()
        # 菜单关闭后不把焦点留在成员列表/菜单上
        self.member_list.clearFocus()

    def _refresh_owner_controls(self) -> None:
        """F：房主标识 + 仅房主显示「房间设置」。"""
        owner_member = next(
            (member for member in self._members if str(member.id) == str(self._owner_id)),
            None,
        )
        if owner_member is not None:
            self.owner_label.setText(f"房主：{owner_member.display_name}")
        elif self._owner_id:
            self.owner_label.setText("")
        is_owner = bool(self._user_id and self._owner_id and str(self._user_id) == str(self._owner_id))
        self.room_settings_button.setVisible(is_owner)

    def _emit_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self.chat_submitted.emit(text)

    def _copy_code(self) -> None:
        if self._room is not None and self._room.code:
            QApplication.clipboard().setText(self._room.code)
            self.set_status(f"已复制房间号 {self._room.code}")
