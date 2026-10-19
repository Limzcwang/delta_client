"""数据模型：房间、成员、聊天消息；以及 API/WS JSON -> 模型的容错解析。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from core.protocol import WS_CHAT_MESSAGE, unwrap_payload
from core.rooms import normalize_room_code, room_has_password


def now_ms() -> int:
    """当前 Unix 毫秒时间戳（PROTOCOL.md §1.2 统一时间格式）。"""
    return int(time.time() * 1000)


def parse_ts(value: Any) -> int | None:
    """把毫秒时间戳/数字字符串/ISO8601 统一成毫秒 int；无法识别返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)
    return None


def format_timestamp(ts: Any) -> str:
    """毫秒时间戳 -> 本地 ``HH:MM:SS``；解析失败返回空串。"""
    value = parse_ts(ts)
    if value is None:
        return ""
    try:
        return datetime.fromtimestamp(value / 1000.0).strftime("%H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return ""


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def _as_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


@dataclass(frozen=True)
class Member:
    """房间成员（PROTOCOL.md §3.2 UserSummary）。"""

    id: str = ""
    username: str = ""
    online: bool = True

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> "Member":
        if not isinstance(payload, Mapping):
            payload = {}
        return cls(
            id=_as_str(_first(payload, "id", "user_id", "userId")),
            username=_as_str(_first(payload, "username", "name", "nickname")),
            online=_first(payload, "online", default=True) is not False,
        )

    @property
    def display_name(self) -> str:
        return self.username or self.id or "未知用户"


@dataclass(frozen=True)
class Room:
    """房间摘要（PROTOCOL.md §3.2 RoomSummary + Room 扩展字段）。"""

    id: str = ""
    code: str = ""
    name: str = ""
    owner_id: str = ""
    member_count: int = 0
    has_password: bool = False
    created_at: int | None = None
    background_id: str | None = None
    members: tuple[Member, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> "Room":
        if not isinstance(payload, Mapping):
            payload = {}
        background = payload.get("background")
        if isinstance(background, Mapping):
            background_id = _as_str(_first(background, "id"), "") or None
        else:
            background_id = _as_str(_first(payload, "background_id", "backgroundId"), "") or None

        raw_members = payload.get("members")
        members: tuple[Member, ...] = ()
        if isinstance(raw_members, list):
            members = tuple(Member.from_api(item) for item in raw_members if isinstance(item, Mapping))

        member_count = _as_int(
            _first(payload, "member_count", "memberCount", "members_count", "current_members"),
            default=len(members),
        )

        return cls(
            id=_as_str(_first(payload, "id", "room_id", "roomId")),
            code=normalize_room_code(_first(payload, "code", "room_code", "roomCode")),
            name=_as_str(_first(payload, "name", "room_name", "title")),
            owner_id=_as_str(_first(payload, "owner_id", "ownerId", "owner", "creator")),
            member_count=member_count,
            has_password=room_has_password(payload),
            created_at=parse_ts(_first(payload, "created_at", "createdAt")),
            background_id=background_id,
            members=members,
            raw=dict(payload),
        )

    @property
    def display_name(self) -> str:
        return self.name or (f"房间 {self.code}" if self.code else "未命名房间")

    @property
    def has_members(self) -> bool:
        return bool(self.members)

    @property
    def created_text(self) -> str:
        return format_timestamp(self.created_at)


@dataclass(frozen=True)
class ChatMessage:
    """聊天消息（PROTOCOL.md §6.4 chat_message）。"""

    sender_name: str = ""
    content: str = ""
    ts: int | None = None
    message_id: str = ""
    client_msg_id: str = ""
    system: bool = False

    @classmethod
    def from_ws(cls, payload: Mapping[str, Any]) -> "ChatMessage":
        if not isinstance(payload, Mapping):
            payload = {}
        sender = payload.get("sender")
        if isinstance(sender, Mapping):
            sender_name = _as_str(_first(sender, "username", "name", "id"))
        elif isinstance(payload.get("username"), str):
            sender_name = payload["username"]
        else:
            sender_name = _as_str(payload.get("sender_name"))
        return cls(
            sender_name=sender_name or "未知用户",
            content=_as_str(payload.get("content")),
            ts=parse_ts(payload.get("ts")),
            message_id=_as_str(_first(payload, "message_id", "messageId")),
            client_msg_id=_as_str(_first(payload, "client_msg_id", "clientMsgId")),
            system=False,
        )

    @property
    def time_text(self) -> str:
        return format_timestamp(self.ts)

    def display_text(self) -> str:
        if self.system:
            return f"— {self.content} —"
        stamp = f"[{self.time_text}] " if self.time_text else ""
        return f"{stamp}{self.sender_name}：{self.content}"


def make_system_message(content: str) -> ChatMessage:
    return ChatMessage(content=content, system=True)


def parse_room_list(payload: Any) -> list[Room]:
    """解析房间列表：兼容 ``{items:[...]}``、``{rooms:[...]}``、``data:...`` 与裸数组。"""
    if isinstance(payload, Mapping):
        if "data" in payload:
            return parse_room_list(payload.get("data"))
        for key in ("items", "rooms", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [Room.from_api(item) for item in value if isinstance(item, Mapping)]
        return []
    if isinstance(payload, list):
        return [Room.from_api(item) for item in payload if isinstance(item, Mapping)]
    return []


def parse_members(payload: Any) -> list[Member]:
    """解析成员列表（``room_joined.members`` 或 ``{members:[...]}``）。"""
    if isinstance(payload, Mapping):
        payload = payload.get("members", payload.get("items"))
    if not isinstance(payload, list):
        return []
    return [Member.from_api(item) for item in payload if isinstance(item, Mapping)]


@dataclass(frozen=True)
class RoomDetail:
    """房间详情：``GET /api/v1/rooms/{room_id_or_code}`` 的 ``{room, members}``。"""

    room: Room = field(default_factory=Room)
    members: tuple[Member, ...] = ()

    @property
    def member_names(self) -> tuple[str, ...]:
        return tuple(member.display_name for member in self.members)


def parse_room_detail(payload: Any) -> RoomDetail | None:
    """解析房间详情（兼容统一包 ``{code,data:{room,members}}`` 与裸 ``{room,members}``）。"""
    data = unwrap_payload(payload)
    if not isinstance(data, Mapping):
        return None
    room_payload = data.get("room")
    room = Room.from_api(room_payload if isinstance(room_payload, Mapping) else data)
    members = parse_members(data.get("members"))
    if not members and room.members:
        members = list(room.members)
    return RoomDetail(room=room, members=tuple(members))


def message_is_chat(message: Mapping[str, Any]) -> bool:
    return str(message.get("type", "")) == WS_CHAT_MESSAGE
