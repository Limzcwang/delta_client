"""主窗口：QStackedWidget 切换 登录 -> 房间大厅 -> 房间内页，并负责网络编排。"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from config import AppConfig, ConfigError, normalize_server_url, normalize_ws_url, save_config
from core.chat import ChatTimeline
from core.errors import ApiError, ErrorKind, to_user_message
from core.models import ChatMessage, Member, Room, RoomDetail, now_ms, parse_members
from core.protocol import extract_token, extract_user, make_client_msg_id, message_type
from net.api_client import ApiClient, LoginResult
from net.mock_backend import MockApiClient, MockWsClient
from net.ws_client import WsClient
from state.session import Session, default_session_path
from ui.async_bridge import AsyncBridge
from ui.dialogs import CreateRoomDialog, JoinRoomDialog, SettingsDialog
from ui.login_view import LoginView
from ui.room_list_view import RoomListView
from ui.room_view import RoomView

logger = logging.getLogger(__name__)

#: 聊天相关 WS 错误 -> 面向用户的失败原因（这些错误需要把 pending 消息标红）
_CHAT_ERROR_REASONS: dict[str, str] = {
    "RATE_LIMITED": "发送过快，请稍后再试",
    "INVALID_MESSAGE": "消息内容不合法（1-2000 字）",
    "NOT_ROOM_MEMBER": "你不在该房间中，请重新加入",
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

        self.setWindowTitle("Delta Client - 三角洲行动队友房间")
        self.resize(1200, 780)
        self.setMinimumSize(1020, 680)
        self._build_ui()
        self._wire_views()
        self._refresh_status_bar()

        if self.session.is_logged_in:
            self._show_rooms()
            self._set_status("已恢复上次登录状态")
        else:
            self._show_login()

    # ---------- 构建 ----------
    def _build_ui(self) -> None:
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_view = LoginView()
        self.room_list_view = RoomListView()
        self.room_view = RoomView()
        self.stack.addWidget(self.login_view)
        self.stack.addWidget(self.room_list_view)
        self.stack.addWidget(self.room_view)

        self._server_label = QLabel()
        self._server_label.setObjectName("Muted")
        self.statusBar().addPermanentWidget(self._server_label)

    def _wire_views(self) -> None:
        self.login_view.login_requested.connect(self._on_login)
        self.login_view.register_requested.connect(self._on_register)
        self.login_view.settings_requested.connect(self._on_settings)

        self.room_list_view.refresh_requested.connect(self._refresh_rooms)
        self.room_list_view.create_requested.connect(self._on_create_room)
        self.room_list_view.join_requested.connect(self._on_join_room)
        self.room_list_view.logout_requested.connect(self._on_logout)
        self.room_list_view.settings_requested.connect(self._on_settings)

        self.room_view.leave_requested.connect(self._on_leave_room)
        self.room_view.chat_submitted.connect(self._on_chat_submitted)
        self.room_view.history_requested.connect(self._on_history_requested)
        self.room_view.retry_requested.connect(self._on_retry_chat)

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
        return self.session.username or "未知用户"

    def _set_status(self, message: str) -> None:
        self.statusBar().showMessage(str(message), 8000)

    def _refresh_status_bar(self) -> None:
        self._server_label.setText(
            f"服务器：{self.config.server_url}  ·  模式：{self.config.mode_label}"
        )

    def _safe_submit(self, coro: Any, on_success=None, on_error=None) -> None:
        try:
            self.bridge.submit(coro, on_success, on_error)
        except RuntimeError:  # 窗口关闭后不再提交
            logger.debug("异步桥已停止，忽略任务提交")

    def _show_login(self, message: str = "") -> None:
        self.login_view.set_server_text(self.config.server_url, self.config.mode_label)
        self.login_view.set_busy(False)
        self.login_view.set_mode("login")
        if message:
            self.login_view.show_error(message)
        self.stack.setCurrentWidget(self.login_view)
        self.login_view.focus_first()

    def _show_rooms(self) -> None:
        self.room_list_view.set_user(self._username())
        self.room_list_view.set_mode(self.config.use_mock, self.config.server_url)
        self.stack.setCurrentWidget(self.room_list_view)
        self._refresh_rooms()

    # ---------- 认证 ----------
    def _on_login(self, username: str, password: str) -> None:
        self.login_view.set_busy(True)
        self.login_view.hide_messages()
        self._safe_submit(
            self.api.login(username, password),
            self._on_login_success,
            self._on_login_failure,
        )

    def _on_login_success(self, result: LoginResult) -> None:
        self.login_view.set_busy(False)
        self.session.set_login(result.token, result.user)
        if result.token:
            self._set_status(f"登录成功：{self._username()}")
        else:
            # 后端 B 阶段前 /api/users/login 不返回 JWT，保留兼容分支
            self._set_status("登录成功，但服务器未返回 JWT（PROTOCOL B 阶段才上线）")
        self._show_rooms()

    def _on_login_failure(self, exc: BaseException) -> None:
        self.login_view.set_busy(False)
        self.login_view.show_error(to_user_message(exc))

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
            user = extract_user(data) or {"username": username}
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
        self._current_room = None
        self.session.clear()
        self._show_login(f"{message}，请重新登录")

    # ---------- 房间大厅 ----------
    def _refresh_rooms(self) -> None:
        self.room_list_view.set_loading(True)
        self.room_list_view.set_status(f"正在连接 {self.config.server_url} …")
        self._safe_submit(
            self.api.list_rooms(),
            self._on_rooms_loaded,
            self._on_rooms_failed,
        )

    def _on_rooms_loaded(self, rooms: list[Room]) -> None:
        self.room_list_view.set_loading(False)
        self.room_list_view.set_rooms(rooms)
        suffix = "（Mock 演示数据）" if self.config.use_mock else ""
        if rooms:
            self.room_list_view.set_status(f"共 {len(rooms)} 个公共房间{suffix}")
        else:
            self.room_list_view.set_status(f"暂无公开房间{suffix}，可以创建一个")

    def _on_rooms_failed(self, exc: BaseException) -> None:
        self.room_list_view.set_loading(False)
        if isinstance(exc, ApiError) and exc.is_auth_error:
            self._handle_auth_expired(exc)
            return
        self.room_list_view.set_status(to_user_message(exc), error=True)

    def _on_create_room(self) -> None:
        dialog = CreateRoomDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, visibility, password = dialog.values()
        self.room_list_view.set_status("正在创建房间…")
        self._safe_submit(
            self.api.create_room(name, visibility, password),
            lambda room: self._on_room_created(room, password),
            self._on_room_action_failed,
        )

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
        self._stop_ws(room.code if room is not None else None)
        self._current_room = None
        self.session.clear()
        self._show_login()
        self.login_view.show_success("已退出登录")
        self._set_status("已退出登录")

    # ---------- 房间内 ----------
    def _enter_room(self, room: Room, password: str | None = None) -> None:
        self._current_room = room
        self._room_password = password
        self._ws_members_loaded = False
        self._last_members_refresh = 0.0
        self._timeline = ChatTimeline()
        self._chat_has_more = False
        self._chat_next_before = None
        self._chat_loading = False
        self.room_view.set_room(room)
        self.room_view.set_user(self._username())
        self.room_view.clear_chat()
        self.room_view.set_members(list(room.members))
        self.room_view.set_connection_state("connecting", "正在建立实时连接")
        self.room_view.set_status("")
        self.stack.setCurrentWidget(self.room_view)
        self.room_view.focus_chat_input()
        self._system_message(f"已进入 {room.display_name}（{room.code}）")
        self._start_ws(room)
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

    def _stop_ws(self, leave_room_code: str | None = None) -> None:
        """停止 WS；若在房间内，先发一帧 WS ``leave_room`` 再断开。

        B2b 实测：服务端的 ``user_left`` 只在收到客户端 WS ``leave_room`` 时广播，
        单纯断开连接或 HTTP leave 都不会通知队友，因此离开房间必须优雅告知。
        """
        self._ws_generation += 1
        ws, self._ws = self._ws, None
        if ws is None:
            return
        if not leave_room_code:
            self._safe_submit(ws.close())
            return

        async def _shutdown() -> None:
            try:
                if getattr(ws, "connected", False):
                    await ws.leave_room(leave_room_code)
            except Exception:  # noqa: BLE001 - 离开是尽力而为
                logger.debug("发送 WS leave_room 失败", exc_info=True)
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                logger.debug("关闭 WS 失败", exc_info=True)

        self._safe_submit(_shutdown())

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
        if generation != self._ws_generation or self._current_room is None:
            return
        mtype = message_type(message)
        if mtype == "room_joined":
            payload = message.get("room")
            if isinstance(payload, Mapping):
                room = Room.from_api(payload)
                self._current_room = room
                self.room_view.set_room(room)
            members = parse_members(message.get("members"))
            if members:
                self._ws_members_loaded = True
                self._last_members_refresh = time.monotonic()
                self.room_view.set_members(members)
            self.room_view.set_status("")
        elif mtype == "user_joined":
            user = message.get("user")
            if isinstance(user, Mapping):
                member = Member.from_api(user)
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
        elif mtype == "error":
            self._handle_ws_error(message)
        elif mtype in ("heartbeat", "pong", "auth_ok"):
            return
        elif mtype in ("canvas_snapshot", "canvas_op", "skill_state"):
            return  # C2/C3 占位：本轮不实现画板与技能共享
        # 未知类型按协议要求直接忽略

    # ---------- 聊天 ----------
    def _system_message(self, text: str) -> None:
        self._timeline.add_system(str(text))
        self._render_chat()

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
        self._render_chat(stick_to_bottom=initial)
        if initial:
            self.room_view.set_status(f"已加载 {len(page.messages)} 条历史消息" if page.messages else "")
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
        self._timeline.add_pending(client_msg_id, self._username(), text, now_ms())
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
            if code == "ROOM_CLOSED":
                self.room_view.set_status("房间已关闭，即将返回房间列表", error=True)
                QTimer.singleShot(1200, self._on_leave_room)
            return
        self._render_chat()

    def _on_leave_room(self) -> None:
        room = self._current_room
        self._stop_ws(room.code if room is not None else None)
        self._current_room = None
        self._room_password = None
        self._timeline.clear()
        self._chat_has_more = False
        self._chat_next_before = None
        self._chat_loading = False
        if room is not None:
            self._safe_submit(self.api.leave_room(room.code), on_error=lambda exc: None)
        self._show_rooms()

    # ---------- 设置 ----------
    def _on_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        dialog.test_requested.connect(
            lambda server_text, ws_text: self._on_test_connection(dialog, server_text, ws_text)
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_config = dialog.config_result()
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
        self.config = new_config
        self._refresh_status_bar()
        self.login_view.set_server_text(new_config.server_url, new_config.mode_label)
        self.room_list_view.set_mode(new_config.use_mock, new_config.server_url)
        self.session.set_persist_token(new_config.persist_token)

        if identity_changed:
            room = self._current_room
            self._stop_ws(room.code if room is not None else None)
            self._current_room = None
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

    # ---------- 关闭 ----------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 覆盖
        try:
            room = self._current_room
            self._safe_submit(self.api.close())
            self._stop_ws(room.code if room is not None else None)
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
