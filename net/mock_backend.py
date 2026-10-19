"""可切换的 Mock 后端：后端 B 阶段接口就绪前，让 UI 能完整跑通演示。

- :class:`MockApiClient` 与 :class:`net.api_client.ApiClient` 同接口（login/register/
  list_rooms/create_room/join_room/leave_room），全部在内存中完成，不发网络请求；
- :class:`MockWsClient` 与 :class:`net.ws_client.WsClient` 同接口（run/join_room/
  send_chat/close），模拟 auth_ok / room_joined / chat_message 推送；
- Mock 数据只存在进程内，**不落盘、不含任何真实凭据**，重启即重置。
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Any, Mapping

from core import protocol
from core.errors import ApiError, ErrorKind
from core.models import Room, now_ms
from core.rooms import (
    ValidationError,
    normalize_room_code,
    validate_room_code,
    validate_room_name,
    validate_visibility,
)
from core.validation import validate_register_password, validate_username
from net.api_client import LoginResult

_MOCK_LATENCY = 0.05
_ROOM_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

#: 演示账号（仅内存、仅 Mock 模式）
_MOCK_USERS: tuple[dict[str, Any], ...] = (
    {"id": "1", "username": "demo", "password": "demo123"},
    {"id": "2", "username": "player", "password": "player123"},
)

#: 演示房间（Demo 账号进入后可直接看到）
_SEED_ROOMS: tuple[dict[str, Any], ...] = (
    {
        "id": "mock-room-ab12c",
        "code": "AB12C",
        "name": "新手训练房",
        "owner_id": "2",
        "member_count": 2,
        "has_password": False,
        "visibility": "public",
        "created_at": now_ms() - 3_600_000,
        "background_id": "bg_default_01",
    },
    {
        "id": "mock-room-k7m2p",
        "code": "K7M2P",
        "name": "开黑上分（缺 1）",
        "owner_id": "3",
        "member_count": 4,
        "has_password": False,
        "visibility": "public",
        "created_at": now_ms() - 7_200_000,
        "background_id": "bg_default_01",
    },
    {
        "id": "mock-room-q4w8e",
        "code": "Q4W8E",
        "name": "私密战术讨论",
        "owner_id": "2",
        "member_count": 1,
        "has_password": True,
        "password": "1234",
        "visibility": "private",
        "created_at": now_ms() - 10_800_000,
        "background_id": "bg_default_01",
    },
)


def _copy_room_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    copy = {key: value for key, value in payload.items() if key != "password"}
    return copy


class MockApiClient:
    """内存版 API 客户端（用于 ``--mock`` / ``DELTA_MOCK=1``）。"""

    is_mock = True
    base_url = "mock://local"
    timeout = 0.0

    def __init__(self, latency: float = _MOCK_LATENCY) -> None:
        self.latency = max(0.0, float(latency))
        self._users: dict[str, dict[str, Any]] = {item["username"]: dict(item) for item in _MOCK_USERS}
        self._rooms: dict[str, dict[str, Any]] = {item["code"]: dict(item) for item in _SEED_ROOMS}
        self._memberships: set[tuple[str, str]] = set()
        self._username: str | None = None

    # ---------- 基础 ----------
    async def _tick(self) -> None:
        if self.latency:
            await asyncio.sleep(self.latency)

    async def close(self) -> None:
        return None

    def _user_id(self, username: str) -> str:
        return str(self._users.get(username, {}).get("id", "0"))

    # ---------- 认证 ----------
    def _issue_token(self, user: Mapping[str, Any]) -> str:
        return f"mock-token.{user['id']}.{uuid.uuid4().hex}"

    async def login(self, username: str, password: str) -> LoginResult:
        await self._tick()
        self._username = str(username or "").strip()
        user = self._users.get(self._username)
        if user is None or str(user.get("password")) != str(password):
            raise ApiError(ErrorKind.AUTH, "用户名或密码错误", status=401)
        token = self._issue_token(user)
        public_user = {"id": str(user["id"]), "username": str(user["username"])}
        return LoginResult(
            token=token,
            user=public_user,
            raw={"code": 200, "message": "OK", "data": {"access_token": token, "token_type": "Bearer", "expires_in": 604800, "user": public_user}},
        )

    async def register(self, username: str, password: str) -> dict[str, Any]:
        await self._tick()
        try:
            name = validate_username(username)
            raw_password = validate_register_password(password)
        except ValidationError as exc:
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400) from exc
        if name in self._users:
            raise ApiError(ErrorKind.CONFLICT, "用户名已存在", status=409, code="USERNAME_EXISTS")
        new_id = str(max(int(item["id"]) for item in self._users.values()) + 1)
        self._users[name] = {"id": new_id, "username": name, "password": raw_password}
        user = self._users[name]
        self._username = name
        token = self._issue_token(user)
        # 与 B2b 的 v1 注册响应保持一致（同登录），便于 UI 注册后自动登录
        return {
            "id": new_id,
            "username": name,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 604800,
            "user": {"id": new_id, "username": name},
        }

    # ---------- 房间 ----------
    async def list_rooms(self) -> list[Room]:
        await self._tick()
        rooms = [
            Room.from_api(_copy_room_payload(item))
            for item in self._rooms.values()
            if item.get("visibility") != "private"
        ]
        rooms.sort(key=lambda room: room.created_at or 0, reverse=True)
        return rooms

    async def create_room(self, name: str, visibility: str, password: str | None = None) -> Room:
        await self._tick()
        try:
            room_name = validate_room_name(name)
            room_visibility = validate_visibility(visibility)
        except ValidationError as exc:
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400) from exc
        if room_visibility == "private" and not password:
            raise ApiError(ErrorKind.VALIDATION, "私有房间必须设置密码", status=400)
        code = self._generate_room_code()
        payload: dict[str, Any] = {
            "id": f"mock-room-{uuid.uuid4().hex[:8]}",
            "code": code,
            "name": room_name,
            "owner_id": self._user_id(self._username or ""),
            "member_count": 1,
            "has_password": room_visibility == "private",
            "visibility": room_visibility,
            "created_at": now_ms(),
            "background_id": "bg_default_01",
        }
        if password:
            payload["password"] = str(password)
        self._rooms[code] = payload
        if self._username:
            self._memberships.add((self._username, code))
        return Room.from_api(_copy_room_payload(payload))

    async def join_room(self, room_code: str, password: str | None = None) -> Room:
        await self._tick()
        try:
            code = validate_room_code(room_code)
        except ValidationError as exc:
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400) from exc
        payload = self._rooms.get(code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        if payload.get("has_password") and not password:
            raise ApiError(
                ErrorKind.ROOM_PASSWORD_REQUIRED, "该房间需要密码", status=403, code="ROOM_PASSWORD_REQUIRED"
            )
        if payload.get("has_password") and str(password) != str(payload.get("password")):
            raise ApiError(
                ErrorKind.ROOM_PASSWORD_INVALID, "房间密码错误", status=403, code="ROOM_PASSWORD_INVALID"
            )
        key = (self._username or "", code)
        if key not in self._memberships:
            self._memberships.add(key)
            payload["member_count"] = int(payload.get("member_count", 0)) + 1
        return Room.from_api(_copy_room_payload(payload))

    async def leave_room(self, room_code: str) -> None:
        await self._tick()
        code = normalize_room_code(room_code)
        key = (self._username or "", code)
        if key in self._memberships:
            self._memberships.discard(key)
            payload = self._rooms.get(code)
            if payload is not None:
                payload["member_count"] = max(0, int(payload.get("member_count", 1)) - 1)

    def _generate_room_code(self) -> str:
        while True:
            code = "".join(secrets.choice(_ROOM_CODE_ALPHABET) for _ in range(5))
            if code not in self._rooms:
                return code


class MockWsClient:
    """内存版 WebSocket 客户端：模拟 auth_ok / room_joined / chat_message。"""

    is_mock = True

    def __init__(
        self,
        url: str = "mock://ws",
        token: str = "mock-token",
        *,
        on_message=None,
        on_state=None,
        user: Mapping[str, Any] | None = None,
        room: Room | None = None,
        latency: float = _MOCK_LATENCY,
    ) -> None:
        self.url = url
        self.token = token
        self.on_message = on_message
        self.on_state = on_state
        self.user: dict[str, Any] = dict(user or {"id": "1", "username": "demo"})
        self.room = room
        self.latency = max(0.0, float(latency))
        self.connected = False
        self._state = "idle"
        self._stop_event: asyncio.Event | None = None

    def _set_state(self, state: str, **info: Any) -> None:
        self._state = state
        if self.on_state:
            try:
                self.on_state(state, info)
            except Exception:  # pragma: no cover
                pass

    def _emit(self, message: dict[str, Any]) -> None:
        if self.on_message:
            try:
                self.on_message(message)
            except Exception:  # pragma: no cover
                pass

    async def run(self) -> None:
        self._stop_event = asyncio.Event()
        await asyncio.sleep(self.latency)
        self.connected = True
        self._state = "connected"
        self._set_state("connected", mode="mock", url=self.url)
        self._emit(
            {
                "type": protocol.WS_AUTH_OK,
                "user": self.user,
                "server_time": now_ms(),
                "heartbeat_interval_ms": 15000,
            }
        )
        await self._stop_event.wait()
        self.connected = False
        self._state = "stopped"
        self._set_state("stopped")

    async def join_room(self, room_code: str, password: str | None = None) -> bool:
        raw = dict(self.room.raw) if self.room is not None and self.room.raw else {}
        raw.setdefault("code", room_code)
        raw.setdefault("name", f"房间 {room_code}")
        members: list[dict[str, Any]] = [dict(self.user)]
        if self.user.get("username") != "队友-Alpha":
            members.append({"id": "2", "username": "队友-Alpha", "online": True})
        if self.user.get("username") != "队友-Bravo":
            members.append({"id": "3", "username": "队友-Bravo", "online": True})
        self._emit(
            {
                "type": protocol.WS_ROOM_JOINED,
                "room": raw,
                "members": members,
                "canvas_snapshot": {
                    "seq": 0,
                    "canvas_size": [1920, 1080],
                    "background": {"id": raw.get("background_id", "bg_default_01")},
                    "ops": [],
                },
                "skill_state": {"items": []},
                "server_time": now_ms(),
            }
        )
        return True

    async def send_chat(self, content: str, client_msg_id: str | None = None) -> str | None:
        client_msg_id = client_msg_id or protocol.make_client_msg_id()

        async def _echo() -> None:
            await asyncio.sleep(self.latency + 0.2)
            self._emit(
                {
                    "type": protocol.WS_CHAT_MESSAGE,
                    "room_id": str(self.room.id) if self.room is not None else "",
                    "message_id": f"mock-msg-{uuid.uuid4().hex[:8]}",
                    "client_msg_id": client_msg_id,
                    "sender": {"id": str(self.user.get("id", "1")), "username": str(self.user.get("username", "demo"))},
                    "content": content,
                    "content_type": "text",
                    "ts": now_ms(),
                }
            )

        asyncio.get_running_loop().create_task(_echo())
        return client_msg_id

    async def leave_room(self, room_id_or_code: str) -> bool:
        return True

    async def close(self) -> None:
        self.connected = False
        if self._stop_event is not None:
            self._stop_event.set()
