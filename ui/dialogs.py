"""对话框：创建房间、加入房间、连接设置。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig, ConfigError, normalize_server_url, normalize_ws_url
from core.models import Room
from core.rooms import ValidationError, validate_room_code, validate_room_name, validate_visibility
from core.rooms import (
    validate_room_delete_confirmation,
    validate_room_name_update,
    validate_room_password,
    validate_room_password_change,
)
from core.validation import validate_nickname, validate_password_change


def _add_buttons(dialog: QDialog, layout: QVBoxLayout, ok_text: str) -> QPushButton:
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("取消")
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("Primary")
    ok.setDefault(True)
    ok.clicked.connect(dialog.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    layout.addSpacing(6)
    layout.addLayout(row)
    return ok


def _error_label(layout: QVBoxLayout) -> QLabel:
    label = QLabel()
    label.setObjectName("ErrorBanner")
    label.setWordWrap(True)
    label.hide()
    layout.addWidget(label)
    return label


class CreateRoomDialog(QDialog):
    """创建房间：名称 + 公开/私有 + 私有密码。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[str, str, str | None] | None = None
        self._build()

    def _build(self) -> None:
        self.setWindowTitle("创建房间")
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)
        heading = QLabel("创建房间")
        heading.setObjectName("PageTitle")
        sub = QLabel("公共房间会出现在大厅；私有房间需凭房间号 + 密码加入")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)
        root.addSpacing(6)

        root.addWidget(QLabel("房间名称"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：开黑上分（缺 1）")
        root.addWidget(self.name_edit)

        root.addWidget(QLabel("可见性"))
        self.public_radio = QRadioButton("公开房间（出现在公共列表）")
        self.private_radio = QRadioButton("私有房间（需要密码加入，不出现在公共列表）")
        self.public_radio.setChecked(True)
        self.public_radio.toggled.connect(self._on_visibility_changed)
        root.addWidget(self.public_radio)
        root.addWidget(self.private_radio)

        self.password_label = QLabel("房间密码")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("私有房间密码（公开房间不需要）")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(self.password_label)
        root.addWidget(self.password_edit)

        self.error_label = _error_label(root)
        _add_buttons(self, root, "创建并进入")
        self._on_visibility_changed()

    def _on_visibility_changed(self, *_args: object) -> None:
        is_private = self.private_radio.isChecked()
        self.password_label.setVisible(is_private)
        self.password_edit.setVisible(is_private)
        self.password_edit.setEnabled(is_private)
        if not is_private:
            self.password_edit.clear()

    def accept(self) -> None:  # noqa: D401 - Qt 覆盖
        self.error_label.hide()
        try:
            name = validate_room_name(self.name_edit.text())
            visibility = validate_visibility("private" if self.private_radio.isChecked() else "public")
            password = validate_room_password(self.password_edit.text(), visibility)
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self._values = (name, visibility, password)
        super().accept()

    def values(self) -> tuple[str, str, str | None]:
        return self._values or ("", "public", None)

    def set_default_name(self, name: str) -> None:
        self.name_edit.setText(name)


class JoinRoomDialog(QDialog):
    """加入房间：5 位房间号 + 可选密码。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        code: str = "",
        hint: str = "",
        password_focus: bool = False,
    ) -> None:
        super().__init__(parent)
        self._values: tuple[str, str | None] | None = None
        self._build(code=code, hint=hint, password_focus=password_focus)

    def _build(self, code: str, hint: str, password_focus: bool) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)
        heading = QLabel("加入房间")
        heading.setObjectName("PageTitle")
        sub = QLabel("输入 5 位房间号（A-Z / 0-9）；私有房间还需要房间密码")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)
        root.addSpacing(6)

        root.addWidget(QLabel("房间号"))
        self.code_edit = QLineEdit()
        self.code_edit.setObjectName("CodeInput")
        self.code_edit.setMaxLength(5)
        self.code_edit.setPlaceholderText("AB12C")
        self.code_edit.setText(code.upper())
        self.code_edit.setValidator(QRegularExpressionValidator("[A-Za-z0-9]{0,5}", self.code_edit))
        root.addWidget(self.code_edit)

        root.addWidget(QLabel("房间密码（公开房间留空）"))
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("私有房间密码")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(self.password_edit)

        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("Hint")
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        root.addWidget(self.hint_label)

        self.error_label = _error_label(root)
        _add_buttons(self, root, "加入")
        self.code_edit.textChanged.connect(self._upper_code)
        if password_focus:
            self.password_edit.setFocus()
        else:
            self.code_edit.setFocus()
        self.code_edit.selectAll()

    def _upper_code(self, text: str) -> None:
        upper = text.upper()
        if upper != text:
            self.code_edit.blockSignals(True)
            self.code_edit.setText(upper)
            self.code_edit.setCursorPosition(len(upper))
            self.code_edit.blockSignals(False)

    def accept(self) -> None:  # noqa: D401 - Qt 覆盖
        self.error_label.hide()
        try:
            code = validate_room_code(self.code_edit.text())
        except ValidationError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        password = self.password_edit.text()
        self._values = (code, password if password else None)
        super().accept()

    def values(self) -> tuple[str, str | None]:
        return self._values or ("", None)


class SettingsDialog(QDialog):
    """设置：连接配置（服务器/WS/Mock/token）+ 个人资料（昵称/密码）。"""

    test_requested = Signal(str, str)  # (server_url 文本, ws_url 文本)
    nickname_save_requested = Signal(str)
    password_change_requested = Signal(str, str)  # (旧密码, 新密码)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._result: AppConfig | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)
        heading = QLabel("设置")
        heading.setObjectName("PageTitle")
        sub = QLabel("连接配置保存到 ~/.delta_client.json；个人资料修改成功后保持登录")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)
        root.addSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_connection_tab(), "连接")
        self.tabs.addTab(self._build_profile_tab(), "个人资料")
        root.addWidget(self.tabs, stretch=1)

        self.error_label = _error_label(root)
        _add_buttons(self, root, "保存")

    def _build_connection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        layout.addWidget(QLabel("HTTP 服务器地址"))
        self.server_edit = QLineEdit(self._config.server_url)
        self.server_edit.setPlaceholderText("http://127.0.0.1:8000")
        layout.addWidget(self.server_edit)

        layout.addWidget(QLabel("WebSocket 地址（留空则自动推导为 ws(s)://host/ws）"))
        self.ws_edit = QLineEdit(self._config.ws_url or "")
        self.ws_edit.setPlaceholderText("留空 = 自动推导 ws://<host>:8000/ws")
        layout.addWidget(self.ws_edit)

        self.mock_check = QCheckBox("使用内置 Mock 后端（不联网，用于后端未就绪时演示）")
        self.mock_check.setChecked(self._config.use_mock)
        layout.addWidget(self.mock_check)

        self.save_token_check = QCheckBox("登录后把 token 保存到本机（不保存密码）")
        self.save_token_check.setChecked(self._config.persist_token)
        layout.addWidget(self.save_token_check)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self.test_button)
        test_row.addStretch(1)
        layout.addLayout(test_row)

        self.test_result_label = QLabel()
        self.test_result_label.setObjectName("Hint")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.hide()
        layout.addWidget(self.test_result_label)

        hint = QLabel(
            "「测试连接」会请求 /health 与 /api/v1/rooms?page=1，并用当前登录 token 验证鉴权。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        self.account_label = QLabel("账号：-（仅自己可见）")
        self.account_label.setObjectName("Muted")
        layout.addWidget(self.account_label)

        layout.addSpacing(4)
        layout.addWidget(QLabel("昵称（1–20 字符，展示给队友）"))
        nickname_row = QHBoxLayout()
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setPlaceholderText("例如：老王的队友")
        self.nickname_save_button = QPushButton("保存昵称")
        self.nickname_save_button.clicked.connect(self._on_save_nickname)
        nickname_row.addWidget(self.nickname_edit, stretch=1)
        nickname_row.addWidget(self.nickname_save_button)
        layout.addLayout(nickname_row)
        self.nickname_result_label = QLabel()
        self.nickname_result_label.setObjectName("Hint")
        self.nickname_result_label.setWordWrap(True)
        self.nickname_result_label.hide()
        layout.addWidget(self.nickname_result_label)

        layout.addSpacing(10)
        layout.addWidget(QLabel("修改密码（新密码 8–64 位，成功后保持登录）"))
        layout.addWidget(QLabel("旧密码"))
        self.old_password_edit = QLineEdit()
        self.old_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.old_password_edit)
        layout.addWidget(QLabel("新密码"))
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.new_password_edit)
        layout.addWidget(QLabel("确认新密码"))
        self.confirm_new_password_edit = QLineEdit()
        self.confirm_new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.confirm_new_password_edit)

        self.password_change_button = QPushButton("修改密码")
        self.password_change_button.setObjectName("Primary")
        self.password_change_button.clicked.connect(self._on_change_password)
        layout.addWidget(self.password_change_button)
        self.password_result_label = QLabel()
        self.password_result_label.setObjectName("Hint")
        self.password_result_label.setWordWrap(True)
        self.password_result_label.hide()
        layout.addWidget(self.password_result_label)

        hint = QLabel(
            "账号只在本页对自己可见；房间成员、聊天、加入/离开提示统一显示昵称。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    # ---------- 个人资料 ----------
    def set_account(self, account: str) -> None:
        self.account_label.setText(f"账号：{account or '-'}（仅自己可见）")

    def set_nickname(self, nickname: str) -> None:
        self.nickname_edit.setText(nickname or "")

    def _on_save_nickname(self) -> None:
        try:
            nickname = validate_nickname(self.nickname_edit.text())
        except ValidationError as exc:
            self.set_nickname_result(str(exc), False)
            return
        self.set_nickname_busy(True)
        self.nickname_save_requested.emit(nickname)

    def _on_change_password(self) -> None:
        try:
            old_password, new_password = validate_password_change(
                self.old_password_edit.text(),
                self.new_password_edit.text(),
                self.confirm_new_password_edit.text(),
            )
        except ValidationError as exc:
            self.set_password_result(str(exc), False)
            return
        self.set_password_busy(True)
        self.password_change_requested.emit(old_password, new_password)

    def set_nickname_busy(self, busy: bool) -> None:
        self.nickname_save_button.setEnabled(not busy)
        self.nickname_save_button.setText("保存中…" if busy else "保存昵称")

    def set_password_busy(self, busy: bool) -> None:
        self.password_change_button.setEnabled(not busy)
        self.password_change_button.setText("修改中…" if busy else "修改密码")

    def set_nickname_result(self, text: str, ok: bool | None = None) -> None:
        self.set_nickname_busy(False)
        self.nickname_result_label.setText(str(text))
        self.nickname_result_label.setStyleSheet(
            "color: #8be3a8;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.nickname_result_label.show()

    def set_password_result(self, text: str, ok: bool | None = None) -> None:
        self.set_password_busy(False)
        self.password_result_label.setText(str(text))
        self.password_result_label.setStyleSheet(
            "color: #8be3a8;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.password_result_label.show()
        if ok is True:
            for edit in (
                self.old_password_edit,
                self.new_password_edit,
                self.confirm_new_password_edit,
            ):
                edit.clear()

    def _on_test_clicked(self) -> None:
        self.test_requested.emit(self.server_edit.text().strip(), self.ws_edit.text().strip())

    def set_testing(self, testing: bool) -> None:
        self.test_button.setEnabled(not testing)
        self.test_button.setText("测试中…" if testing else "测试连接")
        if testing:
            self.test_result_label.setStyleSheet("")
            self.test_result_label.setText("正在测试 /health 与 /api/v1/rooms?page=1 …")
            self.test_result_label.show()

    def set_test_result(self, text: str, ok: bool | None = None) -> None:
        self.set_testing(False)
        self.test_result_label.setText(str(text))
        if ok is True:
            self.test_result_label.setStyleSheet("color: #8be3a8;")
        elif ok is False:
            self.test_result_label.setStyleSheet("color: #ff9b8f;")
        else:
            self.test_result_label.setStyleSheet("")
        self.test_result_label.show()

    def accept(self) -> None:  # noqa: D401 - Qt 覆盖
        self.error_label.hide()
        try:
            server_url = normalize_server_url(self.server_edit.text())
            ws_text = self.ws_edit.text().strip()
            ws_url = normalize_ws_url(ws_text) if ws_text else None
        except ConfigError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self._result = replace(
            self._config,
            server_url=server_url,
            ws_url=ws_url,
            use_mock=self.mock_check.isChecked(),
            persist_token=self.save_token_check.isChecked(),
            source="file",
        )
        super().accept()

    def config_result(self) -> AppConfig:
        return self._result or self._config


class RoomSettingsDialog(QDialog):
    """房主房间管理（F）：改房间名 / 改私有房密码 / 删除房间（二次确认）。"""

    rename_requested = Signal(str)
    password_change_requested = Signal(str)
    delete_requested = Signal()

    def __init__(self, room: Room, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._room = room
        self._build()

    def _build(self) -> None:
        self.setWindowTitle("房间设置")
        self.setModal(True)
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(8)
        heading = QLabel("房间设置")
        heading.setObjectName("PageTitle")
        sub = QLabel(f"房间 {self._room.code} · 仅房主可操作")
        sub.setObjectName("PageSubtitle")
        root.addWidget(heading)
        root.addWidget(sub)
        root.addSpacing(4)

        # 改房间名
        root.addWidget(QLabel("房间名称（1–30 字符）"))
        rename_row = QHBoxLayout()
        self.name_edit = QLineEdit(self._room.name)
        self.rename_button = QPushButton("保存名称")
        self.rename_button.clicked.connect(self._on_rename)
        rename_row.addWidget(self.name_edit, stretch=1)
        rename_row.addWidget(self.rename_button)
        root.addLayout(rename_row)
        self.rename_result_label = QLabel()
        self.rename_result_label.setObjectName("Hint")
        self.rename_result_label.setWordWrap(True)
        self.rename_result_label.hide()
        root.addWidget(self.rename_result_label)

        # 改密码（仅私有房）
        if self._room.has_password:
            root.addSpacing(6)
            root.addWidget(QLabel("修改房间密码（4–64 位）"))
            self.new_password_edit = QLineEdit()
            self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.new_password_edit.setPlaceholderText("新房间密码")
            self.confirm_password_edit = QLineEdit()
            self.confirm_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_password_edit.setPlaceholderText("确认新房间密码")
            root.addWidget(self.new_password_edit)
            root.addWidget(self.confirm_password_edit)
            self.password_button = QPushButton("修改密码")
            self.password_button.clicked.connect(self._on_change_password)
            root.addWidget(self.password_button)
            self.password_result_label = QLabel()
            self.password_result_label.setObjectName("Hint")
            self.password_result_label.setWordWrap(True)
            self.password_result_label.hide()
            root.addWidget(self.password_result_label)
        else:
            self.new_password_edit = None
            self.confirm_password_edit = None
            self.password_button = None
            self.password_result_label = None

        # 删除房间（输入房间名确认）
        root.addSpacing(10)
        warning = QLabel("危险操作：删除后房间关闭、成员会被移出，且不可恢复。")
        warning.setObjectName("ErrorBanner")
        warning.setWordWrap(True)
        root.addWidget(warning)
        root.addWidget(QLabel(f"输入房间名「{self._room.name}」以确认删除"))
        self.delete_confirm_edit = QLineEdit()
        self.delete_confirm_edit.setPlaceholderText(self._room.name)
        self.delete_button = QPushButton("删除房间")
        self.delete_button.setObjectName("Danger")
        self.delete_button.setEnabled(False)
        self.delete_confirm_edit.textChanged.connect(self._on_delete_text_changed)
        self.delete_button.clicked.connect(self._on_delete_clicked)
        root.addWidget(self.delete_confirm_edit)
        root.addWidget(self.delete_button)
        self.delete_result_label = QLabel()
        self.delete_result_label.setObjectName("Hint")
        self.delete_result_label.setWordWrap(True)
        self.delete_result_label.hide()
        root.addWidget(self.delete_result_label)

        root.addSpacing(6)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        close_row.addWidget(close_button)
        root.addLayout(close_row)

    # ---------- 操作 ----------
    def _on_rename(self) -> None:
        try:
            name = validate_room_name_update(self.name_edit.text())
        except ValidationError as exc:
            self.set_rename_result(str(exc), False)
            return
        self.set_rename_busy(True)
        self.rename_requested.emit(name)

    def _on_change_password(self) -> None:
        if self.new_password_edit is None or self.confirm_password_edit is None:
            return
        try:
            password = validate_room_password_change(
                self.new_password_edit.text(), self.confirm_password_edit.text()
            )
        except ValidationError as exc:
            self.set_password_result(str(exc), False)
            return
        self.set_password_busy(True)
        self.password_change_requested.emit(password)

    def _on_delete_text_changed(self, text: str) -> None:
        self.delete_button.setEnabled(
            str(text).strip() == self._room.name.strip() and bool(self._room.name.strip())
        )

    def _on_delete_clicked(self) -> None:
        try:
            validate_room_delete_confirmation(self.delete_confirm_edit.text(), self._room.name)
        except ValidationError as exc:
            self.set_delete_result(str(exc), False)
            return
        self.delete_button.setEnabled(False)
        self.delete_result_label.setText("正在删除房间…")
        self.delete_result_label.setStyleSheet("")
        self.delete_result_label.show()
        self.delete_requested.emit()

    # ---------- 结果 ----------
    def set_rename_busy(self, busy: bool) -> None:
        self.rename_button.setEnabled(not busy)
        self.rename_button.setText("保存中…" if busy else "保存名称")

    def set_password_busy(self, busy: bool) -> None:
        if self.password_button is None:
            return
        self.password_button.setEnabled(not busy)
        self.password_button.setText("修改中…" if busy else "修改密码")

    def set_rename_result(self, text: str, ok: bool | None = None) -> None:
        self.set_rename_busy(False)
        self.rename_result_label.setText(str(text))
        self.rename_result_label.setStyleSheet(
            "color: #8be3a8;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.rename_result_label.show()

    def set_password_result(self, text: str, ok: bool | None = None) -> None:
        if self.password_result_label is None:
            return
        self.set_password_busy(False)
        self.password_result_label.setText(str(text))
        self.password_result_label.setStyleSheet(
            "color: #8be3a8;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.password_result_label.show()
        if ok is True:
            self.new_password_edit.clear()
            self.confirm_password_edit.clear()

    def set_delete_result(self, text: str, ok: bool | None = None) -> None:
        self.delete_result_label.setText(str(text))
        self.delete_result_label.setStyleSheet(
            "color: #8be3a8;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.delete_result_label.show()

    def update_room(self, room: Room) -> None:
        self._room = room
        self.name_edit.setText(room.name)
        self.delete_confirm_edit.setPlaceholderText(room.name)
