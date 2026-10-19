"""后端协议常量与纯逻辑辅助。

契约来源：后端仓库 ``delta_service/PROTOCOL.md``（里程碑 A 契约基线，2026-10）。
本模块只做字符串/JSON 处理，不发起任何网络请求，便于离线单测。
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlsplit, urlunsplit

#: 协议版本（PROTOCOL.md §10，A=1）
PROTOCOL_VERSION = 1
CLIENT_NAME = "delta-desktop"
CLIENT_VERSION = "1.0.0"

#: HTTP 路径（目标契约 /api/v1，B 阶段落地）
API_V1_LOGIN = "/api/v1/auth/login"
API_V1_REGISTER = "/api/v1/auth/register"
API_V1_ME = "/api/v1/users/me"
#: F 个人资料（feat/profile 契约）：改名 PATCH /users/me，改密 POST /users/me/password
API_V1_ME_PASSWORD = "/api/v1/users/me/password"
API_V1_ROOMS = "/api/v1/rooms"
#: H1：「我的房间」（按加入时间倒序，page/page_size）
API_V1_MY_ROOMS = "/api/v1/rooms/mine"
API_HEALTH = "/health"

#: 过渡期兼容路径（A 现状）
API_LOGIN_LEGACY = "/api/users/login"
API_REGISTER_LEGACY = "/api/users/create"
API_ROOMS_LEGACY = "/api/room/public/list"

#: WebSocket 消息类型（PROTOCOL.md §6）
WS_AUTH = "auth"
WS_AUTH_OK = "auth_ok"
WS_AUTH_ERROR = "auth_error"
WS_JOIN_ROOM = "join_room"
WS_LEAVE_ROOM = "leave_room"
WS_CHAT_SEND = "chat_send"
WS_CANVAS_OP = "canvas_op"
WS_CANVAS_SNAPSHOT = "canvas_snapshot"
WS_CANVAS_SNAPSHOT_SAVE = "canvas_snapshot_save"
WS_CANVAS_SNAPSHOT_SAVED = "canvas_snapshot_saved"
WS_SKILL_REPORT = "skill_report"
WS_PING = "ping"
WS_ROOM_JOINED = "room_joined"
WS_USER_JOINED = "user_joined"
WS_USER_LEFT = "user_left"
WS_CHAT_MESSAGE = "chat_message"
WS_ROOM_UPDATED = "room_updated"
WS_ROOM_DELETED = "room_deleted"
WS_SKILL_STATE = "skill_state"
WS_HEARTBEAT = "heartbeat"
WS_PONG = "pong"
WS_ERROR = "error"


def room_join_path(room_code: str) -> str:
    """加入房间路径。

    PROTOCOL.md §3.2 写作 ``/api/v1/rooms/{room_id}/join``，但 §4 明确
    “加入按 room_code 或 room_id”；客户端当前只知道 5 位房间码，因此这里传
    code（TODO: 与后端确认路径参数是否同时接受 code，B 阶段对齐）。
    """
    return f"{API_V1_ROOMS}/{quote(str(room_code), safe='')}/join"


def room_leave_path(room_code: str) -> str:
    return f"{API_V1_ROOMS}/{quote(str(room_code), safe='')}/leave"


def room_detail_path(room_code: str) -> str:
    return f"{API_V1_ROOMS}/{quote(str(room_code), safe='')}"


def room_messages_path(room_id_or_code: str) -> str:
    """聊天历史：``GET /api/v1/rooms/{room_id_or_code}/messages``（C）。"""
    return f"{API_V1_ROOMS}/{quote(str(room_id_or_code), safe='')}/messages"


def room_canvas_path(room_id_or_code: str) -> str:
    """画板快照：``GET /api/v1/rooms/{room_id_or_code}/canvas``（D）。"""
    return f"{API_V1_ROOMS}/{quote(str(room_id_or_code), safe='')}/canvas"


def canvas_op_message(room_id: str, rev: int, op: Mapping[str, Any]) -> dict[str, Any]:
    """WS ``canvas_op``（PROTOCOL §6.7）：rev 每连接每房间从 0 单调递增。"""
    return {"type": WS_CANVAS_OP, "room_id": str(room_id), "rev": int(rev), "op": dict(op)}


def canvas_snapshot_save_message(
    room_id: str, rev: int, strokes: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """WS ``canvas_snapshot_save``（离开/关窗前全量落库）。"""
    return {
        "type": WS_CANVAS_SNAPSHOT_SAVE,
        "room_id": str(room_id),
        "rev": int(rev),
        "strokes": [dict(op) for op in strokes],
    }


def ws_url_for(server_url: str, ws_path: str = "/ws") -> str:
    """由 HTTP 基地址推导 WebSocket 地址（PROTOCOL.md §1.1 目标 wss://host/ws）。

    ``http://host:8000`` -> ``ws://host:8000/ws``；
    ``https://host/delta`` -> ``wss://host/delta/ws``。
    """
    parts = urlsplit(str(server_url or "").strip())
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"无法从 {server_url!r} 推导 WebSocket 地址：需要 http/https")
    scheme = "wss" if parts.scheme == "https" else "ws"
    base_path = parts.path.rstrip("/")
    path = f"{base_path}/{ws_path.lstrip('/')}"
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def client_info() -> dict[str, Any]:
    """``auth`` 消息里的 client 字段（PROTOCOL.md §6.2）。"""
    return {"name": CLIENT_NAME, "version": CLIENT_VERSION, "os": "windows"}


def auth_message(token: str, protocol_version: int = PROTOCOL_VERSION) -> dict[str, Any]:
    return {
        "type": WS_AUTH,
        "token": token,
        "protocol_version": protocol_version,
        "client": client_info(),
    }


def join_room_message(
    room_code: str, password: str | None = None, request_id: str | None = None
) -> dict[str, Any]:
    """WS ``join_room``（PROTOCOL PR#9 §6.3）。

    新字段 ``room_id_or_code`` 同时接受 5 位 code 与内部 id；同时保留旧字段
    ``room_code`` 以兼容 B2b（服务端忽略未知字段）。前置条件：必须先通过
    HTTP ``POST /rooms/{room_id_or_code}/join`` 成为成员，否则回 ``NOT_ROOM_MEMBER``。
    ``password`` 在 C 起被服务端忽略（HTTP 已校验），保留仅用于旧服务端兼容。
    """
    message: dict[str, Any] = {
        "type": WS_JOIN_ROOM,
        "room_id_or_code": str(room_code),
        "room_code": str(room_code),
    }
    if password:
        message["password"] = password
    if request_id:
        message["request_id"] = request_id
    return message


def leave_room_message(room_id_or_code: str | None = None) -> dict[str, Any]:
    """WS ``leave_room``；PR#9 起服务端忽略房间参数（退出当前频道）。"""
    message: dict[str, Any] = {"type": WS_LEAVE_ROOM}
    if room_id_or_code:
        # 旧字段+新字段都带，B2b 之前实现会读取
        message["room_id"] = str(room_id_or_code)
        message["room_id_or_code"] = str(room_id_or_code)
    return message


def chat_send_message(
    content: str,
    client_msg_id: str,
    room_id: str | None = None,
    content_type: str = "text",
) -> dict[str, Any]:
    """WS ``chat_send``（PROTOCOL C 定稿）。

    服务端用会话房间（不读 ``room_id``），但按联调约定仍带上房间引用，
    便于服务端日志/未来多房间扩展；``client_msg_id`` 用于回显认领与重试。
    """
    message: dict[str, Any] = {
        "type": WS_CHAT_SEND,
        "client_msg_id": client_msg_id,
        "content": content,
        "content_type": content_type,
    }
    if room_id:
        message["room_id"] = str(room_id)
    return message


def ping_message(ts_ms: int) -> dict[str, Any]:
    return {"type": WS_PING, "ts": int(ts_ms)}


def make_request_id(prefix: str = "c-") -> str:
    return f"{prefix}{uuid.uuid4().hex}"


def make_client_msg_id(prefix: str = "m-") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def unwrap_payload(body: Any) -> Any:
    """兼容统一响应包 ``{code,message,data}`` 与 A 现状的裸 JSON。

    含 ``data`` 字段时返回 ``data``，否则原样返回（房间接口是裸 JSON）。
    """
    if isinstance(body, Mapping) and "data" in body:
        return body["data"]
    return body


def extract_token(payload: Any) -> str | None:
    """从登录响应提取 JWT。

    目标契约用 ``data.access_token``（PROTOCOL.md §2.2）；同时兼容
    ``token`` / ``accessToken`` 等历史字段，方便 B 阶段落地前后的过渡。
    """
    data = unwrap_payload(payload)
    if not isinstance(data, Mapping):
        return None
    for key in ("access_token", "token", "accessToken", "jwt"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_user(payload: Any) -> dict[str, Any] | None:
    """从登录响应提取用户信息（``data.user`` 或扁平用户对象）。"""
    data = unwrap_payload(payload)
    if not isinstance(data, Mapping):
        return None
    user = data.get("user")
    if isinstance(user, Mapping):
        return dict(user)
    if "username" in data or "id" in data or "user_id" in data:
        return dict(data)
    return None


def parse_json_message(raw: Any) -> dict[str, Any] | None:
    """解析 WS 文本消息；非 JSON / 非对象返回 None（客户端忽略未知内容）。"""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def message_type(message: Any) -> str:
    if isinstance(message, Mapping):
        return str(message.get("type", "") or "")
    return ""
