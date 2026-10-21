"""登录 / 注册界面（QStackedWidget 的第一页）。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.validation import (
    ValidationError,
    validate_login_input,
    validate_register_input,
    validate_register_username,
)
from state.saved_logins import SavedLoginInfo
from ui.login_history import LoginHistoryPopup
from ui.username_edit import UsernameLineEdit


class LoginView(QWidget):
    """登录/注册表单；校验在本地完成，网络请求由 MainWindow 处理。"""

    login_requested = Signal(str, str)
    register_requested = Signal(str, str)
    settings_requested = Signal()
    saved_login_selected = Signal(str)
    saved_login_delete_requested = Signal(str)
    saved_login_clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "login"
        self._saved_entries: list[SavedLoginInfo] = []
        self._applying_saved = False
        self._history_popup: LoginHistoryPopup | None = None
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

        self.username_edit = UsernameLineEdit("login")
        self.username_edit.setPlaceholderText("账号")
        self.username_edit.setClearButtonEnabled(True)
        self.username_edit.textChanged.connect(self._on_username_changed)

        # 注册账号实时规则提示（F）：6–20 位字母/数字，至少含 1 个字母
        self.register_username_hint = QLabel()
        self.register_username_hint.setObjectName("Hint")
        self.register_username_hint.setWordWrap(True)
        self.register_username_hint.hide()

        username_row = QHBoxLayout()
        username_row.setContentsMargins(0, 0, 0, 0)
        username_row.setSpacing(0)
        username_row.addWidget(self.username_edit, stretch=1)
        self.history_button = QToolButton()
        self.history_button.setObjectName("HistoryArrow")
        self.history_button.setText("▾")
        self.history_button.setToolTip("历史账号")
        self.history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_button.setFixedWidth(32)
        self.history_button.setAutoRaise(True)
        self.history_button.clicked.connect(self._toggle_history)
        self.history_button.hide()
        username_row.addWidget(self.history_button)
        card_layout.addLayout(username_row)
        card_layout.addWidget(self.register_username_hint)

        # H2：密码自动带出/过期提示
        self.saved_hint = QLabel()
        self.saved_hint.setObjectName("Hint")
        self.saved_hint.setWordWrap(True)
        self.saved_hint.hide()
        card_layout.addWidget(self.saved_hint)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # 注册密码下限与后端 F/B 对齐（8–32 位）
        self.password_hint = QLabel("密码 8–32 位")
        self.password_hint.setObjectName("Hint")
        self.password_hint.hide()

        self.confirm_edit = QLineEdit()
        self.confirm_edit.setPlaceholderText("确认密码")
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)

        card_layout.addWidget(self.password_edit)
        card_layout.addWidget(self.password_hint)
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
        self.server_label.hide()  # 服务器/模式统一放主窗口状态栏，页面内不重复展示

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
        self.username_edit.set_mode(self._mode)
        self.username_edit.setPlaceholderText(
            "账号（字母/数字，6–20 位）" if is_register else "账号（字母/数字）"
        )
        self.password_edit.setPlaceholderText("密码（8–32 位）" if is_register else "密码")
        self.password_hint.setVisible(is_register)
        self.confirm_edit.setVisible(is_register)
        self.register_username_hint.setVisible(is_register)
        self.saved_hint.setVisible(False)
        if is_register:
            self._close_history()
        self._sync_history_button()
        self.primary_button.setText("注 册" if is_register else "登 录")
        self.switch_button.setText("已有账号？返回登录" if is_register else "没有账号？创建账户")
        self._update_register_hint()
        self.hide_messages()
        self._focus_first()

    def _on_username_changed(self) -> None:
        if not self._applying_saved:
            self.saved_hint.hide()
        self._update_register_hint()

    def set_saved_logins(self, entries: list[SavedLoginInfo]) -> None:
        self._saved_entries = list(entries)
        if self._history_popup is not None:
            self._history_popup.set_entries(self._saved_entries)
            if not self._saved_entries:
                self._close_history()
        self._sync_history_button()

    def _sync_history_button(self) -> None:
        count = len(self._saved_entries)
        self.history_button.setToolTip(f"历史账号 ({count})" if count else "无历史账号")
        self.history_button.setVisible(self._mode == "login" and count > 0)

    def _toggle_history(self) -> None:
        if self._mode != "login" or not self._saved_entries:
            return
        if self._history_popup is not None and self._history_popup.isVisible():
            self._close_history()
            return
        if self._history_popup is None:
            self._history_popup = LoginHistoryPopup(self._saved_entries, self)
            self._history_popup.selected.connect(self._on_history_selected)
            self._history_popup.delete_requested.connect(self.saved_login_delete_requested.emit)
            self._history_popup.clear_requested.connect(self._on_history_clear_requested)
        else:
            self._history_popup.set_entries(self._saved_entries)
        self._history_popup.show_for(self.username_edit)

    def _close_history(self) -> None:
        if self._history_popup is not None:
            self._history_popup.hide()

    def _on_history_selected(self, username: str) -> None:
        self._close_history()
        if username:
            self.saved_login_selected.emit(username)

    def _on_history_clear_requested(self) -> None:
        self._close_history()
        answer = QMessageBox.question(
            self,
            "清空历史账号",
            "确定清空本机保存的全部历史账号和密码？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.saved_login_clear_requested.emit()

    @property
    def history_popup(self) -> LoginHistoryPopup | None:
        return self._history_popup

    def apply_saved_login(
        self, username: str, password: str, *, expired: bool = False
    ) -> None:
        """带出最近账号/密码；过期时只填账号并提示重新输入。"""
        self._applying_saved = True
        try:
            self.set_mode("login")
            self.username_edit.setText(username)
            self.password_edit.setText(password or "")
        finally:
            self._applying_saved = False
        self.hide_messages()
        if expired:
            self.saved_hint.setText("密码已过期，请重新输入")
            self.saved_hint.setStyleSheet("color: #ffd071;")
            self.saved_hint.show()
        else:
            self.saved_hint.hide()
        if password:
            self.primary_button.setFocus()
        else:
            self.password_edit.setFocus()

    def focus_login_button(self) -> None:
        self.primary_button.setFocus()

    def _open_history(self) -> None:
        """兼容旧调用：打开下拉弹层。"""
        self._toggle_history()

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
            self.history_button,
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
