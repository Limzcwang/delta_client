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
    QVBoxLayout,
    QWidget,
)

from config import AppConfig, ConfigError, normalize_server_url, normalize_ws_url
from core.rooms import ValidationError, validate_room_code, validate_room_name, validate_visibility
from core.rooms import validate_room_password


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
    """连接设置：服务器地址 / WS 地址 / Mock 开关 / token 是否落盘 / 连通性测试。"""

    test_requested = Signal(str, str)  # (server_url 文本, ws_url 文本)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._result: AppConfig | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)
        heading = QLabel("连接设置")
        heading.setObjectName("PageTitle")
        sub = QLabel("保存到 ~/.delta_client.json；环境变量 DELTA_SERVER / DELTA_WS 优先级更高")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)
        root.addSpacing(6)

        root.addWidget(QLabel("HTTP 服务器地址"))
        self.server_edit = QLineEdit(self._config.server_url)
        self.server_edit.setPlaceholderText("http://127.0.0.1:8000")
        root.addWidget(self.server_edit)

        root.addWidget(QLabel("WebSocket 地址（留空则自动推导为 ws(s)://host/ws）"))
        self.ws_edit = QLineEdit(self._config.ws_url or "")
        self.ws_edit.setPlaceholderText("ws://127.0.0.1:8765（A 现状后端用这个）")
        root.addWidget(self.ws_edit)

        self.mock_check = QCheckBox("使用内置 Mock 后端（不联网，用于后端未就绪时演示）")
        self.mock_check.setChecked(self._config.use_mock)
        root.addWidget(self.mock_check)

        self.save_token_check = QCheckBox("登录后把 token 保存到本机（不保存密码）")
        self.save_token_check.setChecked(self._config.persist_token)
        root.addWidget(self.save_token_check)

        test_row = QHBoxLayout()
        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._on_test_clicked)
        test_row.addWidget(self.test_button)
        test_row.addStretch(1)
        root.addLayout(test_row)

        self.test_result_label = QLabel()
        self.test_result_label.setObjectName("Hint")
        self.test_result_label.setWordWrap(True)
        self.test_result_label.hide()
        root.addWidget(self.test_result_label)

        hint = QLabel(
            "提示：B2b 起 WS 与 HTTP 同端口（ws://<host>:8000/ws）；留空即可自动推导。"
            "「测试连接」会请求 /health 与 /api/v1/rooms?page=1，并用当前登录 token 验证鉴权。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.error_label = _error_label(root)
        _add_buttons(self, root, "保存")

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
