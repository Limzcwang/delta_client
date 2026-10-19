"""主窗口：QStackedWidget 切换 登录 -> 房间大厅 -> 房间内页，并负责网络编排。"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any, Mapping

from PySide6.QtCore import QEvent, QEventLoop, QTimer
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from config import AppConfig, ConfigError, normalize_server_url, normalize_ws_url, save_config
from core.backoff import ReconnectBackoff
from core.clock import ServerClock
from core.canvas import (
    CanvasError,
    CanvasRateLimiter,
    check_snapshot_limits,
    make_clear_op,
    parse_canvas_snapshot,
)
from core.chat import ChatTimeline
from core.errors import ApiError, ErrorKind, to_user_message
from core.models import (
    ChatMessage,
    Member,
    MyRoom,
    Room,
    RoomDetail,
    now_ms,
    parse_history_window_days,
    parse_members,
)
from core.operators import Operator, OperatorCatalog, load_operator_catalog
from core.operator_config import OperatorConfigManager
from core.protocol import extract_token, extract_user, make_client_msg_id, message_type
from core.rooms import ValidationError, validate_room_delete_confirmation
from core.skills import (
    SLOT_KINDS,
    SkillBook,
    SkillShareThrottle,
    SkillSlot,
    SkillState,
    parse_room_joined_skill_states,
    parse_skill_state_list,
)
from core.skill_payload import build_payload_from_state, clean_captured_at, validate_payload
from net.api_client import ApiClient, LoginResult
from net.mock_backend import MockApiClient, MockWsClient
from net.ws_client import WsClient
from state.session import Session, default_session_path
from state.saved_logins import SavedLoginInfo, SavedLogins
from ui.async_bridge import AsyncBridge
from ui.dialogs import (
    CreateRoomDialog,
    JoinRoomDialog,
    RoomSettingsDialog,
    SettingsDialog,
)
from ui.login_view import LoginView
from ui.room_list_view import RoomListView
from ui.room_view import RoomView
from ui.auto_share import AutoShareController
from ui.skill_overlay import OverlayController, SkillOverlay

logger = logging.getLogger(__name__)

#: 聊天相关 WS 错误 -> 面向用户的失败原因（这些错误需要把 pending 消息标红）
_CHAT_ERROR_REASONS: dict[str, str] = {
    "RATE_LIMITED": "发送过快，请稍后再试",
    "INVALID_MESSAGE": "消息内容不合法（1-2000 字）",
    "NOT_ROOM_MEMBER": "你不在该房间中，请重新加入",
    "ROOM_CLOSED": "房间已关闭",
}

#: 画板相关 WS 错误 -> 提示文案（D）
_CANVAS_ERROR_REASONS: dict[str, str] = {
    "INVALID_CANVAS_OP": "画板操作不合法（点数 / 坐标 / 尺寸超限）",
    "CANVAS_OUT_OF_ORDER": "画板操作序号过期，已丢弃",
    "NOT_ROOM_MEMBER": "你不在该房间中，画板已断开",
    "ROOM_CLOSED": "房间已关闭",
}


class MainWindow(QMainWindow):
    """客户端主窗口。

    - ``AsyncBridge`` 提供 asyncio 事件循环；
    - ``ApiClient``（或 Mock）负责 HTTP；
    - ``WsClient``（或 Mock）负责房间实时消息；
    - 视图只发信号，网络与状态切换集中在 MainWindow。
    """

    def __init__(
        self,
        config: AppConfig,
        session: Session | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.session = session or Session(
            persist_token=config.persist_token,
            persist_path=default_session_path(),
        )
        # H2：历史账号/DPAPI 加密密码
        self.saved_logins = SavedLogins()
        self.bridge = AsyncBridge(self)
        self.bridge.start()
        self.api: Any = self._build_api()
        self._ws: Any = None
        self._ws_generation = 0
        self._current_room: Room | None = None
        self._room_password: str | None = None
        self._timeline = ChatTimeline()
        self._chat_has_more = False
        self._chat_next_before: str | None = None
        self._chat_loading = False
        self._last_members_refresh = 0.0
        self._ws_members_loaded = False
        self._canvas_rev = 0
        self._canvas_last_rev: dict[str, int] = {}
        self._canvas_loaded = False
        self._canvas_queue: list[dict[str, Any]] = []
        self._canvas_limiter = CanvasRateLimiter()
        # F-c3：大厅 5s 自动刷新（失败退避 5→10→20s）
        self._lobby_timer = QTimer(self)
        self._lobby_timer.setInterval(5000)
        self._lobby_timer.timeout.connect(self._auto_refresh_lobby)
        self._lobby_backoff = ReconnectBackoff(base=5.0, factor=2.0, max_delay=20.0)
        self._rooms_loading = False
        self._my_rooms_loading = False
        # E2：技能 CD 共享（默认关闭，收到/模拟状态后本地缓存）
        self._skills = SkillBook()
        self._skill_offset_ms = 0
        self._server_clock = ServerClock()
        self._skill_throttle = SkillShareThrottle(max_events=2, window_ms=1000)
        self._skill_share_enabled = False
        self._skill_sim_index = 0
        self._self_skill_state: SkillState | None = None
        self.operator_config = OperatorConfigManager()
        self.operator_catalog: OperatorCatalog = self.operator_config.catalog
        # F-c5：历史窗口文案（room_joined / 历史接口可选字段）
        self._history_window_days: int | None = None

        self.setWindowTitle("Delta Client - 三角洲行动队友房间")
        self.resize(1200, 780)
        self.setMinimumSize(1020, 680)
        self._build_ui()
        self._wire_views()
        self._refresh_status_bar()
        if self.config.server_migrated:
            self._set_status("已切换到 HTTPS 服务器：https://deltachat.icu:8443")

        if self.session.is_logged_in:
            self._show_rooms()
            self._set_status("已恢复上次登录状态")
        else:
            self._show_login()
        QTimer.singleShot(0, lambda: self._refresh_operator_config(silent=True))

    # ---------- 构建 ----------
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_view = LoginView()
        self.room_list_view = RoomListView()
        self.room_view = RoomView()
        self.room_view.skill_panel.set_operator_catalog(self.operator_catalog)
        self.room_view.skill_panel.set_server_now_provider(self._server_clock.now_ms)
        self.stack.addWidget(self.login_view)
        self.stack.addWidget(self.room_list_view)
        self.stack.addWidget(self.room_view)

        self.overlay = SkillOverlay()
        self.overlay.set_server_now(self._server_clock.now_ms)
        self.overlay_controller = OverlayController(
            self.overlay, self._find_game_window, self._screen_size
        )
        self.overlay.position_changed.connect(self._on_overlay_moved)
        self._toggle_shortcut = QShortcut(QKeySequence(self.config.shortcut_toggle), self)
        self._toggle_shortcut.activated.connect(self._toggle_overlay)
        self._edit_shortcut = QShortcut(QKeySequence(self.config.shortcut_edit), self)
        self._edit_shortcut.activated.connect(self._toggle_overlay_edit)
        self._apply_overlay_config()
        self._auto_controller = AutoShareController(
            self._open_capture_source, self._recognize_auto_frame
        )
        self._auto_controller.payload_ready.connect(self._on_auto_payload)
        self._auto_controller.status_changed.connect(self._on_auto_status)
        self._apply_auto_config()

        self._server_label = QLabel()
        self._server_label.setObjectName("Muted")
        self.statusBar().addPermanentWidget(self._server_label)

    def _wire_views(self) -> None:
        self.login_view.login_requested.connect(self._on_login)
        self.login_view.register_requested.connect(self._on_register)
        self.login_view.settings_requested.connect(self._on_settings)
        self.login_view.saved_login_selected.connect(self._on_saved_login_selected)
        self.login_view.saved_login_delete_requested.connect(self._on_saved_login_delete)
        self.login_view.saved_login_clear_requested.connect(self._on_saved_login_clear)

        self.room_list_view.refresh_requested.connect(self._refresh_lobby)
        self.room_list_view.create_requested.connect(self._on_create_room)
        self.room_list_view.join_requested.connect(self._on_join_room)
        self.room_list_view.logout_requested.connect(self._on_logout)
        self.room_list_view.settings_requested.connect(self._on_settings)
        self.room_list_view.profile_requested.connect(self._on_profile)
        self.room_list_view.my_rooms.leave_requested.connect(self._on_my_room_leave)
        self.room_list_view.my_rooms.close_requested.connect(self._on_my_room_close)

        self.room_view.leave_requested.connect(self._on_leave_room)
        self.room_view.chat_submitted.connect(self._on_chat_submitted)
        self.room_view.history_requested.connect(self._on_history_requested)
        self.room_view.retry_requested.connect(self._on_retry_chat)
        self.room_view.room_settings_requested.connect(self._on_room_settings)
        self.room_view.kick_requested.connect(self._on_kick_requested)
        self.room_view.skill_panel.sharing_toggled.connect(self._on_skill_sharing_toggled)
        self.room_view.skill_panel.simulate_requested.connect(self._on_simulate_skill)
        self.room_view.skill_panel.capture_requested.connect(self._on_hud_capture)
        self.room_view.canvas.stroke_finished.connect(self._on_canvas_strokes)
        self.room_view.canvas.clear_requested.connect(self._on_canvas_clear_requested)

    def _build_api(self) -> Any:
        if self.config.use_mock:
            return MockApiClient()
        return ApiClient(
            self.config.server_url,
            token_provider=lambda: self.session.token,
            timeout=self.config.request_timeout,
        )

    # ---------- 通用 ----------
    def _username(self) -> str:
        """F：展示用昵称（成员/聊天/提示均用它，不显示账号）。"""
        return self.session.display_name or "未知用户"

    def _account(self) -> str:
        """账号：仅在个人资料页对自己展示。"""
        return self.session.username

    def _user_id(self) -> str:
        return self.session.user_id

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(str(message), 8000)

    def _refresh_status_bar(self) -> None:
        self._server_label.setText(
            f"服务器：{self.config.server_url}  ·  模式：{self.config.mode_label}"
        )

    def _safe_submit(self, coro: Any, on_success=None, on_error=None) -> Any:
        try:
            return self.bridge.submit(coro, on_success, on_error)
        except RuntimeError:  # 窗口关闭后不再提交
            logger.debug("异步桥已停止，忽略任务提交")
            return None

    def _show_login(self, message: str = "") -> None:
        self._stop_lobby_timer()
        self.login_view.set_server_text(self.config.server_url, self.config.mode_label)
        self.login_view.set_busy(False)
        self.login_view.set_mode("login")
        self.login_view.focus_first()
        self._auto_fill_saved_login()
        if message:
            self.login_view.show_error(message)
        self.stack.setCurrentWidget(self.login_view)

    # ---------- H2：历史账号 ----------
    def _saved_login_infos(self) -> list[SavedLoginInfo]:
        return self.saved_logins.infos()

    def _refresh_saved_login_view(self) -> None:
        self.login_view.set_saved_logins(self._saved_login_infos())

    def _auto_fill_saved_login(self) -> None:
        self._refresh_saved_login_view()
        recent = self.saved_logins.recent_info()
        if recent is None:
            return
        password = self.saved_logins.password_for(recent.username)
        expired = bool(recent.has_password and recent.expired and password is None)
        self.login_view.apply_saved_login(
            recent.username, password or "", expired=expired
        )

    def _on_saved_login_selected(self, username: str) -> None:
        self.login_view.set_mode("login")
        self._refresh_saved_login_view()
        info = next(
            (entry for entry in self._saved_login_infos() if entry.username == username),
            None,
        )
        password = self.saved_logins.password_for(username)
        expired = bool(info is not None and info.has_password and info.expired and password is None)
        self.login_view.apply_saved_login(username, password or "", expired=expired)
        if password:
            self.login_view.focus_login_button()
        else:
            self.login_view.password_edit.setFocus()

    def _on_saved_login_delete(self, username: str) -> None:
        self.saved_logins.remove(username)
        self._refresh_saved_login_view()
        self.login_view.saved_hint.setText("已删除该账号的本地记录")
        self.login_view.saved_hint.setStyleSheet("color: #8b98a8;")
        self.login_view.saved_hint.show()

    def _on_saved_login_clear(self) -> None:
        self.saved_logins.clear()
        self._refresh_saved_login_view()
        self.login_view.saved_hint.setText("已清空本地历史账号")
        self.login_view.saved_hint.setStyleSheet("color: #8b98a8;")
        self.login_view.saved_hint.show()

    def _show_rooms(self) -> None:
        self.room_list_view.set_user(self._username())
        self.room_list_view.set_mode(self.config.use_mock, self.config.server_url)
        self.stack.setCurrentWidget(self.room_list_view)
        self._lobby_backoff.reset()
        self._lobby_timer.setInterval(5000)
        self._update_lobby_timer()
        self._refresh_lobby(manual=True)

    # ---------- F-c3：大厅自动刷新 ----------
    def _update_lobby_timer(self) -> None:
        """仅大厅可见且有焦点时开启 5s 轮询。"""
        if self.stack.currentWidget() is self.room_list_view and self.isActiveWindow():
            if not self._lobby_timer.isActive():
                self._lobby_timer.setInterval(5000)
                self._lobby_timer.start()
                self.room_list_view.set_auto_refresh_hint("大厅每 5s 自动刷新")
        else:
            self._stop_lobby_timer()

    def _stop_lobby_timer(self) -> None:
        self._lobby_timer.stop()
        self.room_list_view.set_auto_refresh_hint("")

    def _auto_refresh_lobby(self) -> None:
        if self.stack.currentWidget() is not self.room_list_view or not self.isActiveWindow():
            self._stop_lobby_timer()
            return
        if self._rooms_loading and self._my_rooms_loading:
            return
        self._refresh_lobby(manual=False)

    def changeEvent(self, event: Any) -> None:  # noqa: N802 - Qt 覆盖
        if event.type() == QEvent.Type.ActivationChange:
            self._update_lobby_timer()
        super().changeEvent(event)

    # ---------- 认证 ----------
    def _on_login(self, username: str, password: str) -> None:
        self.login_view.set_busy(True)
        self.login_view.hide_messages()
        self._safe_submit(
            self.api.login(username, password),
            lambda result: self._on_login_success(result, username, password),
            lambda exc: self._on_login_failure(exc, username),
        )

    def _on_login_success(
        self, result: LoginResult, username: str = "", password: str = ""
    ) -> None:
        self.login_view.set_busy(False)
        self.session.set_login(result.token, result.user)
        account = str(result.user.get("username") or username or "").strip()
        if account and password:
            # H2：登录成功记录历史账号（密码 DPAPI 加密；失败则只存账号）
            self.saved_logins.upsert(account, password)
            self._refresh_saved_login_view()
        if result.token:
            self._set_status(f"登录成功：{self._username()}")
        else:
            # 后端 B 阶段前 /api/users/login 不返回 JWT，保留兼容分支
            self._set_status("登录成功，但服务器未返回 JWT（PROTOCOL B 阶段才上线）")
        self._refresh_operator_config(silent=True)
        self._show_rooms()

    def _on_login_failure(self, exc: BaseException, username: str = "") -> None:
        self.login_view.set_busy(False)
        message = to_user_message(exc)
        if (
            username
            and isinstance(exc, ApiError)
            and exc.kind == ErrorKind.AUTH
            and self.saved_logins.clear_password(username)
        ):
            # 用户名或密码错误：清除本地密码，账号保留
            self._refresh_saved_login_view()
            message = f"{message}（已清除本地保存的密码）"
        self.login_view.show_error(message)

    def _on_register(self, username: str, password: str) -> None:
        self.login_view.set_busy(True)
        self.login_view.hide_messages()
        self._safe_submit(
            self.api.register(username, password),
            lambda data: self._on_register_success(data, username),
            self._on_register_failure,
        )

    def _on_register_success(self, data: Any, username: str) -> None:
        self.login_view.set_busy(False)
        # B2b 的 v1 注册响应与登录一致（含 access_token），可直接自动登录
        token = extract_token(data)
        if token:
            user = extract_user(data) or {"username": username, "nickname": username}
            self.session.set_login(token, user)
            self._set_status(f"注册成功，已自动登录：{self._username()}")
            self._show_rooms()
            return
        self.login_view.set_mode("login")
        self.login_view.show_success("注册成功，请使用新账号登录")
        self.login_view.prefill_username(username)
        self._set_status("注册成功")

    def _on_register_failure(self, exc: BaseException) -> None:
        self.login_view.set_busy(False)
        self.login_view.show_error(to_user_message(exc))

    def _handle_auth_expired(self, exc: BaseException) -> None:
        message = to_user_message(exc)
        self._stop_ws()
        self._stop_lobby_timer()
        self._current_room = None
        self._clear_room_state()
        self.session.clear()
        self._show_login(f"{message}，请重新登录")

    # ---------- 房间大厅 ----------
    def _refresh_lobby(self, manual: bool = True) -> None:
        """H1：公共房间 + 我的房间共用同一个刷新节拍。"""
        self._refresh_rooms(manual=manual)
        self._refresh_my_rooms(manual=manual)

    def _refresh_my_rooms(self, manual: bool = True) -> None:
        if self._my_rooms_loading:
            return
        self._my_rooms_loading = True
        self._safe_submit(
            self.api.list_my_rooms(),
            lambda page: self._on_my_rooms_loaded(page, manual),
            lambda exc: self._on_my_rooms_failed(exc, manual),
        )

    def _on_my_rooms_loaded(self, page: Any, manual: bool = True) -> None:
        self._my_rooms_loading = False
        rooms = list(getattr(page, "items", ()) or ())
        self.room_list_view.my_rooms.set_rooms(rooms)
        self._update_my_rooms_tab(len(rooms))

    def _on_my_rooms_failed(self, exc: BaseException, manual: bool = True) -> None:
        self._my_rooms_loading = False
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        if manual:
            self.room_list_view.set_status(
                f"我的房间加载失败：{to_user_message(exc)}", error=True
            )

    def _update_my_rooms_tab(self, count: int | None = None) -> None:
        rooms = self.room_list_view.my_rooms.rooms
        total = len(rooms) if count is None else int(count)
        title = f"我的房间 ({total})" if total else "我的房间"
        self.room_list_view.tabs.setTabText(1, title)

    def _refresh_rooms(self, manual: bool = True) -> None:
        if self._rooms_loading:
            return
        self._rooms_loading = True
        if manual:
            self.room_list_view.set_loading(True)
            self.room_list_view.set_status(f"正在连接 {self.config.server_url} …")
        self._safe_submit(
            self.api.list_rooms(),
            lambda rooms: self._on_rooms_loaded(rooms, manual),
            lambda exc: self._on_rooms_failed(exc, manual),
        )

    def _on_rooms_loaded(self, rooms: list[Room], manual: bool = True) -> None:
        self._rooms_loading = False
        if manual:
            self.room_list_view.set_loading(False)
        self.room_list_view.update_rooms(rooms)
        self._lobby_backoff.reset()
        self._lobby_timer.setInterval(5000)
        suffix = "（Mock 演示数据）" if self.config.use_mock else ""
        stamp = time.strftime("%H:%M:%S")
        if rooms:
            self.room_list_view.set_status(f"共 {len(rooms)} 个公共房间{suffix} · 更新于 {stamp}")
        else:
            self.room_list_view.set_status(f"暂无公开房间{suffix}，可以创建一个")

    def _on_rooms_failed(self, exc: BaseException, manual: bool = True) -> None:
        self._rooms_loading = False
        if manual:
            self.room_list_view.set_loading(False)
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        if manual:
            self._lobby_backoff.reset()
            self._lobby_timer.setInterval(5000)
            self.room_list_view.set_status(to_user_message(exc), error=True)
            return
        delay = self._lobby_backoff.next_delay()
        self._lobby_timer.setInterval(int(delay * 1000))
        self.room_list_view.set_status(
            f"自动刷新失败，{delay:.0f}s 后重试：{to_user_message(exc)}", error=True
        )

    # ---------- H1：我的房间 ----------
    def _on_my_room_leave(self, key: str) -> None:
        mine = self.room_list_view.my_rooms.room(key)
        if mine is None:
            return
        answer = QMessageBox.question(
            self,
            "退出房间",
            f"确定退出《{mine.display_name}》？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.room_list_view.my_rooms.set_room_busy(mine.key, True)
        self._safe_submit(
            self.api.leave_room(mine.code or mine.reference),
            lambda _result: self._on_my_room_left(mine),
            lambda exc: self._on_my_room_action_failed(mine, "退出", exc),
        )

    def _on_my_room_left(self, mine: MyRoom) -> None:
        self.room_list_view.my_rooms.remove_room(mine.key)
        self._update_my_rooms_tab()
        self.room_list_view.set_status(f"已退出「{mine.display_name}」")
        current = self._current_room
        if current is not None and self._room_matches_my_room(current, mine):
            self._return_to_lobby_after_room_gone()
            return
        # 公共列表人数需要刷新（不阻塞）
        self._refresh_rooms(manual=False)

    def _on_my_room_close(self, key: str) -> None:
        mine = self.room_list_view.my_rooms.room(key)
        if mine is None:
            return
        text, accepted = QInputDialog.getText(
            self,
            "关闭房间",
            f"输入房间名「{mine.display_name}」以确认关闭：",
        )
        if not accepted:
            return
        try:
            validate_room_delete_confirmation(text, mine.display_name)
        except ValidationError as exc:
            QMessageBox.warning(self, "确认失败", str(exc))
            return
        self.room_list_view.my_rooms.set_room_busy(mine.key, True)
        self._safe_submit(
            self.api.delete_room(mine.reference),
            lambda _result: self._on_my_room_closed(mine),
            lambda exc: self._on_my_room_action_failed(mine, "关闭", exc),
        )

    def _on_my_room_closed(self, mine: MyRoom) -> None:
        self.room_list_view.my_rooms.remove_room(mine.key)
        self._update_my_rooms_tab()
        self.room_list_view.set_status(f"已关闭「{mine.display_name}」")
        current = self._current_room
        if current is not None and self._room_matches_my_room(current, mine):
            self._return_to_lobby_after_room_gone()
            return
        self._refresh_rooms(manual=False)

    def _on_my_room_action_failed(
        self, mine: MyRoom, action: str, exc: BaseException
    ) -> None:
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self.room_list_view.my_rooms.set_room_busy(mine.key, False)
        self.room_list_view.set_status(
            f"{action}「{mine.display_name}」失败：{to_user_message(exc)}", error=True
        )

    @staticmethod
    def _room_matches_my_room(room: Room, mine: MyRoom) -> bool:
        return bool(
            (room.id and mine.id and room.id == mine.id)
            or (room.code and mine.code and room.code == mine.code)
        )

    def _return_to_lobby_after_room_gone(self) -> None:
        self._stop_ws()
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._show_rooms()

    def _on_create_room(self) -> None:
        dialog = CreateRoomDialog(self)
        dialog.create_requested.connect(
            lambda name, visibility, password: self._submit_create_room(
                dialog, name, visibility, password
            )
        )
        dialog.exec()

    def _submit_create_room(
        self, dialog: CreateRoomDialog, name: str, visibility: str, password: str
    ) -> None:
        dialog.set_busy(True)
        self.room_list_view.set_status("正在创建房间…")
        self._safe_submit(
            self.api.create_room(name, visibility, password or None),
            lambda room: self._on_create_room_succeeded(dialog, room, password or None),
            lambda exc: self._on_create_room_failed(dialog, exc),
        )

    def _on_create_room_succeeded(
        self, dialog: CreateRoomDialog, room: Room, password: str | None
    ) -> None:
        dialog.accept()
        self._on_room_created(room, password)

    def _on_create_room_failed(self, dialog: CreateRoomDialog, exc: BaseException) -> None:
        if isinstance(exc, ApiError) and exc.is_auth_error:
            try:
                dialog.reject()
            except RuntimeError:
                pass
            self._handle_auth_expired(exc)
            return
        try:
            dialog.set_busy(False)
            dialog.set_error(to_user_message(exc))
        except RuntimeError:  # 对话框已关闭
            logger.debug("创建房间对话框已关闭，忽略迟到错误")
        self.room_list_view.set_status(to_user_message(exc), error=True)

    def _on_room_created(self, room: Room, password: str | None) -> None:
        self._set_status(f"房间已创建：{room.code}")
        self._enter_room(room, password=password)

    def _on_join_room(self, code: str) -> None:
        self._prompt_join(code or "")

    def _prompt_join(self, code: str, hint: str = "", attempt: int = 0, password_focus: bool = False) -> None:
        dialog = JoinRoomDialog(self, code=code, hint=hint, password_focus=password_focus)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        code, password = dialog.values()
        self.room_list_view.set_status(f"正在加入房间 {code} …")
        self._safe_submit(
            self.api.join_room(code, password),
            lambda room: self._on_room_joined(room, password),
            lambda exc: self._on_join_failed(exc, code, attempt),
        )

    def _on_room_joined(self, room: Room, password: str | None) -> None:
        self._set_status(f"已加入房间 {room.code}")
        self._enter_room(room, password=password)

    def _on_join_failed(self, exc: BaseException, code: str, attempt: int) -> None:
        if isinstance(exc, ApiError) and exc.needs_room_password and attempt < 2:
            self.room_list_view.set_status(exc.user_message, error=True)
            password_focus = exc.kind == ErrorKind.ROOM_PASSWORD_INVALID
            self._prompt_join(code, hint=exc.user_message, attempt=attempt + 1, password_focus=password_focus)
            return
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self.room_list_view.set_status(to_user_message(exc), error=True)

    def _on_room_action_failed(self, exc: BaseException) -> None:
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self.room_list_view.set_status(to_user_message(exc), error=True)

    def _on_logout(self) -> None:
        room = self._current_room
        self._stop_ws(
            room.code if room is not None else None,
            save_canvas=room is not None,
            http_leave_room=room,
        )
        self._current_room = None
        self._clear_room_state()
        self.session.clear()
        self._show_login()
        self.login_view.show_success("已退出登录")
        self._set_status("已退出登录")

    # ---------- 房间内 ----------
    def _enter_room(self, room: Room, password: str | None = None) -> None:
        self._refresh_operator_config(silent=True)
        self._stop_lobby_timer()
        self._current_room = room
        self._room_password = password
        self._ws_members_loaded = False
        self._last_members_refresh = 0.0
        self._timeline = ChatTimeline()
        self._chat_has_more = False
        self._chat_next_before = None
        self._chat_loading = False
        self._history_window_days = None
        self._skills.clear()
        self._self_skill_state = None
        self._skill_share_enabled = False
        if hasattr(self, "_auto_controller"):
            self._auto_controller.stop()
        self.room_view.skill_panel.clear()
        self.room_view.skill_panel.set_sharing(False)
        self._sync_overlay_states()
        self.room_view.skill_panel.set_clock_offset(0)
        self.room_view.set_room(room)
        self.room_view.set_user(self._username(), self._user_id())
        self.room_view.clear_chat()
        self.room_view.canvas.reset()
        self._canvas_rev = 0
        self._canvas_last_rev.clear()
        self._canvas_loaded = False
        self._canvas_queue.clear()
        self.room_view.set_members(list(room.members))
        self.room_view.set_connection_state("connecting", "正在建立实时连接")
        self.room_view.set_status("")
        self.stack.setCurrentWidget(self.room_view)
        self.room_view.focus_chat_input()
        self._system_message(f"已进入 {room.display_name}（{room.code}）")
        self._start_ws(room)
        if hasattr(self, "_auto_controller"):
            self._apply_auto_config()
        # HTTP 成员兜底：WS room_joined 丢失/重连失败时仍能展示成员
        self._refresh_members_http(room, fallback=False)
        # 进房先拉最近一页聊天历史；向上滚动用 next_before 续拉
        self._load_chat_history(room, initial=True)

    def _start_ws(self, room: Room) -> None:
        self._stop_ws()
        generation = self._ws_generation

        def on_message(message: dict[str, Any]) -> None:
            self.bridge.post(lambda: self._on_ws_message(generation, message))

        def on_state(state: str, info: dict[str, Any]) -> None:
            self.bridge.post(lambda: self._on_ws_state(generation, state, info))

        if self.config.use_mock:
            ws: Any = MockWsClient(
                on_message=on_message,
                on_state=on_state,
                user=self.session.user or {"id": "0", "username": self._username()},
                room=room,
                store=self.api if isinstance(self.api, MockApiClient) else None,
            )
        elif not self.session.token:
            self.room_view.set_connection_state("offline", "未获取 JWT，聊天仅本地回显")
            self._system_message(
                "当前登录没有 JWT（PROTOCOL B 阶段才上线）：实时聊天不可用，仅本地回显。"
            )
            return
        else:
            ws = WsClient(
                self.config.effective_ws_url,
                self.session.token,
                on_message=on_message,
                on_state=on_state,
            )
        self._ws = ws
        self._safe_submit(ws.run(), on_error=self._on_ws_run_failed)

    def _stop_ws(
        self,
        leave_room_code: str | None = None,
        *,
        save_canvas: bool = False,
        http_leave_room: Room | None = None,
    ) -> Any:
        """停止 WS；离开房间时先保存画板快照、再发 WS leave_room、最后 HTTP leave。

        D 协议要求「离开前必须 canvas_snapshot_save，否则未保存增量丢失」；
        快照 ack 到达后才断开，避免服务端还在处理保存就摘除会话。
        """
        self._ws_generation += 1
        ws, self._ws = self._ws, None
        if ws is None:
            return None
        snapshot = self._canvas_snapshot_for_save() if save_canvas else None
        if not leave_room_code and not save_canvas and http_leave_room is None:
            return self._safe_submit(ws.close())

        async def _shutdown() -> None:
            if snapshot is not None and getattr(ws, "connected", False):
                try:
                    ack = await ws.save_canvas_snapshot(
                        snapshot["strokes"], snapshot["rev"], snapshot["room_id"], timeout=3.0
                    )
                    if ack is None:
                        logger.warning("画板快照保存超时，未保存增量可能丢失")
                        self.bridge.post(
                            lambda: self._set_status("画板快照保存超时，未保存的增量可能丢失")
                        )
                    else:
                        logger.info("画板快照已保存 rev=%s", ack.get("rev"))
                except Exception:  # noqa: BLE001
                    logger.debug("保存画板快照失败", exc_info=True)
            try:
                if leave_room_code and getattr(ws, "connected", False):
                    await ws.leave_room(leave_room_code)
            except Exception:  # noqa: BLE001
                logger.debug("发送 WS leave_room 失败", exc_info=True)
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                logger.debug("关闭 WS 失败", exc_info=True)
            if http_leave_room is not None:
                try:
                    await self.api.leave_room(http_leave_room.code)
                except Exception:  # noqa: BLE001 - 离开是尽力而为
                    logger.debug("HTTP leave_room 失败", exc_info=True)

        return self._safe_submit(_shutdown())

    def _canvas_snapshot_for_save(self) -> dict[str, Any] | None:
        room = self._current_room
        if room is None or not self._canvas_loaded:
            return None
        strokes = self.room_view.canvas.snapshot_strokes()
        limit_message = check_snapshot_limits(strokes)
        if limit_message:
            self.room_view.set_status(limit_message, error=True)
            self._set_status(limit_message)
            return None
        return {"strokes": strokes, "rev": self._canvas_rev, "room_id": room.id or room.code}

    def _wait_future(self, future: Any, timeout_ms: int = 2500) -> None:
        """在关闭窗口等同步场景里等待后台协程完成（最多 timeout_ms）。"""
        if future is None:
            return
        loop = QEventLoop()
        deadline = time.monotonic() + timeout_ms / 1000.0
        timer = QTimer()
        timer.setInterval(30)

        def _check() -> None:
            if future.done() or time.monotonic() >= deadline:
                loop.quit()

        timer.timeout.connect(_check)
        timer.start()
        loop.exec()
        timer.stop()

    # ---------- 成员兜底（HTTP） ----------
    def _refresh_members_http(self, room: Room, *, fallback: bool) -> None:
        """HTTP 成员兜底：``GET /api/v1/rooms/{room_id_or_code}`` 拉 ``members``。

        WS ``room_joined`` 是权威来源；进入房间时先渲染一次，断线/重连失败时按
        5s 节流刷新，避免 WS 快照丢失时成员区长期空白。
        """
        if room is None or not room.code:
            return
        now = time.monotonic()
        if fallback and now - self._last_members_refresh < 5.0:
            return
        self._last_members_refresh = now
        code = room.code
        self._safe_submit(
            self.api.get_room_detail(code),
            lambda detail: self._on_members_fallback(code, detail, fallback),
            lambda exc: self._on_members_fallback_failed(code, exc, fallback),
        )

    def _on_members_fallback(self, code: str, detail: RoomDetail, fallback: bool) -> None:
        if self._current_room is None or self._current_room.code != code:
            return
        if detail.members:
            self.room_view.set_members(list(detail.members))
        if self._current_room.name == "" and detail.room.name:
            self._current_room = detail.room
            self.room_view.set_room(detail.room)
        if fallback and not self._ws_members_loaded:
            self.room_view.set_status(f"已通过 HTTP 同步成员（{len(detail.members)} 人）")

    def _on_members_fallback_failed(self, code: str, exc: BaseException, fallback: bool) -> None:
        if self._current_room is None or self._current_room.code != code:
            return
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        if fallback and not self._ws_members_loaded:
            self.room_view.set_status(f"成员同步失败：{to_user_message(exc)}", error=True)

    def _on_ws_run_failed(self, exc: BaseException) -> None:
        self.room_view.set_connection_state("error", to_user_message(exc))
        self._system_message(f"实时连接失败：{to_user_message(exc)}")
        if self._current_room is not None:
            self._refresh_members_http(self._current_room, fallback=True)

    def _on_ws_state(self, generation: int, state: str, info: Mapping[str, Any]) -> None:
        if generation != self._ws_generation or self._current_room is None:
            return
        detail = str(info.get("message") or info.get("error") or "")
        if state == "connected":
            self.room_view.set_connection_state("connected", "实时连接已建立")
            self._system_message("实时连接已建立")
            self._set_skill_server_time(info.get("server_time"))
            room = self._current_room
            if self._ws is not None and room is not None:
                self._safe_submit(self._ws.join_room(room.code, self._room_password))
        elif state in ("connecting", "authenticating"):
            self.room_view.set_connection_state(state, detail or "正在连接")
        elif state == "waiting":
            delay = float(info.get("delay") or 0.0)
            self.room_view.set_connection_state("waiting", detail or f"{delay:.0f}s 后重连")
            self.room_view.set_status(f"连接中断，{delay:.0f}s 后自动重连", error=True)
            self._refresh_members_http(self._current_room, fallback=True)
        elif state == "reconnecting":
            self.room_view.set_connection_state("reconnecting", detail)
            if detail:
                self.room_view.set_status(f"重连中：{detail}", error=True)
            self._refresh_members_http(self._current_room, fallback=True)
        elif state == "auth_error":
            self.room_view.set_connection_state("auth_error", detail)
            self._system_message(f"认证失败：{detail or '登录状态无效'}")
            self._refresh_members_http(self._current_room, fallback=True)
        else:
            self.room_view.set_connection_state(state, detail)
            if state in ("error", "stopped"):
                self._refresh_members_http(self._current_room, fallback=True)

    def _on_ws_message(self, generation: int, message: Mapping[str, Any]) -> None:
        if generation != self._ws_generation:
            return
        mtype = message_type(message)
        # H3：定向移出事件即使当前无房间也要提示；带房间匹配逻辑在 handler 内
        if mtype == "room_kicked":
            self._on_room_kicked(message)
            return
        if mtype == "auth_ok":
            self._set_skill_server_time(message.get("server_time"))
            return
        if mtype == "pong":
            self._observe_skill_pong(message)
            return
        if self._current_room is None:
            return
        if mtype == "room_joined":
            payload = message.get("room")
            if isinstance(payload, Mapping):
                room = Room.from_api(payload)
                self._current_room = room
                self.room_view.set_room(room)
            self._history_window_days = parse_history_window_days(message)
            self._set_skill_server_time(message.get("server_time"))
            members = parse_members(message.get("members"))
            if members:
                self._ws_members_loaded = True
                self._last_members_refresh = time.monotonic()
                self.room_view.set_members(members)
            joined_skills = parse_room_joined_skill_states(message)
            if joined_skills:
                self._skills.update_many(joined_skills)
                self.room_view.skill_panel.set_states(self._skills.states())
            self._sync_overlay_states()
            self._on_room_joined_canvas(message.get("canvas_snapshot"))
            self.room_view.set_status("")
        elif mtype == "skill_share_state":
            self._on_skill_share_state(message)
        elif mtype == "skill_share_removed":
            self._on_skill_share_removed(message)
        elif mtype == "room_updated":
            self._on_room_updated(message)
        elif mtype == "room_deleted":
            self._on_room_deleted(message)
        elif mtype == "user_joined":
            user = message.get("user")
            if isinstance(user, Mapping):
                member = Member.from_api(user)
                # 重连后 rev 从 0 重新计数：清掉该用户的旧水位
                self._canvas_last_rev.pop(str(member.id), None)
                self.room_view.add_member(member)
                self._system_message(f"{member.display_name} 加入了房间")
        elif mtype == "user_left":
            user = message.get("user")
            if isinstance(user, Mapping):
                member = Member.from_api(user)
                self.room_view.remove_member(member)
                reason = str(message.get("reason") or "")
                reason_text = {
                    "left": "离开",
                    "disconnected": "断线",
                    "kicked": "被房主移出",
                    "replaced": "被顶号",
                }.get(reason, "")
                suffix = f"（{reason_text}）" if reason_text else ""
                self._system_message(f"{member.display_name} 离开了房间{suffix}")
        elif mtype == "chat_message":
            chat = ChatMessage.from_ws(message)
            if not self._chat_belongs_to_current_room(chat.room_id):
                return  # 只展示当前房间消息
            result = self._timeline.merge_remote(chat)
            if result != "duplicate":
                self._render_chat(stick_to_bottom=(result == "appended"))
        elif mtype == "canvas_op":
            self._on_remote_canvas_op(message)
        elif mtype == "canvas_snapshot_saved":
            return  # WsClient 内部已处理 ack，UI 无需渲染
        elif mtype == "error":
            self._handle_ws_error(message)
        elif mtype in ("heartbeat", "pong", "canvas_snapshot"):
            return
        # 未知类型按协议要求直接忽略

    # ---------- H3：房主移出成员 / room_kicked ----------
    def _on_kick_requested(self, user_id: str, nickname: str) -> None:
        room = self._current_room
        if room is None:
            return
        if not (self._user_id() and str(room.owner_id) == self._user_id()):
            self.room_view.set_status("只有房主可以移出成员", error=True)
            return
        answer = QMessageBox.question(
            self,
            "移出成员",
            f"确定将《{nickname}》移出房间？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.room_view.set_status(f"正在移出《{nickname}》…")
        self._safe_submit(
            self.api.kick_member(room.code or room.id, user_id),
            lambda _result: self._on_member_kicked(room, nickname),
            lambda exc: self._on_kick_failed(exc, nickname),
        )

    def _on_member_kicked(self, room: Room, nickname: str) -> None:
        current = self._current_room
        if current is None or not self._room_matches_my_room(
            current, MyRoom(id=room.id, code=room.code)
        ):
            return
        self.room_view.set_status(f"已移出《{nickname}》")
        self._refresh_members_http(room, fallback=False)

    def _on_kick_failed(self, exc: BaseException, nickname: str) -> None:
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self.room_view.set_status(
            f"移出《{nickname}》失败：{to_user_message(exc)}", error=True
        )

    def _on_room_kicked(self, message: Mapping[str, Any]) -> None:
        by = message.get("by")
        by_name = (
            Member.from_api(by).display_name
            if isinstance(by, Mapping)
            else str(by or "房主")
        )
        text = f"你已被房主《{by_name}》移出房间"
        room = self._current_room
        if room is None:
            self._set_status(text)
            return
        refs = {
            str(value)
            for value in (
                message.get("room_id"),
                message.get("room_code"),
            )
            if value
        }
        if not (
            (room.id and room.id in refs) or (room.code and room.code in refs)
        ):
            self._set_status(text)
            return
        QMessageBox.warning(self, "已被移出房间", text)
        self._stop_ws()
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._set_status(text)
        self._show_rooms()

    # ---------- 干员配置中心 ----------
    def _refresh_operator_config(self, silent: bool = True, dialog=None) -> None:
        manager = self.operator_config

        def success(response) -> None:
            status = int(getattr(response, "status", 0))
            message = ""
            if status == 304:
                message = "已是最新"
            elif status == 200:
                if manager.apply_server_payload(response.payload, getattr(response, "etag", "")):
                    message = f"已更新到版本 {manager.state.version}"
                else:
                    message = "服务器配置异常，已保留本地配置"
            else:
                message = f"服务器返回异常状态 {status}"
            self._apply_operator_catalog()
            if dialog is not None:
                dialog.refresh_operator_catalog(manager.catalog)
                dialog.refresh_operator_config_info(manager)
                dialog.set_config_check_result(message, ok=(status in (200, 304)))
            if status == 200 and not silent:
                self.room_view.set_status(message)

        def error(exc: BaseException) -> None:
            message = "网络失败，请稍后"
            if dialog is not None:
                dialog.set_config_check_result(message, ok=False)
            if not silent:
                self.room_view.set_status(message, error=True)
            logger.debug("干员配置更新失败：%s", exc)

        try:
            coro = self.api.get_operator_config(manager.state.etag)
        except Exception as exc:  # noqa: BLE001
            error(exc)
            return
        self._safe_submit(coro, success, error)

    def _apply_operator_catalog(self) -> None:
        self.operator_catalog = self.operator_config.catalog
        self.room_view.skill_panel.set_operator_catalog(self.operator_catalog)
        self.overlay.catalog = self.operator_catalog
        self._sync_overlay_states()
        self._on_operator_changed()

    # ---------- E4：悬浮窗 / 自动循环 ----------
    def _open_capture_source(self):
        try:
            from capture.sources import open_source

            return open_source()
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)

    def _recognize_auto_frame(self, frame):
        from core.hud_pipeline import recognize_frame
        from core.hud_profile import HudProfile

        profile = HudProfile.from_dict(self.config.hud_profile or {})
        return recognize_frame(frame.image, profile, operator=self._selected_operator())

    def _apply_auto_config(self) -> None:
        enabled = bool(self.config.auto_capture_enabled and self.config.auto_loop_enabled)
        self._auto_controller.interval_ms = int(self.config.auto_sample_ms)
        self._auto_controller.configure(
            enabled=enabled,
            sharing=self._skill_share_enabled,
            room_active=self._current_room is not None,
            interval_ms=int(self.config.auto_sample_ms),
        )
        if enabled and self._skill_share_enabled and self._current_room is not None:
            self._auto_controller.start()

    def _on_auto_status(self, text: str) -> None:
        if hasattr(self, "overlay"):
            self.overlay.set_status(text)
        if self.stack.currentWidget() is self.room_view:
            self.room_view.set_status(text)

    def _on_auto_payload(self, payload) -> None:
        if self._current_room is None:
            return
        operator = self._selected_operator()
        state = SkillState.from_ws(
            {
                "user_id": self._user_id(),
                "nickname": self._username(),
                "operator_id": operator.id if operator else "",
                "operator_name": operator.display_name if operator else "",
                "captured_at": self._server_now_ms(),
                "skills": payload,
            }
        )
        self._self_skill_state = state
        self._skills.update(state)
        self.room_view.skill_panel.upsert(state)
        self._sync_overlay_states()
        if self._skill_share_enabled:
            self._send_skill_state(state)

    def _find_game_window(self):
        try:
            from capture.window import find_window_by_process

            return find_window_by_process()
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _screen_size() -> tuple[int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return (1920, 1080)
        size = screen.size()
        return (int(size.width()), int(size.height()))

    def _apply_overlay_config(self) -> None:
        self.overlay.set_opacity(self.config.overlay_opacity / 100.0)
        self.overlay.set_scale(self.config.overlay_scale)
        if self.config.shortcut_toggle:
            self._toggle_shortcut.setKey(QKeySequence(self.config.shortcut_toggle))
        if self.config.shortcut_edit:
            self._edit_shortcut.setKey(QKeySequence(self.config.shortcut_edit))
        if self.config.overlay_x is not None and self.config.overlay_y is not None:
            self.overlay_controller.fixed_position = (
                int(self.config.overlay_x),
                int(self.config.overlay_y),
            )
        else:
            self.overlay_controller.fixed_position = None
        if self.config.overlay_enabled:
            self.overlay_controller.set_opacity(self.config.overlay_opacity / 100.0)
            self.overlay_controller.start()
            self.overlay_controller.follow(force=True)
        else:
            self.overlay_controller.stop()

    def _toggle_overlay(self) -> None:
        if self.overlay_controller.enabled:
            self.overlay_controller.stop()
            self.room_view.set_status("悬浮窗已隐藏")
        else:
            self.overlay_controller.start()
            self.room_view.set_status(f"悬浮窗：{self.overlay_controller.last_reason or '等待游戏窗口'}")

    def _toggle_overlay_edit(self) -> None:
        enabled = not self.overlay.edit_mode
        self.overlay.set_edit_mode(enabled)
        self.room_view.set_status("悬浮窗编辑模式：可拖动，退出后恢复鼠标穿透" if enabled else "悬浮窗已恢复鼠标穿透")

    def _on_overlay_moved(self, x: int, y: int) -> None:
        self.overlay_controller.fixed_position = (int(x), int(y))
        self.config = replace(self.config, overlay_x=int(x), overlay_y=int(y))
        try:
            save_config(self.config)
        except OSError:
            pass

    def _sync_overlay_states(self) -> None:
        try:
            self.overlay.set_states(self._skills.states(), self.operator_catalog)
        except Exception:  # noqa: BLE001
            pass

    # ---------- E2：技能 CD 共享 ----------
    def _set_skill_server_time(self, server_time: Any) -> None:
        try:
            server = int(server_time)
        except (TypeError, ValueError):
            return
        if server <= 0:
            return
        self._server_clock.observe(server, now_ms(), time.monotonic() * 1000)

    def _observe_skill_pong(self, message: Mapping[str, Any]) -> None:
        server_time = message.get("server_time")
        client_sent = message.get("_client_sent_ms") or message.get("ts")
        if server_time is None or client_sent is None:
            return
        try:
            self._server_clock.observe_rtt(
                int(server_time),
                int(client_sent),
                now_ms(),
            )
        except (TypeError, ValueError):
            return

    def _server_now_ms(self) -> int:
        return int(self._server_clock.now_ms())

    def _on_skill_share_state(self, message: Mapping[str, Any]) -> None:
        state = SkillState.from_ws(message)
        if not state.user_id:
            return
        # captured_at 缺失时用本机估算的服务器时间兜底
        if not state.captured_at:
            state = replace(state, captured_at=self._server_now_ms())
        self._skills.update(state)
        self.room_view.skill_panel.upsert(state)
        self._sync_overlay_states()

    def _on_skill_share_removed(self, message: Mapping[str, Any]) -> None:
        user_id = str(message.get("user_id") or "")
        if not user_id:
            return
        self._skills.remove(user_id)
        self.room_view.skill_panel.remove(user_id)
        self._sync_overlay_states()

    def _on_simulate_skill(self) -> None:
        if self._current_room is None:
            return
        state = self._build_simulated_skill()
        self._self_skill_state = state
        self._skills.update(state)
        self.room_view.skill_panel.upsert(state)
        self._sync_overlay_states()
        if self._skill_share_enabled:
            self._send_skill_state(state)
        else:
            self.room_view.set_status("已模拟本地技能状态（技能共享未开启，未上报）")

    def _selected_operator(self) -> Operator | None:
        operator = self.operator_catalog.get(self.config.operator_id)
        if operator is not None:
            return operator
        return next(iter(self.operator_catalog), None)

    def _build_simulated_skill(self) -> SkillState:
        self._skill_sim_index = (self._skill_sim_index + 1) % 3
        index = self._skill_sim_index
        operator = self._selected_operator()
        if operator is not None:
            skills: list[dict[str, Any]] = []
            for slot in (0, 1, 2):
                meta = operator.skill(slot)
                if meta is None:
                    skills.append({"slot": slot, "state": "unknown"})
                    continue
                if not meta.cd_known:
                    # 配置缺 CD：不参与倒计时/上报数值，只报 unknown
                    skills.append({"slot": slot, "state": "unknown"})
                    continue
                if index == 0:
                    item: dict[str, Any] = {
                        "slot": slot,
                        "state": "ready",
                        "charges": meta.max_charges,
                        "max_charges": meta.max_charges,
                        "pct": 100,
                    }
                elif index == 1:
                    item = {
                        "slot": slot,
                        "state": "charging",
                        "remaining_ms": meta.total_cd_ms//2,
                        "charges": max(0, meta.max_charges - 1),
                        "max_charges": meta.max_charges,
                        "pct": 60 if slot == 0 else 40,
                    }
                else:
                    item = {
                        "slot": slot,
                        "state": "charging" if slot != 0 else "ready",
                        "remaining_ms": meta.total_cd_ms//4 if slot != 0 else 0,
                        "charges": 0 if slot != 0 else meta.max_charges,
                        "max_charges": meta.max_charges,
                        "pct": 100 if slot == 0 else 25,
                    }
                skills.append(item)
            return SkillState.from_ws(
                {
                    "user_id": self._user_id(),
                    "nickname": self._username(),
                    "operator_id": operator.id,
                    "operator_name": operator.display_name,
                    "captured_at": self._server_now_ms(),
                    "skills": skills,
                }
            )
        # 没有干员配置时保留旧的手动模拟数据
        if index == 0:
            skills = [
                {"slot": 0, "state": "ready", "pct": 100},
                {"slot": 1, "state": "ready", "charges": 2, "max_charges": 2},
                {"slot": 2, "state": "ready", "charges": 1, "max_charges": 1},
            ]
        elif index == 1:
            skills = [
                {"slot": 0, "state": "charging", "pct": 60, "remaining_ms": 30000},
                {"slot": 1, "state": "charging", "charges": 1, "max_charges": 2, "remaining_ms": 12000},
                {"slot": 2, "state": "charging", "charges": 0, "max_charges": 1, "remaining_ms": 25000},
            ]
        else:
            skills = [
                {"slot": 0, "state": "ready", "pct": 100},
                {"slot": 1, "state": "charging", "charges": 0, "max_charges": 1, "remaining_ms": 5000},
                {"slot": 2, "state": "unknown"},
            ]
        return SkillState.from_ws(
            {
                "user_id": self._user_id(),
                "nickname": self._username(),
                "operator": "模拟干员",
                "captured_at": self._server_now_ms(),
                "skills": skills,
            }
        )

    def _on_hud_capture(self) -> None:
        """E3b：一次性抓取游戏窗口 + 识别技能栏，更新自己的状态/上报。"""
        if self._current_room is None:
            return
        try:
            from capture.sources import open_source
            from core.hud_pipeline import recognize_frame, to_skill_state
            from core.hud_profile import HudProfile

            source, message = open_source()
            if source is None:
                self.room_view.set_status(f"HUD 识别不可用：{message}", error=True)
                return
            try:
                frame = source.grab()
            finally:
                source.close()
            if frame is None:
                self.room_view.set_status("HUD 识别失败：未取到游戏画面（最小化/遮挡？）", error=True)
                return
            profile = HudProfile.from_dict(self.config.hud_profile or {})
            operator = self._selected_operator()
            recognized = recognize_frame(frame.image, profile, operator=operator)
            state = to_skill_state(
                recognized,
                user_id=self._user_id(),
                nickname=self._username(),
                captured_at=self._server_now_ms(),
                operator_id=operator.id if operator is not None else "",
                operator_name=operator.display_name if operator is not None else "",
            )
            self._self_skill_state = state
            self._skills.update(state)
            self.room_view.skill_panel.upsert(state)
            if self._skill_share_enabled:
                self._send_skill_state(state)
            count = sum(1 for slot in state.slots.values() if slot.state != "unknown")
            self.room_view.set_status(f"HUD 识别完成：{count}/3 槽有结果")
        except Exception as exc:  # noqa: BLE001
            logger.warning("HUD 识别失败", exc_info=True)
            self.room_view.set_status(f"HUD 识别失败：{exc}", error=True)

    def _on_skill_sharing_toggled(self, enabled: bool) -> None:
        self._skill_share_enabled = bool(enabled)
        if hasattr(self, "_auto_controller"):
            self._apply_auto_config()
        if not enabled:
            self._send_skill_off()
            self.room_view.set_status("技能共享已关闭")
            return
        if self._current_room is None:
            self.room_view.skill_panel.set_sharing(False)
            self._skill_share_enabled = False
            return
        if self._self_skill_state is None:
            self._self_skill_state = self._build_simulated_skill()
            self._skills.update(self._self_skill_state)
            self.room_view.skill_panel.upsert(self._self_skill_state)
        self._send_skill_state(self._self_skill_state)
        self.room_view.set_status("技能共享已开启（本地限频 2 次/秒）")

    def _send_skill_state(self, state: SkillState) -> None:
        room = self._current_room
        if room is None:
            return
        if self._ws is None or not getattr(self._ws, "connected", False):
            self.room_view.set_status("实时连接未建立，技能状态未上报", error=True)
            return
        if not self._skill_throttle.allow(now_ms()):
            self.room_view.set_status("技能上报过快（本地限频 2 次/秒）", error=True)
            return
        captured_at = clean_captured_at(self._server_now_ms())
        if captured_at is None:
            self.room_view.set_status("技能上报失败：captured_at 非法", error=True)
            return
        state = replace(state, captured_at=captured_at)
        self._self_skill_state = state
        self._skills.update(state)
        self.room_view.skill_panel.upsert(state)
        self._sync_overlay_states()
        payload = build_payload_from_state(state)
        valid, reason = validate_payload(payload)
        if not valid:
            logger.warning("技能 payload 自检失败，已取消发送：%s", reason)
            self.room_view.set_status(f"技能上报已取消：{reason}", error=True)
            return
        self._safe_submit(
            self._ws.send_skill_update(
                room.id or room.code,
                captured_at,
                payload,
                state.operator_id,
                state.operator,
            )
        )

    def _send_skill_off(self) -> None:
        room = self._current_room
        if room is None or self._ws is None or not getattr(self._ws, "connected", False):
            return
        self._safe_submit(self._ws.send_skill_off(room.id or room.code))

    # ---------- 聊天 ----------
    def _system_message(self, text: str) -> None:
        self._timeline.add_system(str(text))
        self._render_chat()

    # ---------- F-c4：房间事件 ----------
    def _on_room_updated(self, message: Mapping[str, Any]) -> None:
        room = self._current_room
        if room is None:
            return
        payload = message.get("room")
        if isinstance(payload, Mapping):
            updated = Room.from_api(payload)
        else:
            updated = replace(
                room,
                name=str(message.get("name") or room.name),
                has_password=bool(message.get("has_password", room.has_password)),
            )
        self._current_room = updated
        self.room_view.set_room(updated)
        self.room_view.set_user(self._username(), self._user_id())
        self.room_view.set_status("房间信息已更新")
        self._set_status(f"房间「{updated.name}」已更新")

    def _on_room_deleted(self, message: Mapping[str, Any] | None = None) -> None:
        room = self._current_room
        refs = {
            str(value)
            for value in (
                (message or {}).get("room_id"),
                (message or {}).get("id"),
                (message or {}).get("code"),
                room.id if room is not None else "",
                room.code if room is not None else "",
            )
            if value
        }
        for mine in list(self.room_list_view.my_rooms.rooms):
            if mine.key in refs or mine.id in refs or mine.code in refs:
                self.room_list_view.my_rooms.remove_room(mine.key)
        self._update_my_rooms_tab()
        self._system_message("房间已被房主删除")
        self._stop_ws()
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._set_status("房间已被删除，已返回大厅")
        self._show_rooms()

    # ---------- 设置（含个人资料） ----------
    def _on_profile(self) -> None:
        self._open_settings(start_tab=1)

    def _on_nickname_save(self, dialog: SettingsDialog, nickname: str) -> None:
        self._safe_submit(
            self.api.update_nickname(nickname),
            lambda data: self._on_nickname_saved(dialog, data, nickname),
            lambda exc: self._update_profile_dialog(
                dialog, "nickname", f"昵称修改失败：{to_user_message(exc)}", False
            ),
        )

    def _on_nickname_saved(self, dialog: SettingsDialog, data: Any, nickname: str) -> None:
        user = dict(data) if isinstance(data, Mapping) else {}
        user.setdefault("nickname", nickname)
        self.session.update_user(user)
        self.room_list_view.set_user(self._username())
        self.room_view.set_user(self._username(), self._user_id())
        self.room_view.update_member(self._user_id(), self._username())
        if self._timeline.rename_sender(self._user_id(), self._username()):
            self._render_chat()
        self._update_profile_dialog(dialog, "nickname", "昵称已更新", True)
        self._set_status(f"昵称已更新为：{self._username()}")

    def _on_password_change(self, dialog: SettingsDialog, old_password: str, new_password: str) -> None:
        self._safe_submit(
            self.api.change_password(old_password, new_password),
            lambda _result: self._on_password_changed(dialog),
            lambda exc: self._update_profile_dialog(
                dialog, "password", to_user_message(exc), False
            ),
        )

    def _on_password_changed(self, dialog: SettingsDialog) -> None:
        self._update_profile_dialog(
            dialog, "password", "密码已修改，当前登录保持有效", True
        )
        # H2：改密成功后清除本地保存的密码（账号保留）
        self.saved_logins.clear_password(self._account())
        self._refresh_saved_login_view()
        self._set_status("密码已修改，当前登录保持有效（已清除本地保存的密码）")

    @staticmethod
    def _update_profile_dialog(
        dialog: SettingsDialog, kind: str, text: str, ok: bool
    ) -> None:
        try:
            if kind == "nickname":
                dialog.set_nickname_result(text, ok)
            else:
                dialog.set_password_result(text, ok)
        except RuntimeError:  # 对话框已关闭
            logger.debug("设置对话框已关闭，忽略个人资料结果")

    def _render_chat(self, *, stick_to_bottom: bool = False) -> None:
        self.room_view.set_chat_entries(list(self._timeline.entries), stick_to_bottom=stick_to_bottom)

    def _chat_belongs_to_current_room(self, room_id: str) -> bool:
        if not room_id:
            return True
        room = self._current_room
        if room is None:
            return False
        return str(room_id) in {str(room.id), str(room.code)}

    def _load_chat_history(self, room: Room, *, initial: bool = False) -> None:
        if self._chat_loading:
            return
        if not initial and not self._chat_has_more:
            return
        if self._current_room is None or self._current_room.code != room.code:
            return
        self._chat_loading = True
        before = None if initial else self._chat_next_before
        if initial:
            self.room_view.set_status("正在加载聊天记录…")
        self._safe_submit(
            self.api.get_messages(room.code, before=before, limit=50),
            lambda page: self._on_chat_history(room.code, page, initial),
            lambda exc: self._on_chat_history_failed(room.code, exc, initial),
        )

    def _on_chat_history(self, code: str, page: Any, initial: bool) -> None:
        self._chat_loading = False
        if self._current_room is None or self._current_room.code != code:
            return
        added = self._timeline.add_page(page)
        self._chat_has_more = bool(page.has_more)
        self._chat_next_before = page.next_before
        if initial and (page.window_days or page.truncated):
            self._history_window_days = page.window_days or self._history_window_days
        self._render_chat(stick_to_bottom=initial)
        if initial:
            window_days = page.window_days or self._history_window_days
            if window_days:
                self.room_view.set_status(f"仅显示最近 {window_days} 天消息")
            elif page.truncated:
                self.room_view.set_status("仅显示最近一段时间的消息（历史已截断）")
            else:
                self.room_view.set_status(
                    f"已加载 {len(page.messages)} 条历史消息" if page.messages else ""
                )
        elif added:
            self.room_view.set_status(f"已加载 {added} 条更早消息")

    def _on_chat_history_failed(self, code: str, exc: BaseException, initial: bool) -> None:
        self._chat_loading = False
        if self._current_room is None or self._current_room.code != code:
            return
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        if initial and self._timeline.is_empty:
            self._chat_has_more = True  # 允许滚动到顶部时重试
        self.room_view.set_status(f"聊天记录加载失败：{to_user_message(exc)}", error=True)

    def _on_history_requested(self) -> None:
        room = self._current_room
        if room is not None and not self._chat_loading and self._chat_has_more:
            self._load_chat_history(room, initial=False)

    def _on_chat_submitted(self, text: str) -> None:
        text = str(text).strip()
        if not text:
            return
        if len(text) > 2000:
            self.room_view.set_status("消息最多 2000 字，请精简后再发", error=True)
            self.room_view.append_chat_input(text)
            return
        room = self._current_room
        if room is None:
            return
        if self._ws is None or not getattr(self._ws, "connected", False):
            self.room_view.set_status("实时连接未建立，消息未发送", error=True)
            self.room_view.append_chat_input(text)
            return
        client_msg_id = make_client_msg_id()
        self._timeline.add_pending(
            client_msg_id, self._username(), text, now_ms(), self._user_id()
        )
        self._render_chat(stick_to_bottom=True)
        self._send_chat(client_msg_id, text, room)

    def _send_chat(self, client_msg_id: str, text: str, room: Room) -> None:
        room_ref = room.id or room.code
        self._safe_submit(
            self._ws.send_chat(text, client_msg_id, room_ref),
            lambda sent: self._on_chat_sent(client_msg_id, sent),
            lambda exc: self._fail_chat(client_msg_id, to_user_message(exc)),
        )
        QTimer.singleShot(10_000, lambda: self._on_chat_timeout(client_msg_id))

    def _on_chat_sent(self, client_msg_id: str, sent_id: Any) -> None:
        if not sent_id:
            self._fail_chat(client_msg_id, "实时连接未就绪")

    def _on_chat_timeout(self, client_msg_id: str) -> None:
        entry = self._timeline.get(client_msg_id)
        if entry is not None and entry.is_pending:
            self._fail_chat(client_msg_id, "发送超时（未收到服务端广播）")

    def _fail_chat(self, client_msg_id: str, reason: str) -> None:
        if not self._timeline.fail(client_msg_id, reason):
            return
        entry = self._timeline.get(client_msg_id)
        self._render_chat()
        self.room_view.set_status(f"发送失败：{reason}（双击失败消息重试）", error=True)
        if entry is not None:
            self.room_view.append_chat_input(entry.content)

    def _on_retry_chat(self, client_msg_id: str) -> None:
        room = self._current_room
        if room is None:
            return
        entry = self._timeline.retry(client_msg_id)
        if entry is None:
            return
        if self._ws is None or not getattr(self._ws, "connected", False):
            self._fail_chat(client_msg_id, "实时连接未建立")
            return
        self._render_chat(stick_to_bottom=True)
        self._send_chat(client_msg_id, entry.content, room)

    # ---------- 画板（D） ----------
    def _on_room_joined_canvas(self, snapshot_payload: Any) -> None:
        room = self._current_room
        if room is None:
            return
        self._canvas_rev = 0
        self._canvas_last_rev.clear()
        self._canvas_queue.clear()
        if isinstance(snapshot_payload, Mapping):
            snapshot = parse_canvas_snapshot(snapshot_payload)
            self.room_view.canvas.load_snapshot(snapshot.strokes)
            self._canvas_loaded = True
            if snapshot.strokes:
                return
        # 字段缺失/为空：HTTP fallback（可能仍是空板）
        self._load_canvas_http(room)

    def _load_canvas_http(self, room: Room) -> None:
        code = room.code
        self._safe_submit(
            self.api.get_canvas(code),
            lambda snapshot: self._on_canvas_http(code, snapshot),
            lambda exc: self._on_canvas_http_failed(code, exc),
        )

    def _on_canvas_http(self, code: str, snapshot: Any) -> None:
        if self._current_room is None or self._current_room.code != code:
            return
        self.room_view.canvas.load_snapshot(snapshot.strokes)
        self._canvas_loaded = True
        self._canvas_rev = 0
        self._canvas_last_rev.clear()
        if snapshot.strokes:
            self.room_view.set_status(f"已加载画板（{len(snapshot.strokes)} 笔）")

    def _on_canvas_http_failed(self, code: str, exc: BaseException) -> None:
        if self._current_room is None or self._current_room.code != code:
            return
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self._canvas_loaded = False
        self.room_view.set_status(f"画板加载失败：{to_user_message(exc)}", error=True)

    def _on_remote_canvas_op(self, message: Mapping[str, Any]) -> None:
        if not self._chat_belongs_to_current_room(str(message.get("room_id") or "")):
            return
        try:
            rev = int(message.get("rev", 0))
        except (TypeError, ValueError):
            rev = 0
        user_id = str(message.get("user_id") or "")
        last_rev = self._canvas_last_rev.get(user_id)
        # 同 user 的 rev 单调递增；rev=0 视为重连后的新连接（重置水位）
        if last_rev is not None and rev <= last_rev and rev != 0:
            return
        self._canvas_last_rev[user_id] = rev
        try:
            self.room_view.canvas.apply_remote_op(message.get("op"))
        except CanvasError as exc:
            self.room_view.set_status(f"已忽略非法画板操作：{exc}", error=True)

    def _on_canvas_strokes(self, ops: list[dict[str, Any]]) -> None:
        if self._current_room is None:
            return
        if not self._canvas_loaded:
            self._canvas_loaded = True
        for op in ops:
            self._canvas_queue.append(op)
        self._drain_canvas_queue()

    def _on_canvas_clear_requested(self) -> None:
        if self._current_room is None:
            return
        if not self._canvas_loaded:
            self._canvas_loaded = True
        self._canvas_queue.append(make_clear_op())
        self._drain_canvas_queue()

    def _drain_canvas_queue(self) -> None:
        room = self._current_room
        if room is None:
            self._canvas_queue.clear()
            return
        ws = self._ws
        if ws is None or not getattr(ws, "connected", False):
            self._canvas_queue.clear()
            self.room_view.set_status("实时连接未建立，画板改动仅本地可见", error=True)
            return
        while self._canvas_queue:
            wait = self._canvas_limiter.wait_seconds()
            if wait > 0:
                break
            self._canvas_limiter.allow()
            op = self._canvas_queue.pop(0)
            rev = self._canvas_rev
            self._canvas_rev += 1
            self._safe_submit(
                ws.send_canvas_op(op, rev, room.id or room.code),
                on_error=lambda exc: self.room_view.set_status(
                    f"画板同步失败：{to_user_message(exc)}", error=True
                ),
            )
        if self._canvas_queue:
            delay = max(30, int(self._canvas_limiter.wait_seconds() * 1000) + 20)
            QTimer.singleShot(delay, self._drain_canvas_queue)

    def _handle_ws_error(self, message: Mapping[str, Any]) -> None:
        code = str(message.get("code") or message.get("error_code") or "")
        text = str(message.get("message") or code or "未知错误")
        self._timeline.add_system(f"服务端错误：{text}")
        chat_reason = _CHAT_ERROR_REASONS.get(code)
        if chat_reason:
            failed = self._timeline.fail_all_pending(chat_reason)
            if failed:
                self.room_view.append_chat_input(failed[-1].content)
                self.room_view.set_status(f"发送失败：{chat_reason}", error=True)
        self._render_chat()

        canvas_reason = _CANVAS_ERROR_REASONS.get(code)
        if canvas_reason and code not in ("ROOM_CLOSED",):
            self.room_view.set_status(canvas_reason, error=True)
        if code == "RATE_LIMITED" and self._canvas_queue:
            QTimer.singleShot(700, self._drain_canvas_queue)
        if code == "ROOM_CLOSED":
            self.room_view.set_status("房间已关闭，即将返回房间列表", error=True)
            QTimer.singleShot(1200, self._on_room_closed)

    def _on_room_closed(self) -> None:
        """房间被关闭：不再尝试保存/HTTP leave（会话已被摘除），直接回大厅。"""
        room = self._current_room
        self._stop_ws()
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._set_status(f"房间 {room.code if room else ''} 已关闭")
        self._show_rooms()

    def _clear_room_state(self) -> None:
        self._timeline.clear()
        self._chat_has_more = False
        self._chat_next_before = None
        self._chat_loading = False
        self._canvas_rev = 0
        self._canvas_last_rev.clear()
        self._canvas_loaded = False
        self._canvas_queue.clear()
        self._skills.clear()
        self._self_skill_state = None
        self._skill_share_enabled = False
        if hasattr(self, "_auto_controller"):
            self._auto_controller.stop()
        self.room_view.skill_panel.clear()
        self.room_view.skill_panel.set_sharing(False)
        self._sync_overlay_states()

    def _on_leave_room(self) -> None:
        room = self._current_room
        save_canvas = True
        if room is not None and self._canvas_loaded and self._canvas_snapshot_for_save() is None:
            answer = QMessageBox.warning(
                self,
                "画布已满",
                "画布已超过 5000 笔或 512KB，无法保存快照。\n"
                "请先清空画板；仍要离开则本次未保存的增量会丢失。是否继续离开？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            save_canvas = False
        if self._skill_share_enabled:
            self._send_skill_off()
            self._skill_share_enabled = False
        self._stop_ws(
            room.code if room is not None else None,
            save_canvas=save_canvas,
            http_leave_room=room,
        )
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._show_rooms()

    # ---------- 设置 ----------
    def _on_operator_changed(self) -> None:
        """设置页切换干员后：刷新自己的模拟状态；开启共享时立即按新干员上报。"""
        self._self_skill_state = None
        if self._current_room is None:
            return
        state = self._build_simulated_skill()
        self._self_skill_state = state
        self._skills.update(state)
        self.room_view.skill_panel.upsert(state)
        self._sync_overlay_states()
        if self._skill_share_enabled:
            self._send_skill_state(state)
        else:
            self.room_view.set_status(f"已切换干员：{state.operator or state.operator_id}")

    def _on_settings(self) -> None:
        self._open_settings(start_tab=0)

    def _open_settings(self, start_tab: int = 0) -> None:
        dialog = SettingsDialog(self.config, self, self.operator_catalog, self.operator_config)
        dialog.config_check_requested.connect(
            lambda: self._refresh_operator_config(silent=False, dialog=dialog)
        )
        dialog.test_requested.connect(
            lambda server_text, ws_text: self._on_test_connection(dialog, server_text, ws_text)
        )
        dialog.nickname_save_requested.connect(
            lambda nickname: self._on_nickname_save(dialog, nickname)
        )
        dialog.password_change_requested.connect(
            lambda old_password, new_password: self._on_password_change(
                dialog, old_password, new_password
            )
        )
        dialog.set_account(self._account())
        dialog.set_nickname(self.session.nickname or self.session.username)
        dialog.set_overlay_status(self.overlay_controller.last_reason or "未附加")
        dialog.set_server_migrated(self.config.server_migrated)
        dialog.tabs.setCurrentIndex(0 if start_tab <= 0 else 1)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_config = dialog.config_result()
        old_operator_id = self.config.operator_id
        try:
            saved_path = save_config(new_config)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法写入配置文件：{exc}")
            return

        identity_changed = (
            new_config.server_url != self.config.server_url
            or new_config.ws_url != self.config.ws_url
            or new_config.use_mock != self.config.use_mock
        )
        operator_changed = new_config.operator_id != old_operator_id
        self.config = new_config
        if operator_changed:
            self._on_operator_changed()
        self._apply_overlay_config()
        self._apply_auto_config()
        self._refresh_status_bar()
        self.login_view.set_server_text(new_config.server_url, new_config.mode_label)
        self.room_list_view.set_mode(new_config.use_mock, new_config.server_url)
        self.session.set_persist_token(new_config.persist_token)

        if identity_changed:
            room = self._current_room
            self._stop_ws(
                room.code if room is not None else None,
                save_canvas=room is not None,
                http_leave_room=room,
            )
            self._current_room = None
            self._clear_room_state()
            self.session.clear()
            self.api = self._build_api()
            self._show_login()
            self.login_view.show_success(f"配置已保存到 {saved_path}，请重新登录")
            return

        self.api = self._build_api()
        if self.stack.currentWidget() is self.room_view:
            self._on_leave_room()
        elif self.session.is_logged_in:
            self._show_rooms()
        else:
            self._show_login()
        self._set_status(f"配置已保存：{saved_path}")

    # ---------- 连通性测试 ----------
    def _on_test_connection(self, dialog: SettingsDialog, server_text: str, ws_text: str) -> None:
        try:
            server_url = normalize_server_url(server_text)
            if ws_text.strip():
                normalize_ws_url(ws_text)  # 只为校验格式，WS 不作为本次探测目标
        except ConfigError as exc:
            self._update_test_dialog(dialog, f"配置错误：{exc}", False)
            return
        dialog.set_testing(True)
        self._safe_submit(
            _run_connection_check(server_url, self.session.token, timeout=8.0),
            lambda check: self._update_test_dialog(dialog, check.format_text(), check.ok),
            lambda exc: self._update_test_dialog(dialog, f"测试失败：{to_user_message(exc)}", False),
        )

    @staticmethod
    def _update_test_dialog(dialog: SettingsDialog, text: str, ok: bool) -> None:
        try:
            dialog.set_test_result(text, ok)
        except RuntimeError:  # 对话框已关闭，忽略迟到的测试回调
            logger.debug("设置对话框已关闭，忽略连通性测试结果")

    # ---------- F-c4：房主房间管理 ----------
    def _on_room_settings(self) -> None:
        room = self._current_room
        if room is None:
            return
        if not (self._user_id() and str(room.owner_id) == self._user_id()):
            self.room_view.set_status("只有房主可以修改房间设置", error=True)
            return
        dialog = RoomSettingsDialog(room, self)
        dialog.rename_requested.connect(lambda name: self._on_room_rename(dialog, name))
        dialog.password_change_requested.connect(
            lambda password: self._on_room_password_change(dialog, password)
        )
        dialog.delete_requested.connect(lambda: self._on_room_delete(dialog))
        dialog.exec()

    def _on_room_rename(self, dialog: RoomSettingsDialog, name: str) -> None:
        room = self._current_room
        if room is None:
            return
        self._safe_submit(
            self.api.update_room(room.code, name=name),
            lambda updated: self._on_room_renamed(dialog, updated),
            lambda exc: self._room_dialog_failure(dialog, "rename", exc),
        )

    def _on_room_renamed(self, dialog: RoomSettingsDialog, updated: Room) -> None:
        self._current_room = updated
        self.room_view.set_room(updated)
        self._safe_room_dialog(dialog, "rename", "房间名称已更新", True)
        dialog.update_room(updated)
        self._set_status(f"房间名称已更新：{updated.name}")

    def _on_room_password_change(self, dialog: RoomSettingsDialog, password: str) -> None:
        room = self._current_room
        if room is None:
            return
        self._safe_submit(
            self.api.update_room(room.code, password=password),
            lambda updated: self._on_room_password_changed(dialog, updated),
            lambda exc: self._room_dialog_failure(dialog, "password", exc),
        )

    def _on_room_password_changed(self, dialog: RoomSettingsDialog, updated: Room) -> None:
        self._current_room = updated
        self.room_view.set_room(updated)
        self._safe_room_dialog(dialog, "password", "房间密码已更新", True)
        dialog.update_room(updated)
        self._set_status("房间密码已更新")

    def _on_room_delete(self, dialog: RoomSettingsDialog) -> None:
        room = self._current_room
        if room is None:
            return
        self._safe_submit(
            self.api.delete_room(room.code),
            lambda _result: self._on_room_deleted_by_owner(dialog),
            lambda exc: self._room_dialog_failure(dialog, "delete", exc),
        )

    def _on_room_deleted_by_owner(self, dialog: RoomSettingsDialog) -> None:
        try:
            dialog.accept()
        except RuntimeError:
            pass
        self._stop_ws()
        self._current_room = None
        self._room_password = None
        self._clear_room_state()
        self._set_status("房间已删除，已返回大厅")
        self._show_rooms()

    def _room_dialog_failure(self, dialog: RoomSettingsDialog, kind: str, exc: BaseException) -> None:
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        message = to_user_message(exc)
        if isinstance(exc, ApiError) and exc.kind == ErrorKind.FORBIDDEN:
            message = "只有房主才能执行该操作"
        self._safe_room_dialog(dialog, kind, f"操作失败：{message}", False)

    @staticmethod
    def _safe_room_dialog(
        dialog: RoomSettingsDialog, kind: str, text: str, ok: bool
    ) -> None:
        try:
            if kind == "rename":
                dialog.set_rename_result(text, ok)
            elif kind == "password":
                dialog.set_password_result(text, ok)
            else:
                dialog.set_delete_result(text, ok)
        except RuntimeError:  # 对话框已关闭
            logger.debug("房间设置对话框已关闭，忽略结果")

    # ---------- 关闭 ----------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 覆盖
        try:
            self._stop_lobby_timer()
            room = self._current_room
            save_canvas = room is not None
            if save_canvas and self._canvas_loaded and self._canvas_snapshot_for_save() is None:
                QMessageBox.warning(
                    self,
                    "画布已满",
                    "画布已超过 5000 笔或 512KB，无法保存快照；本次关闭不会保存未保存的增量。",
                )
                save_canvas = False
            shutdown = self._stop_ws(
                room.code if room is not None else None,
                save_canvas=save_canvas,
                http_leave_room=room,
            )
            # 等待「画板快照保存 → WS leave → 关闭」完成，避免未保存增量丢失
            self._wait_future(shutdown, 3000)
            self._safe_submit(self.api.close())
            self._current_room = None
            self._clear_room_state()
        finally:
            self.bridge.stop()
            super().closeEvent(event)


async def _run_connection_check(server_url: str, token: str | None, timeout: float = 8.0) -> Any:
    """用临时 ApiClient 做一次连通性测试，结束后关闭连接池。"""
    client = ApiClient(server_url, token_provider=lambda: token, timeout=timeout)
    try:
        return await client.check_connection()
    finally:
        await client.close()
