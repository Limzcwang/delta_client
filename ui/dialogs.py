"""对话框：创建房间、加入房间、连接设置。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import APP_VERSION, AppConfig, ConfigError, normalize_server_url, normalize_ws_url
from core.models import Room
from core.operators import OperatorCatalog, load_operator_catalog
from state.saved_logins import SavedLoginInfo
from core.rooms import ValidationError, validate_room_code, validate_room_name, validate_visibility
from core.rooms import (
    MAX_ROOM_NAME_LENGTH,
    ROOM_PASSWORD_MAX,
    ValidationError,
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
    """创建房间：名称 + 公开/私有 + 私有密码（A：实时校验，失败保留表单）。"""

    create_requested = Signal(str, str, str)  # (name, visibility, password 或 "")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[str, str, str | None] | None = None
        self._busy = False
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
        self.name_edit.setPlaceholderText("1–30 位，例如：开黑上分（缺 1）")
        self.name_edit.textChanged.connect(self._revalidate)
        root.addWidget(self.name_edit)
        self.name_hint = QLabel("1–30 位")
        self.name_hint.setObjectName("Hint")
        self.name_hint.setWordWrap(True)
        root.addWidget(self.name_hint)

        root.addWidget(QLabel("可见性"))
        self.public_radio = QRadioButton("公开房间（出现在公共列表）")
        self.private_radio = QRadioButton("私有房间（需要密码加入，不出现在公共列表）")
        self.public_radio.setChecked(True)
        self.public_radio.toggled.connect(self._on_visibility_changed)
        root.addWidget(self.public_radio)
        root.addWidget(self.private_radio)

        self.password_label = QLabel("房间密码（4–32 位）")
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("4–32 位")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.textChanged.connect(self._revalidate)
        self.password_hint = QLabel("4–32 位")
        self.password_hint.setObjectName("Hint")
        self.password_hint.setWordWrap(True)
        root.addWidget(self.password_label)
        root.addWidget(self.password_edit)
        root.addWidget(self.password_hint)

        self.error_label = _error_label(root)

        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.create_button = QPushButton("创建并进入")
        self.create_button.setObjectName("Primary")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create_clicked)
        row.addWidget(self.cancel_button)
        row.addWidget(self.create_button)
        root.addSpacing(6)
        root.addLayout(row)

        self._on_visibility_changed()

    def _on_visibility_changed(self, *_args: object) -> None:
        is_private = self.private_radio.isChecked()
        self.password_label.setVisible(is_private)
        self.password_edit.setVisible(is_private)
        self.password_hint.setVisible(is_private)
        if not is_private:
            self.password_edit.blockSignals(True)
            self.password_edit.clear()
            self.password_edit.blockSignals(False)
            self.error_label.hide()
        self._revalidate()

    def _current_values(self) -> tuple[str, str, str] | None:
        visibility = "private" if self.private_radio.isChecked() else "public"
        try:
            name = validate_room_name(self.name_edit.text())
        except ValidationError as exc:
            self._set_hint(self.name_hint, str(exc), error=True)
            return None
        else:
            self._set_hint(self.name_hint, f"{len(name)}/{MAX_ROOM_NAME_LENGTH}", error=False)
        if visibility == "private":
            try:
                password = validate_room_password(self.password_edit.text(), visibility) or ""
            except ValidationError as exc:
                self._set_hint(self.password_hint, str(exc), error=True)
                return None
            else:
                self._set_hint(self.password_hint, f"{len(password)}/{ROOM_PASSWORD_MAX}（4–32 位）", error=False)
        else:
            password = ""
            self._set_hint(self.password_hint, "4–32 位", error=False)
        return name, visibility, password

    def _revalidate(self, *_args: object) -> None:
        valid = self._current_values() is not None
        self.create_button.setEnabled(valid and not self._busy)

    @staticmethod
    def _set_hint(label: QLabel, text: str, *, error: bool) -> None:
        label.setText(text)
        label.setStyleSheet("color: #ff9b8f;" if error else "color: #8b98a8;")

    def _on_create_clicked(self) -> None:
        values = self._current_values()
        if values is None:
            return
        self.error_label.hide()
        self.create_requested.emit(*values)

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.create_button.setText("创建中…" if self._busy else "创建并进入")
        self.name_edit.setEnabled(not self._busy)
        self.password_edit.setEnabled(not self._busy and self.private_radio.isChecked())
        self.public_radio.setEnabled(not self._busy)
        self.private_radio.setEnabled(not self._busy)
        self._revalidate()

    def set_error(self, message: str) -> None:
        self.error_label.setText(str(message))
        self.error_label.show()

    def accept(self) -> None:  # noqa: D401 - Qt 覆盖
        values = self._current_values()
        if values is None:
            return
        name, visibility, password = values
        self._values = (name, visibility, password or None)
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
    config_check_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        catalog: OperatorCatalog | None = None,
        config_manager=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._result: AppConfig | None = None
        self._catalog = catalog if catalog is not None else load_operator_catalog()
        self._config_manager = config_manager
        self._hud_profile: dict = dict(config.hud_profile or {})
        self._capture_process = str(config.capture_window_process or "DeltaForceClient-Win64-Shipping")
        self._capture_title = str(config.capture_window_title or "")
        self._overlay_position_reset = False
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(10)
        heading = QLabel("设置")
        heading.setObjectName("PageTitle")
        sub = QLabel("连接配置保存到 %APPDATA%\\DeltaClient\\config.json；个人资料修改成功后保持登录")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)
        version_label = QLabel(f"版本 v{APP_VERSION}")
        version_label.setObjectName("Hint")
        root.addWidget(version_label)
        root.addSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_connection_tab(), "连接")
        self.tabs.addTab(self._build_profile_tab(), "个人资料")
        self.tabs.addTab(self._build_operator_tab(), "干员")
        self.tabs.addTab(self._build_overlay_tab(), "悬浮窗")
        root.addWidget(self.tabs, stretch=1)

        self.error_label = _error_label(root)
        _add_buttons(self, root, "保存")

    def _build_connection_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        self.server_migrated_label = QLabel("已切换到 HTTPS 服务器（旧 HTTP 默认地址已自动迁移）")
        self.server_migrated_label.setObjectName("Hint")
        self.server_migrated_label.setStyleSheet("color:#8be3a8;")
        self.server_migrated_label.setWordWrap(True)
        self.server_migrated_label.hide()
        layout.addWidget(self.server_migrated_label)

        layout.addWidget(QLabel("HTTP(S) 服务器地址"))
        self.server_edit = QLineEdit(self._config.server_url)
        self.server_edit.setPlaceholderText("https://deltachat.icu:8443")
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

    def _build_operator_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)

        layout.addWidget(QLabel("我的干员（用于技能面板与上报；E3b 识别结果会覆盖）"))
        self.operator_combo = QComboBox()
        for operator in self._catalog:
            self.operator_combo.addItem(operator.display_name, operator.id)
        current = self._config.operator_id
        index = self.operator_combo.findData(current) if current else -1
        if index < 0 and self.operator_combo.count():
            index = 0
        if index >= 0:
            self.operator_combo.setCurrentIndex(index)
        layout.addWidget(self.operator_combo)

        self.operator_detail_label = QLabel()
        self.operator_detail_label.setObjectName("Hint")
        self.operator_detail_label.setWordWrap(True)
        layout.addWidget(self.operator_detail_label)
        self.operator_combo.currentIndexChanged.connect(self._refresh_operator_detail)
        self._refresh_operator_detail()

        config_row = QHBoxLayout()
        self.config_version_label = QLabel()
        self.config_updated_label = QLabel()
        self.config_source_label = QLabel()
        for label in (self.config_version_label, self.config_updated_label, self.config_source_label):
            label.setObjectName("Hint")
        self.check_config_button = QPushButton("检查更新")
        self.check_config_button.clicked.connect(self.config_check_requested.emit)
        config_row.addWidget(self.config_version_label)
        config_row.addWidget(self.config_source_label)
        config_row.addWidget(self.config_updated_label)
        config_row.addStretch(1)
        config_row.addWidget(self.check_config_button)
        layout.addLayout(config_row)
        self.config_check_result = QLabel("")
        self.config_check_result.setObjectName("Hint")
        self.config_check_result.setWordWrap(True)
        layout.addWidget(self.config_check_result)
        self.refresh_operator_config_info(self._config_manager)

        calibration_row = QHBoxLayout()
        self.capture_window_button = QPushButton("选择游戏窗口")
        self.capture_window_button.clicked.connect(self._open_window_picker)
        self.detect_window_button = QPushButton("检测窗口")
        self.detect_window_button.clicked.connect(self._detect_game_window)
        calibration_row.addWidget(self.capture_window_button)
        calibration_row.addWidget(self.detect_window_button)
        layout.addLayout(calibration_row)
        self.capture_window_status = QLabel(self._capture_target_text())
        self.capture_window_status.setObjectName("Hint")
        self.capture_window_status.setWordWrap(True)
        layout.addWidget(self.capture_window_status)
        self.capture_method_label = QLabel("采集方式：mss（默认；WGC 仅独占全屏可选）")
        self.capture_method_label.setObjectName("Hint")
        layout.addWidget(self.capture_method_label)

        calibration_row = QHBoxLayout()
        self.calibration_button = QPushButton("HUD 标定…")
        self.calibration_button.clicked.connect(self._open_calibration)
        self.hud_status_label = QLabel("未标定：识别前请框选技能栏" if not self._hud_profile else "已保存 HUD 标定")
        self.hud_status_label.setObjectName("Hint")
        calibration_row.addWidget(self.calibration_button)
        calibration_row.addWidget(self.hud_status_label, stretch=1)
        layout.addLayout(calibration_row)

        hint = QLabel(
            "干员配置来自 assets/operators.json；无秒数的槽位会显示「CD未知」，不参与倒计时与上报。"
            "头像模板缺失时使用首字母占位。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def refresh_operator_config_info(self, manager=None) -> None:
        if manager is not None:
            self._config_manager = manager
        manager = self._config_manager
        if manager is None:
            self.config_version_label.setText("配置版本：内置")
            self.config_source_label.setText("来源：内置")
            self.config_updated_label.setText("更新时间：-")
            return
        state = manager.state
        self.config_version_label.setText(f"配置版本：{state.version}")
        self.config_source_label.setText(f"来源：{state.source_label}")
        self.config_updated_label.setText(f"更新时间：{state.updated_at or '-'}")

    def refresh_operator_catalog(self, catalog: OperatorCatalog) -> None:
        current = str(self.operator_combo.currentData() or "")
        self._catalog = catalog
        self.operator_combo.blockSignals(True)
        self.operator_combo.clear()
        for operator in catalog:
            self.operator_combo.addItem(operator.display_name, operator.id)
        index = self.operator_combo.findData(current or self._config.operator_id)
        if index < 0 and self.operator_combo.count():
            index = 0
        if index >= 0:
            self.operator_combo.setCurrentIndex(index)
        self.operator_combo.blockSignals(False)
        self._refresh_operator_detail()

    def set_config_check_result(self, text: str, ok: bool | None = None) -> None:
        self.config_check_result.setText(text)
        if ok is True:
            self.config_check_result.setStyleSheet("color:#8be3a8;")
        elif ok is False:
            self.config_check_result.setStyleSheet("color:#ff9b8f;")
        else:
            self.config_check_result.setStyleSheet("")
        self.config_check_result.show()

    def _refresh_operator_detail(self) -> None:
        operator = self._catalog.get(str(self.operator_combo.currentData() or ""))
        if operator is None:
            self.operator_detail_label.setText("未找到干员配置")
            return
        lines = [f"{operator.display_name}（{operator.id}）"]
        for slot in (0, 1, 2):
            skill = operator.skill(slot)
            if skill is None:
                lines.append(f"槽位{slot}：未配置")
            elif skill.cd_known:
                lines.append(f"{skill.slot_name}：{skill.name or '-'}，CD {skill.total_cd_ms / 1000:.0f}s")
            else:
                lines.append(f"{skill.slot_name}：{skill.name or '-'}，CD未知")
        self.operator_detail_label.setText("\n".join(lines))

    def _capture_target_text(self) -> str:
        text = f"抓帧目标：{self._capture_process}"
        if self._capture_title:
            text += f" / 标题：{self._capture_title}"
        return text

    def _open_window_picker(self) -> None:
        try:
            from capture.window import list_visible_windows
            from ui.window_picker import WindowPickerDialog

            candidates = list_visible_windows()
            dialog = WindowPickerDialog(candidates, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selected_candidate()
                if selected is not None:
                    self._capture_process = selected.process_name or selected.title
                    self._capture_title = selected.title
                    self.capture_window_status.setText(self._capture_target_text())
        except Exception as exc:  # noqa: BLE001
            self.capture_window_status.setText(f"枚举窗口失败：{exc}")

    def _detect_game_window(self) -> None:
        try:
            from capture.window import find_game_window

            keywords = (self._capture_title,) if self._capture_title else None
            kwargs = {"title_keywords": keywords} if keywords else {}
            result = find_game_window(self._capture_process, **kwargs)
            if result.window is None:
                self.capture_window_status.setText(f"未找到：{result.reason}")
            else:
                window = result.window
                self.capture_window_status.setText(
                    f"已找到（{result.reason}）：PID {window.pid} · {window.title} · "
                    f"{window.client_width}×{window.client_height}"
                )
        except Exception as exc:  # noqa: BLE001
            self.capture_window_status.setText(f"检测失败：{exc}")

    def _open_calibration(self) -> None:
        try:
            from capture.sources import open_source
            from core.hud_profile import HudProfile
            from ui.calibration_dialog import HudCalibrationDialog

            source, message = open_source(
                process_name=self._capture_process,
                title_keyword=self._capture_title,
            )
            if source is None:
                QMessageBox.warning(self, "HUD 标定", message)
                return
            self.capture_method_label.setText(f"采集方式：{message}")
            try:
                frame = source.grab()
            finally:
                source.close()
            if frame is None:
                QMessageBox.warning(self, "HUD 标定", "未取到游戏画面：请确认游戏未最小化、未被遮挡。")
                return
            dialog = HudCalibrationDialog(
                frame.image, HudProfile.from_dict(self._hud_profile or {}), self
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                profile = dialog.result_profile()
                self._hud_profile = profile.to_dict()
                self.hud_status_label.setText(
                    f"已标定：技能栏 {profile.skill_bar.width}×{profile.skill_bar.height}"
                )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "HUD 标定失败", str(exc))

    def _build_overlay_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(8)
        self.overlay_enabled_check = QCheckBox("启用技能 CD 悬浮窗（默认关闭；仅无边框窗口模式）")
        self.overlay_enabled_check.setChecked(self._config.overlay_enabled)
        layout.addWidget(self.overlay_enabled_check)

        self.auto_capture_check = QCheckBox("允许截图采集（E3b，仅内存，不落盘/不上传）")
        self.auto_capture_check.setChecked(self._config.auto_capture_enabled)
        layout.addWidget(self.auto_capture_check)
        self.auto_loop_check = QCheckBox("自动识别并共享（每 2s 抓帧；变化才上报）")
        self.auto_loop_check.setChecked(self._config.auto_loop_enabled)
        layout.addWidget(self.auto_loop_check)
        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("采样间隔"))
        self.auto_interval_combo = QComboBox()
        for value in (1000, 2000, 3000):
            self.auto_interval_combo.addItem(f"{value} ms", value)
        index = self.auto_interval_combo.findData(int(self._config.auto_sample_ms))
        self.auto_interval_combo.setCurrentIndex(max(0, index))
        interval_row.addWidget(self.auto_interval_combo)
        interval_row.addStretch(1)
        layout.addLayout(interval_row)

        row = QHBoxLayout()
        row.addWidget(QLabel("透明度（%）"))
        self.overlay_opacity_spin = QSpinBox()
        self.overlay_opacity_spin.setRange(10, 100)
        self.overlay_opacity_spin.setValue(int(self._config.overlay_opacity))
        row.addWidget(self.overlay_opacity_spin)
        row.addWidget(QLabel("缩放"))
        self.overlay_scale_spin = QDoubleSpinBox()
        self.overlay_scale_spin.setRange(0.6, 2.0)
        self.overlay_scale_spin.setSingleStep(0.1)
        self.overlay_scale_spin.setValue(float(self._config.overlay_scale))
        row.addWidget(self.overlay_scale_spin)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(QLabel("显示/隐藏快捷键"))
        self.shortcut_toggle_edit = QKeySequenceEdit(str(self._config.shortcut_toggle))
        layout.addWidget(self.shortcut_toggle_edit)
        layout.addWidget(QLabel("编辑模式快捷键（可拖动/缩放，退出后恢复鼠标穿透）"))
        self.shortcut_edit_edit = QKeySequenceEdit(str(self._config.shortcut_edit))
        layout.addWidget(self.shortcut_edit_edit)

        reset_row = QHBoxLayout()
        self.overlay_reset_button = QPushButton("重置悬浮窗位置")
        self.overlay_reset_button.clicked.connect(self._reset_overlay_position)
        reset_row.addWidget(self.overlay_reset_button)
        reset_row.addStretch(1)
        layout.addLayout(reset_row)
        self.overlay_status_label = QLabel("当前状态：未启用")
        self.overlay_status_label.setObjectName("Hint")
        self.overlay_status_label.setWordWrap(True)
        layout.addWidget(self.overlay_status_label)
        hint = QLabel(
            "悬浮窗保留房间内面板不变；仅覆盖无边框窗口模式。独占全屏/找不到游戏窗口时自动回落，"
            "并提示使用房间内面板。数值持久化到本地配置。"
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _reset_overlay_position(self) -> None:
        self._overlay_position_reset = True
        self.overlay_status_label.setText("当前状态：位置将在保存后重置")

    def set_overlay_status(self, text: str) -> None:
        self.overlay_status_label.setText(f"当前状态：{text}")

    def set_server_migrated(self, migrated: bool) -> None:
        self.server_migrated_label.setVisible(bool(migrated))

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
        layout.addWidget(QLabel("修改密码（新密码 8–32 位，成功后保持登录）"))
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
        shortcut_toggle = self.shortcut_toggle_edit.keySequence().toString()
        shortcut_edit = self.shortcut_edit_edit.keySequence().toString()
        if shortcut_toggle and shortcut_toggle == shortcut_edit:
            self.error_label.setText("显示/隐藏与编辑模式快捷键不能相同")
            self.error_label.show()
            return
        self._result = replace(
            self._config,
            server_url=server_url,
            ws_url=ws_url,
            use_mock=self.mock_check.isChecked(),
            persist_token=self.save_token_check.isChecked(),
            operator_id=str(self.operator_combo.currentData() or ""),
            hud_profile=self._hud_profile or None,
            overlay_enabled=self.overlay_enabled_check.isChecked(),
            overlay_opacity=int(self.overlay_opacity_spin.value()),
            overlay_scale=float(self.overlay_scale_spin.value()),
            overlay_x=None if self._overlay_position_reset else self._config.overlay_x,
            overlay_y=None if self._overlay_position_reset else self._config.overlay_y,
            shortcut_toggle=shortcut_toggle or "Ctrl+Shift+D",
            shortcut_edit=shortcut_edit or "Ctrl+Shift+E",
            auto_capture_enabled=self.auto_capture_check.isChecked(),
            auto_loop_enabled=self.auto_loop_check.isChecked(),
            auto_sample_ms=int(self.auto_interval_combo.currentData() or 2000),
            capture_window_process=self._capture_process,
            capture_window_title=self._capture_title,
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
            root.addWidget(QLabel("修改房间密码（4–32 位）"))
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


class SavedLoginsDialog(QDialog):
    """H2：历史账号列表（最多 5 条，可单条删除/清空）。"""

    selected = Signal(str)
    delete_requested = Signal(str)
    clear_requested = Signal()

    def __init__(
        self, entries: list[SavedLoginInfo], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("历史账号")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._entries = list(entries)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(10)
        heading = QLabel("历史账号")
        heading.setObjectName("PageTitle")
        sub = QLabel("点击账号可填入；密码仅本机加密保存，30 天内自动带出")
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(sub)

        self.list = QListWidget()
        self.list.setObjectName("SavedLogins")
        root.addWidget(self.list, stretch=1)
        for entry in self._entries:
            self._add_item(entry)
        self.list.itemClicked.connect(self._on_item_clicked)

        actions = QHBoxLayout()
        self.clear_button = QPushButton("清空全部")
        self.clear_button.setObjectName("Link")
        self.clear_button.clicked.connect(self._on_clear)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        actions.addWidget(close_button)
        root.addLayout(actions)
        self._sync_empty()

    def _add_item(self, entry: SavedLoginInfo) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, entry.username)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)
        text = QLabel(f"{entry.username}  ·  {entry.last_used_text}")
        text.setToolTip(entry.status_text)
        status = QLabel(entry.status_text)
        status.setObjectName("Hint")
        if entry.expired and entry.has_password:
            status.setStyleSheet("color: #ffd071;")
        text.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.mousePressEvent = lambda _event, name=entry.username: self._select(name)
        delete = QPushButton("删除")
        delete.setObjectName("Link")
        delete.setProperty("username", entry.username)
        delete.clicked.connect(
            lambda _checked=False, btn=delete: self._on_delete(str(btn.property("username")))
        )
        layout.addWidget(text, stretch=1)
        layout.addWidget(status)
        layout.addWidget(delete)
        item.setSizeHint(row.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, row)

    def _select(self, username: str) -> None:
        if username:
            self.selected.emit(username)
            self.accept()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        username = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self._select(username)

    def _on_delete(self, username: str) -> None:
        self.delete_requested.emit(username)
        for row in range(self.list.count() - 1, -1, -1):
            item = self.list.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == username:
                self.list.takeItem(row)
                break
        self._entries = [entry for entry in self._entries if entry.username != username]
        self._sync_empty()

    def _on_clear(self) -> None:
        self.clear_requested.emit()
        self.list.clear()
        self._entries = []
        self._sync_empty()

    def _sync_empty(self) -> None:
        self.clear_button.setEnabled(bool(self._entries))
        if not self._entries:
            self.list.addItem("还没有保存的账号")
            self.list.setEnabled(False)
        else:
            self.list.setEnabled(True)
