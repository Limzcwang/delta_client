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
from core.canvas import CanvasSnapshot, parse_canvas_snapshot
from core.connection import ConnectionCheck, probe_ok
from core.errors import ApiError, ErrorKind
from core.models import (
    ChatMessage,
    ChatPage,
    Member,
    MyRoom,
    MyRoomsPage,
    Room,
    RoomDetail,
    now_ms,
)
from core.rooms import (
    ValidationError,
    normalize_room_code,
    room_reference,
    validate_room_code,
    validate_room_name,
    validate_room_name_update,
    validate_visibility,
)
from core.validation import (
    validate_new_password,
    validate_nickname,
    validate_password,
    validate_register_password,
    validate_register_username,
)
from net.api_client import LoginResult

_MOCK_LATENCY = 0.05
_ROOM_CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

#: 演示账号（仅内存、仅 Mock 模式；F 起带昵称）
_MOCK_USERS: tuple[dict[str, Any], ...] = (
    {"id": "1", "username": "demo", "nickname": "演示玩家", "password": "demo123"},
    {"id": "2", "username": "player", "nickname": "队友玩家", "password": "player123"},
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
    # H1「我的房间」演示：demo 已加入 2 个、房主 1 个
    {
        "id": "mock-room-myr01",
        "code": "MYR01",
        "name": "演示·已加入房",
        "owner_id": "2",
        "member_count": 2,
        "has_password": False,
        "visibility": "public",
        "created_at": now_ms() - 1_800_000,
        "background_id": "bg_default_01",
    },
    {
        "id": "mock-room-myr02",
        "code": "MYR02",
        "name": "演示·私密房",
        "owner_id": "3",
        "member_count": 2,
        "has_password": True,
        "password": "1234",
        "visibility": "private",
        "created_at": now_ms() - 2_700_000,
        "background_id": "bg_default_01",
    },
    {
        "id": "mock-room-myr03",
        "code": "MYR03",
        "name": "演示·房主房",
        "owner_id": "1",
        "member_count": 2,
        "has_password": False,
        "visibility": "public",
        "created_at": now_ms() - 3_600_000,
        "background_id": "bg_default_01",
    },
)


def _copy_room_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    copy = {key: value for key, value in payload.items() if key != "password"}
    return copy


def _mock_skill_states(now: int) -> list[dict[str, Any]]:
    """Mock E2：两个队友的预置技能状态（ready/charging/unknown 混合）。"""
    return [
        {
            "user_id": "2",
            "nickname": "队友-Alpha",
            "operator_id": "honglang",
            "operator_name": "红狼",
            "operator": "红狼",
            "captured_at": now,
            "skills": {
                "ultimate": {"state": "ready", "percent": 100},
                "ability": {"state": "ready", "charges": 2, "max_charges": 2},
                "throwable": {
                    "state": "charging",
                    "charges": 0,
                    "max_charges": 1,
                    "remaining_ms": 45000,
                },
            },
        },
        {
            "user_id": "3",
            "nickname": "队友-Bravo",
            "operator_id": "fengyi",
            "operator_name": "蜂医",
            "operator": "蜂医",
            "captured_at": now,
            "skills": {
                "ultimate": {
                    "state": "charging",
                    "percent": 65,
                    "remaining_ms": 20000,
                },
                "ability": {
                    "state": "charging",
                    "charges": 1,
                    "max_charges": 2,
                    "remaining_ms": 8000,
                },
                "throwable": {"state": "unknown"},
            },
        },
    ]


#: 演示房间成员（用于 Mock 的 HTTP 成员兜底，模拟 ``GET /rooms/{ref}`` 返回）
_SEED_MEMBERS: dict[str, list[dict[str, Any]]] = {
    "AB12C": [
        {"id": "2", "username": "player", "nickname": "队友玩家", "online": True},
        {"id": "3", "username": "bravo", "nickname": "队友-Bravo", "online": True},
    ],
    "K7M2P": [
        {"id": "3", "username": "charlie", "nickname": "队友-Charlie", "online": True},
        {"id": "4", "username": "delta", "nickname": "队友-Delta", "online": True},
        {"id": "5", "username": "echo", "nickname": "队友-Echo", "online": False},
        {"id": "6", "username": "foxtrot", "nickname": "队友-Foxtrot", "online": True},
    ],
    "Q4W8E": [{"id": "2", "username": "player", "nickname": "队友玩家", "online": False}],
    "MYR01": [
        {"id": "1", "username": "demo", "nickname": "演示玩家", "online": True},
        {"id": "2", "username": "player", "nickname": "队友玩家", "online": True},
    ],
    "MYR02": [
        {"id": "1", "username": "demo", "nickname": "演示玩家", "online": True},
        {"id": "3", "username": "charlie", "nickname": "队友-Charlie", "online": False},
    ],
    "MYR03": [
        {"id": "1", "username": "demo", "nickname": "演示玩家", "online": True},
        {"id": "2", "username": "player", "nickname": "队友玩家", "online": True},
    ],
}

#: H1：demo 预置已加入房间（`(username, code) -> joined_at`）
_SEED_MEMBERSHIPS: dict[tuple[str, str], int] = {
    ("demo", "MYR01"): now_ms() - 1_800_000,
    ("demo", "MYR02"): now_ms() - 2_700_000,
    ("demo", "MYR03"): now_ms() - 3_600_000,
}

#: 演示聊天历史（按时间正序；接口返回时倒序分页）
_SEED_MESSAGES: dict[str, list[dict[str, Any]]] = {
    "AB12C": [
        {
            "id": "mock-msg-0001",
            "room_id": "mock-room-ab12c",
            "user": {"id": "2", "username": "player", "nickname": "队友玩家"},
            "content": "欢迎来到新手训练房",
            "client_msg_id": None,
            "created_at": now_ms() - 300_000,
        },
        {
            "id": "mock-msg-0002",
            "room_id": "mock-room-ab12c",
            "user": {"id": "3", "username": "bravo", "nickname": "队友-Bravo"},
            "content": "今晚一起上分吗？",
            "client_msg_id": None,
            "created_at": now_ms() - 180_000,
        },
        {
            "id": "mock-msg-0003",
            "room_id": "mock-room-ab12c",
            "user": {"id": "2", "username": "player", "nickname": "队友玩家"},
            "content": "先热身两把",
            "client_msg_id": None,
            "created_at": now_ms() - 60_000,
        },
    ],
}


class MockApiClient:
    """内存版 API 客户端（用于 ``--mock`` / ``DELTA_MOCK=1``）。"""

    is_mock = True
    base_url = "mock://local"
    timeout = 0.0

    def __init__(self, latency: float = _MOCK_LATENCY) -> None:
        self.latency = max(0.0, float(latency))
        self._users: dict[str, dict[str, Any]] = {item["username"]: dict(item) for item in _MOCK_USERS}
        self._rooms: dict[str, dict[str, Any]] = {item["code"]: dict(item) for item in _SEED_ROOMS}
        self._room_members: dict[str, list[dict[str, Any]]] = {
            code: [dict(member) for member in members] for code, members in _SEED_MEMBERS.items()
        }
        self._memberships: set[tuple[str, str]] = set(_SEED_MEMBERSHIPS)
        self._joined_at: dict[tuple[str, str], int] = dict(_SEED_MEMBERSHIPS)
        self._username: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._messages: dict[str, list[dict[str, Any]]] = {
            code: [dict(message) for message in messages] for code, messages in _SEED_MESSAGES.items()
        }
        #: 画板状态（内存，mock 下按房间保存 strokes/rev）
        self._room_canvas: dict[str, dict[str, Any]] = {}

    # ---------- 基础 ----------
    async def _tick(self) -> None:
        if self.latency:
            await asyncio.sleep(self.latency)

    async def close(self) -> None:
        return None

    def _user_id(self, username: str) -> str:
        return str(self._users.get(username, {}).get("id", "0"))

    def _self_member(self) -> dict[str, Any]:
        if self._current_user is not None:
            return {
                "id": str(self._current_user.get("id", "0")),
                "username": str(self._current_user.get("username", "")),
                "nickname": str(self._current_user.get("nickname", "")),
                "online": True,
            }
        return {
            "id": "1",
            "username": self._username or "demo",
            "nickname": "演示玩家",
            "online": True,
        }

    def _find_room(self, room_id_or_code: str) -> dict[str, Any] | None:
        text = str(room_id_or_code or "").strip()
        code = room_reference(text)
        payload = self._rooms.get(code)
        if payload is not None:
            return payload
        for item in self._rooms.values():
            if str(item.get("id")) == text:
                return item
        return None

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
        public_user = {
            "id": str(user["id"]),
            "username": str(user["username"]),
            "nickname": str(user.get("nickname") or user["username"]),
        }
        self._current_user = public_user
        return LoginResult(
            token=token,
            user=public_user,
            raw={"code": 200, "message": "OK", "data": {"access_token": token, "token_type": "Bearer", "expires_in": 604800, "user": public_user}},
        )

    async def register(self, username: str, password: str) -> dict[str, Any]:
        await self._tick()
        try:
            name = validate_register_username(username)
            raw_password = validate_register_password(password)
        except ValidationError as exc:
            code = "INVALID_USERNAME" if "账号" in str(exc) else "INVALID_PASSWORD"
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400, code=code) from exc
        if name in self._users:
            raise ApiError(ErrorKind.CONFLICT, "用户名已存在", status=409, code="USERNAME_EXISTS")
        new_id = str(max(int(item["id"]) for item in self._users.values()) + 1)
        self._users[name] = {
            "id": new_id,
            "username": name,
            "nickname": name,
            "password": raw_password,
        }
        user = self._users[name]
        self._username = name
        self._current_user = {"id": new_id, "username": name, "nickname": name}
        token = self._issue_token(user)
        # 与 B2b 的 v1 注册响应保持一致（同登录），便于 UI 注册后自动登录
        return {
            "id": new_id,
            "username": name,
            "nickname": name,
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 604800,
            "user": {"id": new_id, "username": name, "nickname": name},
        }

    # ---------- 个人资料（F） ----------
    async def update_nickname(self, nickname: str) -> dict[str, Any]:
        await self._tick()
        if self._current_user is None:
            raise ApiError(ErrorKind.AUTH, "请先登录", status=401)
        try:
            value = validate_nickname(nickname)
        except ValidationError as exc:
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400, code="INVALID_NICKNAME") from exc
        user_id = str(self._current_user.get("id", "0"))
        self._current_user["nickname"] = value
        record = self._users.get(self._username or "")
        if record is not None:
            record["nickname"] = value
        for members in self._room_members.values():
            for member in members:
                if str(member.get("id")) == user_id:
                    member["nickname"] = value
        return {
            "id": user_id,
            "username": self._current_user.get("username", ""),
            "nickname": value,
        }

    async def change_password(self, old_password: str, new_password: str) -> None:
        await self._tick()
        if self._current_user is None:
            raise ApiError(ErrorKind.AUTH, "请先登录", status=401)
        try:
            old_value = validate_password(old_password)
            new_value = validate_new_password(new_password)
        except ValidationError as exc:
            code = "INVALID_NEW_PASSWORD" if "新密码" in str(exc) else "INVALID_PASSWORD"
            raise ApiError(ErrorKind.VALIDATION, str(exc), status=400, code=code) from exc
        record = self._users.get(self._username or "")
        if record is None or str(record.get("password")) != old_value:
            raise ApiError(
                ErrorKind.VALIDATION, "旧密码错误", status=400, code="WRONG_OLD_PASSWORD"
            )
        if old_value == new_value:
            raise ApiError(
                ErrorKind.VALIDATION,
                "新密码不能与旧密码相同",
                status=400,
                code="INVALID_NEW_PASSWORD",
            )
        record["password"] = new_value

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

    async def list_my_rooms(self, page: int = 1, page_size: int = 20) -> MyRoomsPage:
        """H1：当前用户已加入的房间（按 joined_at 倒序，role=owner/member）。"""
        await self._tick()
        username = self._username or ""
        user_id = str((self._current_user or {}).get("id", ""))
        entries: list[tuple[int, MyRoom]] = []
        if username:
            for (member_name, code), joined_at in self._joined_at.items():
                if member_name != username:
                    continue
                payload = self._rooms.get(code)
                if payload is None:
                    continue
                item = dict(_copy_room_payload(payload))
                item["joined_at"] = joined_at
                item["role"] = (
                    "owner" if user_id and str(payload.get("owner_id")) == user_id else "member"
                )
                entries.append((int(joined_at or 0), MyRoom.from_api(item)))
        entries.sort(key=lambda pair: pair[0], reverse=True)
        ordered = [item for _, item in entries]
        size = max(1, int(page_size))
        start = max(0, (max(1, int(page)) - 1) * size)
        window = ordered[start : start + size]
        has_more = start + len(window) < len(ordered)
        return MyRoomsPage(
            items=tuple(window),
            has_more=has_more,
            next_before=str(start + len(window)) if has_more else None,
        )

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
        members = self._room_members.setdefault(code, [])
        if self._username:
            self._memberships.add((self._username, code))
            self._joined_at[(self._username, code)] = now_ms()
            self_member = self._self_member()
            if not any(item.get("username") == self_member["username"] for item in members):
                members.append(self_member)
        payload["member_count"] = len(members)
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
        members = self._room_members.setdefault(code, [])
        self_member = self._self_member()
        if key not in self._memberships:
            self._memberships.add(key)
            self._joined_at[key] = now_ms()
            if not any(
                str(item.get("id")) == str(self_member["id"]) or item.get("username") == self_member["username"]
                for item in members
            ):
                members.append(self_member)
        payload["member_count"] = len(members)
        return Room.from_api(_copy_room_payload(payload))

    async def leave_room(self, room_code: str) -> None:
        await self._tick()
        code = normalize_room_code(room_code)
        key = (self._username or "", code)
        if key in self._memberships:
            self._memberships.discard(key)
            self._joined_at.pop(key, None)
            payload = self._rooms.get(code)
            self_member = self._self_member()
            if payload is not None:
                members = self._room_members.get(code, [])
                self._room_members[code] = [
                    item
                    for item in members
                    if not (
                        str(item.get("id")) == str(self_member["id"])
                        or item.get("username") == self_member["username"]
                    )
                ]
                payload["member_count"] = len(self._room_members[code])

    def _require_owner(self, payload: Mapping[str, Any]) -> None:
        current_id = str((self._current_user or {}).get("id", "0"))
        if not current_id or str(payload.get("owner_id", "")) != current_id:
            raise ApiError(ErrorKind.FORBIDDEN, "只有房主才能执行该操作", status=403, code="NOT_ROOM_OWNER")

    async def update_room(
        self,
        room_id_or_code: str,
        *,
        name: str | None = None,
        password: str | None = None,
    ) -> Room:
        """Mock 房主修改房间名/密码（F）。"""
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        self._require_owner(payload)
        if name is not None:
            try:
                payload["name"] = validate_room_name_update(name)
            except ValidationError as exc:
                raise ApiError(ErrorKind.VALIDATION, str(exc), status=400, code="ROOM_NAME_INVALID") from exc
        if password is not None:
            if len(str(password)) < 4 or len(str(password)) > 32:
                raise ApiError(
                    ErrorKind.VALIDATION, "房间密码需为 4–32 位", status=400, code="ROOM_PASSWORD_INVALID"
                )
            payload["password"] = str(password)
            payload["has_password"] = True
        return Room.from_api(_copy_room_payload(payload))

    async def kick_member(self, room_id_or_code: str, user_id: str) -> dict[str, Any]:
        """Mock H3：房主移出成员。"""
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        self._require_owner(payload)
        code = str(payload["code"])
        members = self._room_members.get(code, [])
        target = next(
            (item for item in members if str(item.get("id")) == str(user_id)), None
        )
        if target is None:
            raise ApiError(
                ErrorKind.NOT_FOUND, "目标成员不存在", status=404, code="MEMBER_NOT_FOUND"
            )
        if str(target.get("id")) == str(payload.get("owner_id")):
            raise ApiError(
                ErrorKind.FORBIDDEN, "不能移出房主", status=403, code="CANNOT_KICK_OWNER"
            )
        if str(target.get("id")) == str((self._current_user or {}).get("id")):
            raise ApiError(
                ErrorKind.VALIDATION, "不能移出自己", status=400, code="CANNOT_KICK_SELF"
            )
        self._room_members[code] = [
            item for item in members if str(item.get("id")) != str(user_id)
        ]
        payload["member_count"] = len(self._room_members[code])
        target_name = str(target.get("username") or "")
        if target_name:
            self._memberships.discard((target_name, code))
            self._joined_at.pop((target_name, code), None)
        return {"kicked": True, "user": dict(target)}

    async def delete_room(self, room_id_or_code: str) -> bool:
        """Mock 房主删除房间（F）。"""
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            return True  # 已不存在视为幂等成功
        self._require_owner(payload)
        code = str(payload["code"])
        self._rooms.pop(code, None)
        self._room_members.pop(code, None)
        self._messages.pop(code, None)
        self._room_canvas.pop(code, None)
        self._memberships = {
            pair for pair in self._memberships if pair[1] != code
        }
        self._joined_at = {
            pair: joined_at
            for pair, joined_at in self._joined_at.items()
            if pair[1] != code
        }
        return True

    async def get_room_detail(self, room_id_or_code: str) -> RoomDetail:
        """Mock 版房间详情（对应 ``GET /api/v1/rooms/{room_id_or_code}``）。"""
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        members = tuple(
            Member.from_api(item) for item in self._room_members.get(str(payload["code"]), [])
        )
        return RoomDetail(room=Room.from_api(_copy_room_payload(payload)), members=members)

    async def check_connection(self) -> ConnectionCheck:
        """Mock 版连通性自检（演示/测试用）。"""
        await self._tick()
        rooms = await self.list_rooms()
        return ConnectionCheck(
            server_url=self.base_url,
            health=probe_ok("health", "/health 200（mock）", elapsed_ms=0),
            rooms=probe_ok("rooms", f"/api/v1/rooms 200（{len(rooms)} 个房间）", elapsed_ms=0),
            rooms_count=len(rooms),
        )

    # ---------- 聊天 ----------
    def append_message(
        self,
        room_ref: str,
        user: Mapping[str, Any],
        content: str,
        client_msg_id: str | None = None,
    ) -> dict[str, Any]:
        """Mock WS 发送后落一份消息（供回显与历史查询）。"""
        code = room_reference(str(room_ref))
        payload = self._find_room(code)
        room_id = str(payload["id"]) if payload is not None else str(room_ref)
        message = {
            "id": f"mock-msg-{uuid.uuid4().hex[:12]}",
            "room_id": room_id,
            "room_code": str(payload["code"]) if payload is not None else code,
            "user": {
                "id": str(user.get("id", "0")),
                "username": str(user.get("username", "")),
                "nickname": str(user.get("nickname", "")),
            },
            "content": str(content),
            "client_msg_id": client_msg_id or None,
            "created_at": now_ms(),
        }
        key = str(payload["code"]) if payload is not None else code
        self._messages.setdefault(key, []).append(message)
        return message

    async def get_messages(
        self,
        room_id_or_code: str,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> ChatPage:
        """Mock 版聊天历史：最新一页在前（新→旧），``before`` 为消息 id。"""
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        code = str(payload["code"])
        messages = self._messages.setdefault(code, [])
        if before:
            index = next((i for i, item in enumerate(messages) if item.get("id") == before), None)
            if index is not None:
                messages = messages[:index]
        page_size = max(1, min(100, int(limit)))
        window = messages[-page_size:]
        has_more = len(messages) > len(window)
        page_items = list(reversed(window))
        next_before = page_items[-1]["id"] if has_more and page_items else None
        return ChatPage(
            messages=tuple(ChatMessage.from_ws(item) for item in page_items),
            has_more=has_more,
            next_before=next_before,
            window_days=7,
        )

    # ---------- 画板 ----------
    def _canvas_state(self, room_ref: str) -> dict[str, Any]:
        payload = self._find_room(room_ref)
        key = str(payload["code"]) if payload is not None else room_reference(str(room_ref))
        return self._room_canvas.setdefault(
            key, {"strokes": [], "rev": 0, "updated_at": None}
        )

    def canvas_payload(self, room_ref: str) -> dict[str, Any]:
        state = self._canvas_state(room_ref)
        return {
            "strokes": [dict(op) for op in state.get("strokes", [])],
            "rev": int(state.get("rev", 0)),
        }

    def apply_canvas_op(self, room_ref: str, op: Mapping[str, Any], rev: int) -> None:
        state = self._canvas_state(room_ref)
        state["rev"] = max(int(state.get("rev", 0)), int(rev))
        if op.get("kind") == "clear":
            state["strokes"] = []
        else:
            state["strokes"].append(dict(op))

    def save_canvas_snapshot(
        self, room_ref: str, strokes: list[Mapping[str, Any]], rev: int
    ) -> dict[str, Any]:
        state = self._canvas_state(room_ref)
        state["strokes"] = [dict(op) for op in strokes]
        state["rev"] = int(rev)
        state["updated_at"] = now_ms()
        return {"strokes": list(state["strokes"]), "rev": state["rev"], "updated_at": state["updated_at"]}

    async def get_canvas(self, room_id_or_code: str) -> CanvasSnapshot:
        await self._tick()
        payload = self._find_room(room_id_or_code)
        if payload is None:
            raise ApiError(ErrorKind.ROOM_NOT_FOUND, "房间不存在或已关闭", status=404, code=40402)
        return parse_canvas_snapshot(self.canvas_payload(str(payload["code"])))

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
        store: MockApiClient | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.on_message = on_message
        self.on_state = on_state
        self.user: dict[str, Any] = dict(user or {"id": "1", "username": "demo"})
        self.room = room
        self.latency = max(0.0, float(latency))
        self.store = store
        self.connected = False
        self.last_skill_update: dict[str, Any] | None = None
        self.last_skill_off: str | None = None
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
        members: list[dict[str, Any]] = [
            {
                **dict(self.user),
                "nickname": str(self.user.get("nickname") or self.user.get("username", "demo")),
            }
        ]
        if self.user.get("username") != "队友-Alpha":
            members.append({"id": "2", "username": "alpha", "nickname": "队友-Alpha", "online": True})
        if self.user.get("username") != "队友-Bravo":
            members.append({"id": "3", "username": "bravo", "nickname": "队友-Bravo", "online": True})
        canvas_snapshot = (
            self.store.canvas_payload(str(raw.get("code") or room_code))
            if self.store is not None
            else {"strokes": [], "rev": 0}
        )
        now = now_ms()
        skill_states = _mock_skill_states(now)
        self._emit(
            {
                "type": protocol.WS_ROOM_JOINED,
                "room": raw,
                "members": members,
                "canvas_snapshot": canvas_snapshot,
                "skill_states": skill_states,
                "skill_state": {"items": skill_states},
                "server_time": now,
            }
        )
        return True

    async def send_skill_update(
        self,
        room_id: str,
        captured_at: int,
        skills: Any,
        operator_id: str = "",
        operator_name: str = "",
    ) -> bool:
        self.last_skill_update = {
            "room_id": str(room_id),
            "captured_at": int(captured_at),
            "skills": skills,
            "operator_id": str(operator_id or ""),
            "operator_name": str(operator_name or ""),
        }
        return True

    async def send_skill_off(self, room_id: str | None = None) -> bool:
        self.last_skill_off = str(room_id or "")
        return True

    def simulate_skill_state(
        self,
        user_id: str,
        nickname: str,
        skills: Mapping[str, Any] | list[Mapping[str, Any]],
        *,
        operator: str = "",
        operator_id: str = "",
        captured_at: int | None = None,
    ) -> None:
        """Mock E2/E3a：主动下发一条队友技能状态（skills 支持对象或 E1 数组）。"""
        self._emit(
            {
                "type": protocol.WS_SKILL_SHARE_STATE,
                "user_id": str(user_id),
                "nickname": nickname,
                "operator_id": operator_id,
                "operator_name": operator,
                "operator": operator,
                "captured_at": int(captured_at or now_ms()),
                "skills": (dict(skills) if isinstance(skills, Mapping) else list(skills)),
            }
        )

    def simulate_skill_removed(self, user_id: str) -> None:
        self._emit(
            {"type": protocol.WS_SKILL_SHARE_REMOVED, "user_id": str(user_id)}
        )

    async def send_chat(
        self,
        content: str,
        client_msg_id: str | None = None,
        room_id: str | None = None,
    ) -> str | None:
        client_msg_id = client_msg_id or protocol.make_client_msg_id()
        room_ref = self.room.code if self.room is not None else (room_id or "")

        async def _echo() -> None:
            await asyncio.sleep(self.latency + 0.2)
            if self.store is not None:
                message = self.store.append_message(room_ref, self.user, content, client_msg_id)
            else:
                message = {
                    "id": f"mock-msg-{uuid.uuid4().hex[:12]}",
                    "room_id": str(self.room.id) if self.room is not None else "",
                    "room_code": room_ref,
                    "user": {
                        "id": str(self.user.get("id", "1")),
                        "username": str(self.user.get("username", "demo")),
                        "nickname": str(self.user.get("nickname", self.user.get("username", "demo"))),
                    },
                    "content": content,
                    "client_msg_id": client_msg_id,
                    "created_at": now_ms(),
                }
            payload = {"type": protocol.WS_CHAT_MESSAGE}
            payload.update(message)
            self._emit(payload)

        asyncio.get_running_loop().create_task(_echo())
        return client_msg_id

    async def send_canvas_op(self, op: dict[str, Any], rev: int, room_id: str) -> bool:
        room_ref = self.room.code if self.room is not None else str(room_id)
        if self.store is not None:
            self.store.apply_canvas_op(room_ref, op, rev)
        return True

    async def save_canvas_snapshot(
        self,
        strokes: list[dict[str, Any]],
        rev: int,
        room_id: str,
        timeout: float = 3.0,
    ) -> dict[str, Any] | None:
        room_ref = self.room.code if self.room is not None else str(room_id)
        if self.store is not None:
            saved = self.store.save_canvas_snapshot(room_ref, strokes, rev)
        else:
            saved = {"strokes": list(strokes), "rev": int(rev), "updated_at": now_ms()}
        ack = {
            "type": protocol.WS_CANVAS_SNAPSHOT_SAVED,
            "room_id": str(room_id),
            "rev": saved.get("rev", rev),
            "updated_at": saved.get("updated_at"),
        }
        self._emit(ack)
        return ack

    def simulate_room_kicked(
        self, by: Mapping[str, Any] | None = None, reason: str = "kicked"
    ) -> None:
        """Mock H3：模拟服务端向本连接下发 ``room_kicked``（GUI 冒烟用）。"""
        room = self.room
        payload = {
            "type": protocol.WS_ROOM_KICKED,
            "room_id": str(room.id) if room is not None else "",
            "room_code": str(room.code) if room is not None else "",
            "by": dict(by) if isinstance(by, Mapping) else {"id": "", "nickname": "房主"},
            "reason": reason,
        }
        self._emit(payload)

    async def leave_room(self, room_id_or_code: str) -> bool:
        return True

    async def close(self) -> None:
        self.connected = False
        if self._stop_event is not None:
            self._stop_event.set()
