"""统一错误模型：把 HTTP 状态码 / 业务码 / 网络异常映射成可展示的中文提示。

对应 PROTOCOL.md §7：HTTP 用数字业务码，WebSocket 用 UPPER_SNAKE 字符串码；
A 现状还有 FastAPI 的 ``detail``、房间接口的 ``error_code`` 等过渡格式，这里一并兼容。
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Mapping


class ErrorKind(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    AUTH = "auth"
    TOKEN_EXPIRED = "token_expired"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    ROOM_NOT_FOUND = "room_not_found"
    ROOM_PASSWORD_REQUIRED = "room_password_required"
    ROOM_PASSWORD_INVALID = "room_password_invalid"
    ROOM_FULL = "room_full"
    CONFLICT = "conflict"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    UNKNOWN = "unknown"


DEFAULT_MESSAGES: dict[ErrorKind, str] = {
    ErrorKind.NETWORK: "无法连接到服务器，请检查网络或服务器地址",
    ErrorKind.TIMEOUT: "连接服务器超时，请稍后重试",
    ErrorKind.AUTH: "用户名或密码错误，或登录已过期",
    ErrorKind.TOKEN_EXPIRED: "登录已过期，请重新登录",
    ErrorKind.FORBIDDEN: "没有权限执行该操作",
    ErrorKind.NOT_FOUND: "请求的资源不存在",
    ErrorKind.ROOM_NOT_FOUND: "房间不存在或已关闭",
    ErrorKind.ROOM_PASSWORD_REQUIRED: "该房间需要密码",
    ErrorKind.ROOM_PASSWORD_INVALID: "房间密码错误",
    ErrorKind.ROOM_FULL: "房间人数已满",
    ErrorKind.CONFLICT: "资源已存在或状态冲突",
    ErrorKind.VALIDATION: "请求参数不合法",
    ErrorKind.RATE_LIMIT: "操作过于频繁，请稍后再试",
    ErrorKind.SERVER: "服务器内部错误，请稍后重试",
    ErrorKind.UNKNOWN: "发生未知错误，请稍后重试",
}

#: HTTP 数字业务码（PROTOCOL.md §7.1）
CODE_KINDS: dict[Any, ErrorKind] = {
    40000: ErrorKind.VALIDATION,
    40100: ErrorKind.AUTH,
    40101: ErrorKind.TOKEN_EXPIRED,
    40102: ErrorKind.AUTH,
    40300: ErrorKind.FORBIDDEN,
    40400: ErrorKind.NOT_FOUND,
    40401: ErrorKind.NOT_FOUND,
    40402: ErrorKind.ROOM_NOT_FOUND,
    40900: ErrorKind.CONFLICT,
    40901: ErrorKind.CONFLICT,
    40902: ErrorKind.CONFLICT,
    42200: ErrorKind.VALIDATION,
    42900: ErrorKind.RATE_LIMIT,
    50000: ErrorKind.SERVER,
    50001: ErrorKind.SERVER,
    50300: ErrorKind.SERVER,
    # WebSocket / A 现状的字符串错误码（PROTOCOL.md §7.2）
    "AUTH_REQUIRED": ErrorKind.AUTH,
    "AUTH_FAILED": ErrorKind.AUTH,
    "TOKEN_EXPIRED": ErrorKind.TOKEN_EXPIRED,
    "FORBIDDEN": ErrorKind.FORBIDDEN,
    "NOT_FOUND": ErrorKind.NOT_FOUND,
    "ROOM_NOT_FOUND": ErrorKind.ROOM_NOT_FOUND,
    "ROOM_PASSWORD_REQUIRED": ErrorKind.ROOM_PASSWORD_REQUIRED,
    "ROOM_PASSWORD_INVALID": ErrorKind.ROOM_PASSWORD_INVALID,
    "ROOM_FULL": ErrorKind.ROOM_FULL,
    "ALREADY_IN_ROOM": ErrorKind.CONFLICT,
    "INVALID_PAYLOAD": ErrorKind.VALIDATION,
    "INTERNAL_ERROR": ErrorKind.SERVER,
    "RATE_LIMITED": ErrorKind.RATE_LIMIT,
    # B2b 实测：服务端这两处码与 PROTOCOL §7.2 的命名不同，客户端做别名兼容
    "NOT_AUTHENTICATED": ErrorKind.AUTH,
    "NOT_ROOM_MEMBER": ErrorKind.FORBIDDEN,
    "UNSUPPORTED_MESSAGE_TYPE": ErrorKind.VALIDATION,
    # PROTOCOL PR#9 §7.2 WebSocket 错误码
    "AUTH_INVALID": ErrorKind.AUTH,
    "AUTH_EXPIRED": ErrorKind.TOKEN_EXPIRED,
    "ALREADY_AUTHENTICATED": ErrorKind.VALIDATION,
    "NOT_ROOM_OWNER": ErrorKind.FORBIDDEN,
    "MEMBER_NOT_FOUND": ErrorKind.NOT_FOUND,
    "ROOM_CLOSED": ErrorKind.ROOM_NOT_FOUND,
    "INVALID_MESSAGE": ErrorKind.VALIDATION,
    "INVALID_JSON": ErrorKind.VALIDATION,
    "CANVAS_SEQ_GAP": ErrorKind.VALIDATION,
    "CANVAS_OUT_OF_ORDER": ErrorKind.VALIDATION,
    "INVALID_CANVAS_OP": ErrorKind.VALIDATION,
    # PROTOCOL PR#9 §7.3 HTTP data.error_code
    "ROOM_NAME_INVALID": ErrorKind.VALIDATION,
    "INVALID_BACKGROUND": ErrorKind.VALIDATION,
    "INVALID_VISIBILITY": ErrorKind.VALIDATION,
    "ROOM_PASSWORD_NOT_ALLOWED": ErrorKind.VALIDATION,
    "CANNOT_KICK_OWNER": ErrorKind.FORBIDDEN,
    "INVALID_PAGINATION": ErrorKind.VALIDATION,
    "INVALID_CURSOR": ErrorKind.VALIDATION,
    "ROOM_OWNER_MUST_CLOSE": ErrorKind.CONFLICT,
    "ROOM_CODE_GENERATION_FAILED": ErrorKind.SERVER,
    "ROOM_ALREADY_EXISTS": ErrorKind.CONFLICT,
    "CREATE_ROOM_FAILED": ErrorKind.SERVER,
    "JOIN_ROOM_FAILED": ErrorKind.SERVER,
    "LEAVE_ROOM_FAILED": ErrorKind.SERVER,
    "GET_PUBLIC_ROOMS_FAILED": ErrorKind.SERVER,
    "USER_NOT_IN_ROOM": ErrorKind.FORBIDDEN,
    "INVALID_DOMAIN": ErrorKind.VALIDATION,
    # F：账号/昵称/密码校验
    "INVALID_USERNAME": ErrorKind.VALIDATION,
    "USERNAME_TAKEN": ErrorKind.CONFLICT,
    "INVALID_NICKNAME": ErrorKind.VALIDATION,
    "NICKNAME_TAKEN": ErrorKind.CONFLICT,
    "INVALID_PASSWORD": ErrorKind.VALIDATION,
    "OLD_PASSWORD_INVALID": ErrorKind.VALIDATION,
    "INVALID_OLD_PASSWORD": ErrorKind.VALIDATION,
    "PASSWORD_MISMATCH": ErrorKind.VALIDATION,
    "PASSWORD_TOO_WEAK": ErrorKind.VALIDATION,
}

CODE_MESSAGES: dict[Any, str] = {
    40000: "请求参数不合法",
    40100: "请先登录",
    40101: "登录已过期，请重新登录",
    40102: "登录状态无效，请重新登录",
    40300: "没有权限执行该操作",
    40401: "用户不存在",
    40402: "房间不存在或已关闭",
    40900: "资源已存在",
    40901: "房间号冲突或房间已关闭",
    42200: "请求参数不合法",
    42900: "操作过于频繁，请稍后再试",
    50000: "服务器暂时不可用，请稍后重试",
    50001: "服务器暂时不可用，请稍后重试",
    50300: "服务暂不可用，请稍后重试",
    "ROOM_NOT_FOUND": "房间不存在或已关闭",
    "ROOM_PASSWORD_REQUIRED": "该房间需要密码",
    "ROOM_PASSWORD_INVALID": "房间密码错误",
    "ROOM_FULL": "房间人数已满",
    "ALREADY_IN_ROOM": "你已在该房间中",
    "AUTH_REQUIRED": "登录状态无效，请重新登录",
    "AUTH_FAILED": "登录状态无效，请重新登录",
    "TOKEN_EXPIRED": "登录已过期，请重新登录",
    "USERNAME_EXISTS": "用户名已存在",
    "USER_NOT_FOUND": "用户不存在",
    "USER_NOT_IN_ROOM": "你不在该房间中",
    "INVALID_DOMAIN": "房间类型不合法",
    "INVALID_PAYLOAD": "请求数据不合法",
    "RATE_LIMITED": "操作过于频繁，请稍后再试",
    # B2b 实测码
    "NOT_AUTHENTICATED": "请先完成认证，请重新登录",
    "NOT_ROOM_MEMBER": "你不在该房间中，请重新加入",
    "UNSUPPORTED_MESSAGE_TYPE": "当前版本不支持该消息类型",
    # PROTOCOL PR#9 §7.2 WebSocket 错误码
    "AUTH_INVALID": "登录凭证无效，请重新登录",
    "AUTH_EXPIRED": "登录已过期，请重新登录",
    "ALREADY_AUTHENTICATED": "已登录，无需重复认证",
    "NOT_ROOM_OWNER": "只有房主才能执行该操作",
    "MEMBER_NOT_FOUND": "目标成员不存在",
    "ROOM_CLOSED": "房间已关闭",
    "INVALID_MESSAGE": "消息内容不合法（1-2000 字符）",
    "INVALID_JSON": "消息不是合法 JSON",
    "CANVAS_SEQ_GAP": "画板状态不同步，正在重新同步",
    "CANVAS_OUT_OF_ORDER": "画板操作序号过期，已丢弃",
    "INVALID_CANVAS_OP": "画板操作不合法（点数/坐标/尺寸超限）",
    # PROTOCOL PR#9 §7.3 HTTP data.error_code
    "INVALID_BACKGROUND": "房间底图不合法",
    "INVALID_VISIBILITY": "房间可见性不合法",
    "ROOM_PASSWORD_NOT_ALLOWED": "公开房间不允许设置密码",
    "CANNOT_KICK_OWNER": "不能移出房主",
    "INVALID_PAGINATION": "分页参数不合法",
    "INVALID_CURSOR": "分页游标不合法",
    "ROOM_OWNER_MUST_CLOSE": "房主离开前需先关闭房间或转让",
    "ROOM_CODE_GENERATION_FAILED": "房间号生成失败，请重试",
    "ROOM_ALREADY_EXISTS": "房间号已存在",
    "CREATE_ROOM_FAILED": "创建房间失败，请稍后重试",
    "JOIN_ROOM_FAILED": "加入房间失败，请稍后重试",
    "LEAVE_ROOM_FAILED": "离开房间失败，请稍后重试",
    "GET_PUBLIC_ROOMS_FAILED": "获取房间列表失败，请稍后重试",
    "INTERNAL_ERROR": "服务端内部错误，请稍后重试",
    # F：账号/昵称/密码校验
    "INVALID_USERNAME": "账号需为 6–20 位字母或数字，且至少包含 1 个字母",
    "USERNAME_TAKEN": "账号已被占用",
    "INVALID_NICKNAME": "昵称需为 1–20 个字符",
    "NICKNAME_TAKEN": "昵称已被占用",
    "INVALID_PASSWORD": "新密码需为 8–64 位",
    "OLD_PASSWORD_INVALID": "旧密码错误",
    "INVALID_OLD_PASSWORD": "旧密码错误",
    "PASSWORD_MISMATCH": "两次输入的新密码不一致",
    "PASSWORD_TOO_WEAK": "密码强度不足，请使用 8–64 位密码",
    "ROOM_NAME_INVALID": "房间名称不合法（1–30 字符）",
}

#: HTTP 状态码兜底映射（无业务码时使用）
STATUS_KINDS: dict[int, ErrorKind] = {
    400: ErrorKind.VALIDATION,
    401: ErrorKind.AUTH,
    403: ErrorKind.FORBIDDEN,
    404: ErrorKind.NOT_FOUND,
    405: ErrorKind.VALIDATION,
    409: ErrorKind.CONFLICT,
    413: ErrorKind.VALIDATION,
    422: ErrorKind.VALIDATION,
    429: ErrorKind.RATE_LIMIT,
}

_PASSWORD_HINTS = ("密码", "password")


def _lookup(mapping: Mapping[Any, Any], code: Any) -> Any:
    """业务码可能是 int，也可能是数字字符串；两种都查。"""
    if code is None:
        return None
    try:
        if isinstance(code, str) and code.strip().isdigit():
            code = int(code.strip())
    except (TypeError, ValueError):
        pass
    if code in mapping:
        return mapping[code]
    text = str(code)
    return mapping.get(text)


def kind_for_status(status: int) -> ErrorKind:
    status = int(status)
    if status in STATUS_KINDS:
        return STATUS_KINDS[status]
    if 500 <= status <= 599:
        return ErrorKind.SERVER
    return ErrorKind.UNKNOWN


def kind_for_code(code: Any) -> ErrorKind | None:
    return _lookup(CODE_KINDS, code)


def code_message(code: Any) -> str | None:
    return _lookup(CODE_MESSAGES, code)


def default_message(kind: ErrorKind) -> str:
    return DEFAULT_MESSAGES.get(kind, DEFAULT_MESSAGES[ErrorKind.UNKNOWN])


def _refine_kind(kind: ErrorKind, message: str | None) -> ErrorKind:
    """A 现状可能只给文字 detail（没有码）；用关键词兜底识别房间密码类错误。

    只有在文案明确指向“房间密码”时才细化，避免把登录的
    “用户名或密码错误”误判成房间密码错误。
    """
    if not message:
        return kind
    text = str(message).lower()
    room_context = "房间" in text or "room" in text
    password_context = any(hint in text for hint in _PASSWORD_HINTS)
    if not (room_context and password_context):
        return kind
    if "invalid" in text or "错误" in text:
        return ErrorKind.ROOM_PASSWORD_INVALID
    if "required" in text or "需要" in text:
        return ErrorKind.ROOM_PASSWORD_REQUIRED
    return kind


def user_message(kind: ErrorKind, *, code: Any = None, message: str | None = None, status: int | None = None) -> str:
    """选出面向用户的提示。

    PROTOCOL.md §1.4 约定服务端 ``message`` 本身就是面向用户的简短文案，
    因此优先使用它；5xx/网络/未知错误则用客户端兜底文案（避免展示内部细节）。
    没有服务端文案时再看业务码文案。
    """
    if message and str(message).strip() and kind not in (
        ErrorKind.SERVER,
        ErrorKind.NETWORK,
        ErrorKind.TIMEOUT,
        ErrorKind.UNKNOWN,
    ):
        return str(message).strip()
    by_code = code_message(code)
    if by_code:
        return by_code
    return default_message(kind)


def parse_error_body(body: Any) -> tuple[str | None, Any | None, str | None]:
    """从错误响应体提取 ``(message, code, request_id)``。

    兼容：
    - 目标 ``{code,message,data,request_id}``
    - 房间接口 ``{detail:{error_code,message}}``
    - 用户接口 ``{detail:"字符串"}``
    - FastAPI 422 ``{detail:[{type,loc,msg}]}``
    """
    if body is None:
        return None, None, None
    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8", errors="replace")
        except Exception:
            return None, None, None
    if isinstance(body, str):
        text = body.strip()
        return (text[:300] or None), None, None
    if not isinstance(body, Mapping):
        return None, None, None

    request_id = body.get("request_id") or body.get("requestId")
    request_id = str(request_id) if request_id else None

    message: str | None = None
    code: Any = None

    detail = body.get("detail")
    if isinstance(detail, Mapping):
        code = detail.get("error_code") or detail.get("code")
        raw_message = detail.get("message")
        if raw_message:
            message = str(raw_message)
    elif isinstance(detail, list):
        code = 42200
        message = "请求参数不合法"
        for item in detail:
            if isinstance(item, Mapping) and item.get("msg"):
                message = f"请求参数不合法：{item['msg']}"
                break
    elif isinstance(detail, str) and detail.strip():
        message = detail.strip()

    if code is None:
        code = body.get("error_code") or body.get("code")
    if code is not None and str(code) == "200":
        code = None
    if message is None:
        raw_message = body.get("message")
        if raw_message:
            message = str(raw_message)
    if message is None and body.get("error"):
        raw_error = body.get("error")
        if isinstance(raw_error, Mapping):
            message = raw_error.get("message")
            code = code or raw_error.get("code")
            message = str(message) if message else None
        else:
            message = str(raw_error)

    # B2b 实测：统一响应包把具体错误码放在 data.error_code（顶层 code 只是 40000 之类类别）
    data_section = body.get("data")
    if isinstance(data_section, Mapping):
        nested_code = data_section.get("error_code")
        if nested_code is None:
            nested_code = data_section.get("errorCode")
        if nested_code is not None:
            code = nested_code
        if message is None:
            nested_message = data_section.get("message")
            if nested_message:
                message = str(nested_message)
    return message, code, request_id


class ApiError(Exception):
    """所有网络/接口错误的统一类型（UI 只处理这一种）。"""

    def __init__(
        self,
        kind: ErrorKind = ErrorKind.UNKNOWN,
        message: str = "",
        *,
        status: int | None = None,
        code: Any = None,
        detail: Any = None,
        request_id: str | None = None,
    ) -> None:
        self.kind = kind
        self.server_message = str(message).strip() if message else ""
        self.message = self.server_message or default_message(kind)
        self.status = status
        self.code = code
        self.detail = detail
        self.request_id = request_id
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志/调试
        parts = [self.kind.value]
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.code is not None:
            parts.append(f"code={self.code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return f"ApiError({' '.join(parts)}): {self.message}"

    @property
    def user_message(self) -> str:
        return user_message(
            self.kind, code=self.code, message=self.server_message, status=self.status
        )

    @property
    def is_auth_error(self) -> bool:
        return self.kind in (ErrorKind.AUTH, ErrorKind.TOKEN_EXPIRED)

    @property
    def needs_room_password(self) -> bool:
        return self.kind in (
            ErrorKind.ROOM_PASSWORD_REQUIRED,
            ErrorKind.ROOM_PASSWORD_INVALID,
        )


def api_error_from_response(status: int, body: Any) -> ApiError:
    """由 HTTP 状态 + 响应体构造 ApiError。"""
    message, code, request_id = parse_error_body(body)
    kind = kind_for_code(code) or kind_for_status(status)
    kind = _refine_kind(kind, message)
    return ApiError(kind, message or "", status=status, code=code, detail=body, request_id=request_id)


def api_error_from_exception(exc: BaseException) -> ApiError:
    """由网络异常构造 ApiError（不 import aiohttp，按类型名/模块名判断）。"""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ApiError(ErrorKind.TIMEOUT, detail=exc)
    name = type(exc).__name__.lower()
    module = (type(exc).__module__ or "").lower()
    if "timeout" in name:
        return ApiError(ErrorKind.TIMEOUT, detail=exc)
    if "aiohttp" in module or isinstance(exc, (OSError, ConnectionError)):
        return ApiError(ErrorKind.NETWORK, detail=exc)
    return ApiError(ErrorKind.UNKNOWN, str(exc)[:200], detail=exc)


def to_user_message(exc: BaseException) -> str:
    """任意异常 -> 可直接显示给用户的中文文案。"""
    if isinstance(exc, ApiError):
        return exc.user_message
    return str(exc).strip() or DEFAULT_MESSAGES[ErrorKind.UNKNOWN]
