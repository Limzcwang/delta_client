"""登录 / 注册界面（QStackedWidget 的第一页）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.validation import (
    ValidationError,
    validate_login_input,
    validate_register_input,
    validate_register_username,
)


class LoginView(QWidget):
    """登录/注册表单；校验在本地完成，网络请求由 MainWindow 处理。"""

    login_requested = Signal(str, str)
    register_requested = Signal(str, str)
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "login"
        self._build_ui()
        self.set_mode("login")

    # ---------- UI ----------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_brand_panel(), stretch=0)
        root.addWidget(self._build_form_panel(), stretch=1)

    def _build_brand_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("BrandPanel")
        panel.setFixedWidth(400)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(46, 60, 46, 46)
        layout.setSpacing(18)

        title = QLabel("DELTA")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("三角洲行动 · 队友房间工具")
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)

        features = QLabel(
            "· 公共 / 私有房间，5 位房间号\n"
            "· 房间内文字聊天\n"
            "· 画板协同（C2 占位）\n"
            "· 本地截屏识别技能 CD（C3 占位）"
        )
        features.setObjectName("BrandBullet")
        features.setWordWrap(True)

        notice = QLabel("仅桌面端 · 不收集屏幕内容\n截屏与识别全部在本机完成")
        notice.setObjectName("Hint")
        notice.setWordWrap(True)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addWidget(features)
        layout.addStretch(2)
        layout.addWidget(notice)
        return panel

    def _build_form_panel(self) -> QWidget:
        wrapper = QWidget()
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(60, 44, 60, 44)
        outer.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.addStretch(1)
        self.settings_button = QPushButton("连接设置")
        self.settings_button.setObjectName("Link")
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.clicked.connect(self.settings_requested.emit)
        top_bar.addWidget(self.settings_button)
        outer.addLayout(top_bar)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        card.setMaximumWidth(430)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 30, 32, 30)
        card_layout.setSpacing(12)

        self.form_title = QLabel("欢迎回来")
        self.form_title.setObjectName("PageTitle")
        self.form_subtitle = QLabel("使用账号登录，进入房间大厅")
        self.form_subtitle.setObjectName("PageSubtitle")

        card_layout.addWidget(self.form_title)
        card_layout.addWidget(self.form_subtitle)
        card_layout.addSpacing(10)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("账号")
        self.username_edit.setClearButtonEnabled(True)
        self.username_edit.textChanged.connect(self._update_register_hint)

        # 注册账号实时规则提示（F）：6–20 位字母/数字，至少含 1 个字母
        self.register_username_hint = QLabel()
        self.register_username_hint.setObjectName("Hint")
        self.register_username_hint.setWordWrap(True)
        self.register_username_hint.hide()
        card_layout.addWidget(self.username_edit)
        card_layout.addWidget(self.register_username_hint)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setPlaceholderText("确认密码")
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        card_layout.addWidget(self.password_edit)
        card_layout.addWidget(self.confirm_edit)

        self.error_banner = QLabel()
        self.error_banner.setObjectName("ErrorBanner")
        self.error_banner.setWordWrap(True)
        self.error_banner.hide()
        self.success_banner = QLabel()
        self.success_banner.setObjectName("SuccessBanner")
        self.success_banner.setWordWrap(True)
        self.success_banner.hide()
        card_layout.addWidget(self.error_banner)
        card_layout.addWidget(self.success_banner)

        self.primary_button = QPushButton("登 录")
        self.primary_button.setObjectName("Primary")
        self.primary_button.setMinimumHeight(44)
        self.primary_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_button.clicked.connect(self._submit)

        self.switch_button = QPushButton("没有账号？创建账户")
        self.switch_button.setObjectName("Link")
        self.switch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_button.clicked.connect(self._toggle_mode)

        card_layout.addSpacing(6)
        card_layout.addWidget(self.primary_button)
        card_layout.addWidget(self.switch_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        card_layout.addSpacing(10)
        self.server_label = QLabel("服务器：-")
        self.server_label.setObjectName("Hint")
        self.server_label.setWordWrap(True)
        card_layout.addWidget(self.server_label)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        outer.addStretch(1)

        hint = QLabel("Enter 提交 · 服务器地址可用 DELTA_SERVER 环境变量或 ~/.delta_client.json 配置")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.password_edit.returnPressed.connect(self._submit)
        self.confirm_edit.returnPressed.connect(self._submit)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)
        return wrapper

    # ---------- 对外 ----------
    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        self._mode = "register" if mode == "register" else "login"
        is_register = self._mode == "register"
        self.form_title.setText("创建账户" if is_register else "欢迎回来")
        self.form_subtitle.setText(
            "注册后即可登录并加入队友房间" if is_register else "使用账号登录，进入房间大厅"
        )
        self.confirm_edit.setVisible(is_register)
        self.register_username_hint.setVisible(is_register)
        self.primary_button.setText("注 册" if is_register else "登 录")
        self.switch_button.setText("已有账号？返回登录" if is_register else "没有账号？创建账户")
        self._update_register_hint()
        self.hide_messages()
        self._focus_first()

    def _update_register_hint(self) -> None:
        """注册模式下实时提示账号规则（F）。"""
        if self._mode != "register":
            return
        raw = self.username_edit.text().strip()
        if not raw:
            self.register_username_hint.setText("账号：6–20 位字母或数字，至少包含 1 个字母")
            self.register_username_hint.setStyleSheet("color: #8b98a8;")
            return
        try:
            validate_register_username(raw)
        except ValidationError as exc:
            self.register_username_hint.setText(str(exc))
            self.register_username_hint.setStyleSheet("color: #ff9b8f;")
        else:
            self.register_username_hint.setText("账号格式可用")
            self.register_username_hint.setStyleSheet("color: #8be3a8;")

    def set_server_text(self, server_url: str, mode_label: str) -> None:
        self.server_label.setText(f"服务器：{server_url}  ·  模式：{mode_label}")

    def prefill_username(self, username: str) -> None:
        self.username_edit.setText(username)
        self.username_edit.setFocus()

    def set_busy(self, busy: bool) -> None:
        for widget in (
            self.username_edit,
            self.password_edit,
            self.confirm_edit,
            self.primary_button,
            self.switch_button,
            self.settings_button,
        ):
            widget.setEnabled(not busy)
        if busy:
            self.primary_button.setText("请稍候…")
        else:
            self.primary_button.setText("注 册" if self._mode == "register" else "登 录")

    def show_error(self, message: str) -> None:
        self.success_banner.hide()
        self.error_banner.setText(str(message))
        self.error_banner.show()

    def show_success(self, message: str) -> None:
        self.error_banner.hide()
        self.success_banner.setText(str(message))
        self.success_banner.show()

    def hide_messages(self) -> None:
        self.error_banner.hide()
        self.success_banner.hide()

    def focus_first(self) -> None:
        self._focus_first()

    def _focus_first(self) -> None:
        if self.username_edit.text().strip():
            self.password_edit.setFocus()
        else:
            self.username_edit.setFocus()

    # ---------- 交互 ----------
    def _toggle_mode(self) -> None:
        self.set_mode("login" if self._mode == "register" else "register")

    def _submit(self) -> None:
        self.hide_messages()
        try:
            if self._mode == "register":
                username, password = validate_register_input(
                    self.username_edit.text(),
                    self.password_edit.text(),
                    self.confirm_edit.text(),
                )
                self.register_requested.emit(username, password)
            else:
                username, password = validate_login_input(
                    self.username_edit.text(), self.password_edit.text()
                )
                self.login_requested.emit(username, password)
        except ValidationError as exc:
            self.show_error(str(exc))
