"""房间内页面：成员列表 + 聊天（本地回显/WS）+ 画板占位（C2 不实现）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import ChatMessage, Member, Room


class RoomView(QWidget):
    leave_requested = Signal()
    chat_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._username = ""
        self._room: Room | None = None
        self._members: list[Member] = []
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

        top.addStretch(1)
        self.connection_badge = QLabel("○ 离线")
        self.connection_badge.setObjectName("ConnOffline")
        self.connection_badge.setToolTip("WebSocket 实时连接状态")
        top.addWidget(self.connection_badge)
        root.addLayout(top)

        # 主体：成员 | 聊天 | 画板占位
        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_members_panel(), stretch=0)
        body.addWidget(self._build_chat_panel(), stretch=1)
        body.addWidget(self._build_canvas_panel(), stretch=0)
        root.addLayout(body, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("Muted")
        root.addWidget(self.status_label)

    def _build_members_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setFixedWidth(230)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.members_title = QLabel("成员 (0)")
        self.members_title.setObjectName("SectionTitle")
        layout.addWidget(self.members_title)

        self.member_list = QListWidget()
        layout.addWidget(self.member_list, stretch=1)

        hint = QLabel("成员来自 WS room_joined / user_joined（C 阶段完善）")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return panel

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("聊天")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.chat_list = QListWidget()
        self.chat_list.setWordWrap(True)
        layout.addWidget(self.chat_list, stretch=1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入消息，Enter 发送（C1 聊天为回显演示，C 阶段接正式聊天）")
        self.chat_input.returnPressed.connect(self._emit_chat)
        self.send_button = QPushButton("发送")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self._emit_chat)
        input_row.addWidget(self.chat_input, stretch=1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)
        return panel

    def _build_canvas_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setFixedWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("画板协同")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        placeholder = QFrame()
        placeholder.setObjectName("CanvasPlaceholder")
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(16, 16, 16, 16)
        placeholder_layout.setSpacing(8)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("◈")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("color: #4a5c72; font-size: 48px;")
        caption = QLabel("画板协同（C2 占位）")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setObjectName("Muted")
        details = QLabel(
            "逻辑画布 1920×1080\n底图由运营方配置\n\n本轮 C1 不实现绘制、\n不上传任何截图"
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setObjectName("Hint")

        placeholder_layout.addWidget(icon)
        placeholder_layout.addWidget(caption)
        placeholder_layout.addWidget(details)
        layout.addWidget(placeholder, stretch=1)

        note = QLabel("技能 CD 共享（C3）同样是占位，截屏与识别只会在本机进行")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    # ---------- 对外 ----------
    def set_room(self, room: Room) -> None:
        self._room = room
        self.room_name.setText(room.display_name)
        self.room_code.setText(f"房间号 {room.code}" if room.code else "")

    def set_user(self, username: str) -> None:
        self._username = username

    def set_members(self, members: list[Member]) -> None:
        self._members = list(members)
        self.member_list.clear()
        for member in self._members:
            self.member_list.addItem(self._member_item(member))
        self.members_title.setText(f"成员 ({len(self._members)})")

    def add_member(self, member: Member) -> None:
        if any(existing.id == member.id and existing.username == member.username for existing in self._members):
            return
        self._members.append(member)
        self.member_list.addItem(self._member_item(member))
        self.members_title.setText(f"成员 ({len(self._members)})")

    def remove_member(self, member: Member) -> None:
        for index, existing in enumerate(list(self._members)):
            if existing.id == member.id or (member.username and existing.username == member.username):
                self._members.pop(index)
                self.member_list.takeItem(index)
                break
        self.members_title.setText(f"成员 ({len(self._members)})")

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

    def add_chat_message(self, message: ChatMessage) -> None:
        item = QListWidgetItem(message.display_text())
        item.setToolTip(message.display_text())
        if message.system:
            item.setForeground(QColor("#8b98a8"))
        elif self._username and message.sender_name == self._username:
            item.setForeground(QColor("#ffd071"))
        self.chat_list.addItem(item)
        QTimer.singleShot(0, self.chat_list.scrollToBottom)

    def add_system_message(self, text: str) -> None:
        self.add_chat_message(ChatMessage(system=True, content=str(text)))

    def clear_chat(self) -> None:
        self.chat_list.clear()

    def set_status(self, text: str, error: bool = False) -> None:
        self.status_label.setText(str(text))
        self.status_label.setStyleSheet("color: #ff9b8f;" if error else "")

    def focus_chat_input(self) -> None:
        self.chat_input.setFocus()

    # ---------- 内部 ----------
    @staticmethod
    def _member_item(member: Member) -> QListWidgetItem:
        marker = "●" if member.online else "○"
        item = QListWidgetItem(f"{marker}  {member.display_name}")
        item.setForeground(QColor("#6fdc8c" if member.online else "#778696"))
        return item

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
