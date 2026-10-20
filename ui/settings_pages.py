"""P3：连接设置 / 个人资料独立页（固定表头 + 600px 居中滚动 + 固定底部）。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import (
    DEFAULT_SERVER_URL,
    AppConfig,
    ConfigError,
    normalize_server_url,
    normalize_ws_url,
)


class _PageShell(QWidget):
    """固定表头 + 600px 居中滚动内容 + 固定底部。"""

    back_requested = Signal()

    def __init__(self, title: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("PageHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 14, 26, 12)
        header_layout.setSpacing(12)
        self.back_button = QPushButton("← 返回大厅")
        self.back_button.setObjectName("Text")
        self.back_button.clicked.connect(self.back_requested.emit)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("Hint")
        self.hint_label.setWordWrap(True)
        header_layout.addWidget(self.back_button)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.hint_label)
        root.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(26, 18, 26, 18)
        body_layout.addStretch(1)
        self.form = QWidget()
        self.form.setFixedWidth(600)
        self.form_layout = QVBoxLayout(self.form)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(12)
        body_layout.addWidget(self.form, 0, Qt.AlignmentFlag.AlignTop)
        body_layout.addStretch(1)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("PageFooter")
        self.footer_layout = QHBoxLayout(footer)
        self.footer_layout.setContentsMargins(26, 10, 26, 14)
        self.footer_layout.setSpacing(10)
        root.addWidget(footer)

    def _add_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label


class ConnectionPage(_PageShell):
    """连接设置独立页；不动三个设计稿开关，只沿用现有连接字段。"""

    test_requested = Signal(str, str)
    saved = Signal(object)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__("连接设置", "配置保存到 %APPDATA%\\DeltaClient\\config.json", parent)
        self._config = config
        self._build()
        self.set_config(config)

    def _build(self) -> None:
        self.server_migrated_label = QLabel("已切换到 HTTPS 服务器（旧 HTTP 默认地址已自动迁移）")
        self.server_migrated_label.setObjectName("Hint")
        self.server_migrated_label.setStyleSheet("color: #5fc98e;")
        self.server_migrated_label.setWordWrap(True)
        self.server_migrated_label.hide()
        self.form_layout.addWidget(self.server_migrated_label)

        self.form_layout.addWidget(self._add_field_label("HTTP(S) 服务器地址"))
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("https://deltachat.icu:8443")
        self.form_layout.addWidget(self.server_edit)

        self.form_layout.addWidget(
            self._add_field_label("WebSocket 地址（留空则自动推导为 ws(s)://host/ws）")
        )
        self.ws_edit = QLineEdit()
        self.ws_edit.setPlaceholderText("留空 = 自动推导 ws://<host>:8000/ws")
        self.form_layout.addWidget(self.ws_edit)

        self.mock_check = QCheckBox("使用内置 Mock 后端（不联网，用于后端未就绪时演示）")
        self.form_layout.addWidget(self.mock_check)
        self.save_token_check = QCheckBox("登录后把 token 保存到本机（不保存密码）")
        self.form_layout.addWidget(self.save_token_check)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.setObjectName("Ghost")
        self.test_button.setMinimumHeight(38)
        self.test_button.clicked.connect(
            lambda: self.test_requested.emit(self.server_edit.text().strip(), self.ws_edit.text().strip())
        )
        test_row.addWidget(self.test_button)
        test_row.addStretch(1)
        self.form_layout.addLayout(test_row)

        self.test_result_label = QLabel()
        self.test_result_label.setObjectName("Hint")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.hide()
        self.form_layout.addWidget(self.test_result_label)

        hint = QLabel("「测试连接」会请求 /health 与 /api/v1/rooms?page=1，并用当前登录 token 验证鉴权。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        self.form_layout.addWidget(hint)

        self.error_label = QLabel()
        self.error_label.setObjectName("ErrorBanner")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        self.form_layout.addWidget(self.error_label)

        self.reset_button = QPushButton("恢复默认")
        self.reset_button.setObjectName("Text")
        self.reset_button.clicked.connect(self._reset_defaults)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self.back_requested.emit)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self._save)
        self.footer_layout.addWidget(self.reset_button)
        self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(self.cancel_button)
        self.footer_layout.addWidget(self.save_button)

    def set_config(self, config: AppConfig) -> None:
        self._config = config
        self.server_edit.setText(config.server_url)
        self.ws_edit.setText(config.ws_url or "")
        self.mock_check.setChecked(config.use_mock)
        self.save_token_check.setChecked(config.persist_token)
        self.server_migrated_label.setVisible(bool(config.server_migrated))
        self.error_label.hide()

    def set_server_migrated(self, migrated: bool) -> None:
        self.server_migrated_label.setVisible(bool(migrated))

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
        self.test_result_label.setStyleSheet(
            "color: #5fc98e;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.test_result_label.show()

    def _reset_defaults(self) -> None:
        self.server_edit.setText(DEFAULT_SERVER_URL)
        self.ws_edit.clear()
        self.mock_check.setChecked(False)
        self.save_token_check.setChecked(False)
        self.error_label.hide()

    def result_config(self) -> AppConfig:
        server_url = normalize_server_url(self.server_edit.text())
        ws_text = self.ws_edit.text().strip()
        ws_url = normalize_ws_url(ws_text) if ws_text else None
        return replace(
            self._config,
            server_url=server_url,
            ws_url=ws_url,
            use_mock=self.mock_check.isChecked(),
            persist_token=self.save_token_check.isChecked(),
        )

    def _save(self) -> None:
        self.error_label.hide()
        try:
            config = self.result_config()
        except ConfigError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        self.saved.emit(config)


class ProfilePage(_PageShell):
    """个人资料独立页；修改密码默认收起，点击绿色按钮展开。"""

    nickname_save_requested = Signal(str)
    password_change_requested = Signal(str, str)
    logout_requested = Signal()
    saved = Signal()

    def __init__(self, account: str = "", nickname: str = "", parent: QWidget | None = None) -> None:
        super().__init__("个人资料", "账号只在本页对自己可见", parent)
        self._build()
        self.set_account(account)
        self.set_nickname(nickname)

    def _build(self) -> None:
        self.account_label = QLabel("账号：-（仅自己可见）")
        self.account_label.setObjectName("Muted")
        self.account_label.setStyleSheet("color: rgba(232,238,247,0.55);")
        self.form_layout.addWidget(self.account_label)

        self.form_layout.addWidget(self._add_field_label("昵称（1–20 字符，展示给队友）"))
        row = QHBoxLayout()
        self.nickname_edit = QLineEdit()
        self.nickname_edit.setPlaceholderText("例如：老王的队友")
        self.nickname_save_button = QPushButton("保存昵称")
        self.nickname_save_button.setObjectName("Green")
        self.nickname_save_button.clicked.connect(self._on_save_nickname)
        row.addWidget(self.nickname_edit, 1)
        row.addWidget(self.nickname_save_button)
        self.form_layout.addLayout(row)
        self.nickname_result_label = QLabel()
        self.nickname_result_label.setObjectName("Hint")
        self.nickname_result_label.setWordWrap(True)
        self.nickname_result_label.hide()
        self.form_layout.addWidget(self.nickname_result_label)

        divider = QFrame()
        divider.setObjectName("Divider")
        divider.setFixedHeight(1)
        self.form_layout.addWidget(divider)

        self.password_reveal_button = QPushButton("修改密码")
        self.password_reveal_button.setObjectName("Green")
        self.password_reveal_button.setFixedWidth(180)
        self.password_reveal_button.clicked.connect(self._show_password_form)
        reveal_row = QHBoxLayout()
        reveal_row.addStretch(1)
        reveal_row.addWidget(self.password_reveal_button)
        reveal_row.addStretch(1)
        self.form_layout.addLayout(reveal_row)

        self.password_section = QWidget()
        section = QVBoxLayout(self.password_section)
        section.setContentsMargins(0, 4, 0, 0)
        section.setSpacing(8)
        ps_title = QLabel("修改密码")
        ps_title.setObjectName("SectionTitle")
        section.addWidget(ps_title)
        ps_hint = QLabel("新密码 8–32 位，成功后保持登录")
        ps_hint.setObjectName("Hint")
        section.addWidget(ps_hint)
        section.addWidget(self._add_field_label("旧密码"))
        self.old_password_edit = QLineEdit()
        self.old_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        section.addWidget(self.old_password_edit)
        section.addWidget(self._add_field_label("新密码"))
        self.new_password_edit = QLineEdit()
        self.new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        section.addWidget(self.new_password_edit)
        section.addWidget(self._add_field_label("确认新密码"))
        self.confirm_new_password_edit = QLineEdit()
        self.confirm_new_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        section.addWidget(self.confirm_new_password_edit)
        actions = QHBoxLayout()
        self.password_change_button = QPushButton("修改密码")
        self.password_change_button.setObjectName("Primary")
        self.password_change_button.clicked.connect(self._on_change_password)
        self.password_cancel_button = QPushButton("取消")
        self.password_cancel_button.setObjectName("Ghost")
        self.password_cancel_button.clicked.connect(self._hide_password_form)
        actions.addWidget(self.password_change_button)
        actions.addWidget(self.password_cancel_button)
        actions.addStretch(1)
        section.addLayout(actions)
        self.password_result_label = QLabel()
        self.password_result_label.setObjectName("Hint")
        self.password_result_label.setWordWrap(True)
        self.password_result_label.hide()
        section.addWidget(self.password_result_label)
        self.password_section.hide()
        self.form_layout.addWidget(self.password_section)

        self.logout_button = QPushButton("退出登录")
        self.logout_button.setObjectName("Text")
        self.logout_button.setStyleSheet("QPushButton { color: #ffb347; }")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("Ghost")
        self.cancel_button.clicked.connect(self.back_requested.emit)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self._save)
        self.footer_layout.addWidget(self.logout_button)
        self.footer_layout.addStretch(1)
        self.footer_layout.addWidget(self.cancel_button)
        self.footer_layout.addWidget(self.save_button)

    # ---------- 对外/兼容旧设置页接口 ----------
    def set_account(self, account: str) -> None:
        self.account_label.setText(f"账号：{account or '-'}（仅自己可见）")

    def set_nickname(self, nickname: str) -> None:
        self.nickname_edit.setText(nickname or "")

    def set_nickname_busy(self, busy: bool) -> None:
        self.nickname_save_button.setEnabled(not busy)
        self.nickname_save_button.setText("保存中…" if busy else "保存昵称")

    def set_nickname_result(self, text: str, ok: bool | None = None) -> None:
        self.set_nickname_busy(False)
        self.nickname_result_label.setText(str(text))
        self.nickname_result_label.setStyleSheet(
            "color: #5fc98e;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.nickname_result_label.show()

    def set_password_busy(self, busy: bool) -> None:
        self.password_change_button.setEnabled(not busy)
        self.password_change_button.setText("修改中…" if busy else "修改密码")

    def set_password_result(self, text: str, ok: bool | None = None) -> None:
        self.set_password_busy(False)
        self.password_result_label.setText(str(text))
        self.password_result_label.setStyleSheet(
            "color: #5fc98e;" if ok is True else ("color: #ff9b8f;" if ok is False else "")
        )
        self.password_result_label.show()
        if ok is True:
            for edit in (self.old_password_edit, self.new_password_edit, self.confirm_new_password_edit):
                edit.clear()
            self._hide_password_form()

    def _show_password_form(self) -> None:
        self.password_reveal_button.hide()
        self.password_section.show()
        self.old_password_edit.setFocus()

    def _hide_password_form(self) -> None:
        self.password_section.hide()
        self.password_reveal_button.show()
        self.password_result_label.hide()
        for edit in (self.old_password_edit, self.new_password_edit, self.confirm_new_password_edit):
            edit.clear()

    def _on_save_nickname(self) -> None:
        from core.validation import ValidationError, validate_nickname

        try:
            nickname = validate_nickname(self.nickname_edit.text())
        except ValidationError as exc:
            self.set_nickname_result(str(exc), False)
            return
        self.set_nickname_busy(True)
        self.nickname_save_requested.emit(nickname)

    def _on_change_password(self) -> None:
        from core.validation import ValidationError, validate_password_change

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

    def _save(self) -> None:
        self.saved.emit()
