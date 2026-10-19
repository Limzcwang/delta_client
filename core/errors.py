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
        self.message = message or default_message(kind)
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
        return user_message(self.kind, code=self.code, message=self.message, status=self.status)

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
