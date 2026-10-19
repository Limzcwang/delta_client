"""主窗口：QStackedWidget 切换 登录 -> 房间大厅 -> 房间内页，并负责网络编排。"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from config import AppConfig, save_config
from core.errors import ApiError, ErrorKind, to_user_message
from core.models import ChatMessage, Member, Room, now_ms, parse_members
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
        self._pending_chat_ids: set[str] = set()

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
        self.room_view.set_room(room)
        self.room_view.set_user(self._username())
        self.room_view.clear_chat()
        self.room_view.set_members(list(room.members))
        self.room_view.add_system_message(f"已进入 {room.display_name}（{room.code}）")
        self.room_view.set_connection_state("connecting", "正在建立实时连接")
        self.room_view.set_status("")
        self._pending_chat_ids.clear()
        self.stack.setCurrentWidget(self.room_view)
        self.room_view.focus_chat_input()
        self._start_ws(room)

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
            )
        elif not self.session.token:
            self.room_view.set_connection_state("offline", "未获取 JWT，聊天仅本地回显")
            self.room_view.add_system_message(
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

    def _on_ws_run_failed(self, exc: BaseException) -> None:
        self.room_view.set_connection_state("error", to_user_message(exc))
        self.room_view.add_system_message(f"实时连接失败：{to_user_message(exc)}")

    def _on_ws_state(self, generation: int, state: str, info: Mapping[str, Any]) -> None:
        if generation != self._ws_generation or self._current_room is None:
            return
        detail = str(info.get("message") or info.get("error") or "")
        if state == "connected":
            self.room_view.set_connection_state("connected", "实时连接已建立")
            self.room_view.add_system_message("实时连接已建立")
            room = self._current_room
            if self._ws is not None and room is not None:
                self._safe_submit(self._ws.join_room(room.code, self._room_password))
        elif state in ("connecting", "authenticating"):
            self.room_view.set_connection_state(state, detail or "正在连接")
        elif state == "waiting":
            delay = float(info.get("delay") or 0.0)
            self.room_view.set_connection_state("waiting", detail or f"{delay:.0f}s 后重连")
            self.room_view.set_status(f"连接中断，{delay:.0f}s 后自动重连", error=True)
        elif state == "reconnecting":
            self.room_view.set_connection_state("reconnecting", detail)
            if detail:
                self.room_view.set_status(f"重连中：{detail}", error=True)
        elif state == "auth_error":
            self.room_view.set_connection_state("auth_error", detail)
            self.room_view.add_system_message(f"认证失败：{detail or '登录状态无效'}")
        else:
            self.room_view.set_connection_state(state, detail)

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
                self.room_view.set_members(members)
            self.room_view.set_status("")
        elif mtype == "user_joined":
            user = message.get("user")
            if isinstance(user, Mapping):
                member = Member.from_api(user)
                self.room_view.add_member(member)
                self.room_view.add_system_message(f"{member.display_name} 加入了房间")
        elif mtype == "user_left":
            user = message.get("user")
            if isinstance(user, Mapping):
                member = Member.from_api(user)
                self.room_view.remove_member(member)
                self.room_view.add_system_message(f"{member.display_name} 离开了房间")
        elif mtype == "chat_message":
            chat = ChatMessage.from_ws(message)
            if chat.client_msg_id and chat.client_msg_id in self._pending_chat_ids:
                self._pending_chat_ids.discard(chat.client_msg_id)
                return  # 本机消息已本地回显，跳过服务端回显
            self.room_view.add_chat_message(chat)
        elif mtype == "error":
            text = str(message.get("message") or message.get("code") or "未知错误")
            self.room_view.add_system_message(f"服务端错误：{text}")
        elif mtype in ("heartbeat", "pong", "auth_ok"):
            return
        elif mtype in ("canvas_snapshot", "canvas_op", "skill_state"):
            return  # C2/C3 占位：本轮不实现画板与技能共享
        # 未知类型按协议要求直接忽略

    def _on_chat_submitted(self, text: str) -> None:
        text = str(text).strip()
        if not text:
            return
        username = self._username()
        if self._ws is None or not getattr(self._ws, "connected", False):
            self.room_view.add_chat_message(
                ChatMessage(sender_name=username, content=text, ts=now_ms())
            )
            self.room_view.set_status("未连接实时频道，消息仅本地回显", error=True)
            return

        # 先本地回显；client_msg_id 在发送前登记，服务端回显据此去重（PROTOCOL.md §6.5）
        self.room_view.add_chat_message(ChatMessage(sender_name=username, content=text, ts=now_ms()))
        client_msg_id = make_client_msg_id()
        self._pending_chat_ids.add(client_msg_id)

        def sent(sent_id: Any) -> None:
            if not sent_id:
                self._pending_chat_ids.discard(client_msg_id)
                self.room_view.add_system_message("消息发送失败：实时连接尚未就绪")

        def failed(exc: BaseException) -> None:
            self._pending_chat_ids.discard(client_msg_id)
            self.room_view.add_system_message(f"消息发送失败：{to_user_message(exc)}")

        self._safe_submit(self._ws.send_chat(text, client_msg_id), sent, failed)

    def _on_leave_room(self) -> None:
        room = self._current_room
        self._stop_ws(room.code if room is not None else None)
        self._current_room = None
        self._room_password = None
        if room is not None:
            self._safe_submit(self.api.leave_room(room.code), on_error=lambda exc: None)
        self._show_rooms()

    # ---------- 设置 ----------
    def _on_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
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

    # ---------- 关闭 ----------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 覆盖
        try:
            room = self._current_room
            self._safe_submit(self.api.close())
            self._stop_ws(room.code if room is not None else None)
        finally:
            self.bridge.stop()
            super().closeEvent(event)
