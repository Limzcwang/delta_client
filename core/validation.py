"""登录/注册输入校验与用户信息清洗（纯逻辑）。"""

from __future__ import annotations

import re
from typing import Any, Mapping

from core.rooms import ValidationError

MAX_USERNAME_LENGTH = 20
MAX_PASSWORD_LENGTH = 128

#: 注册/改密统一密码规则（F/B 后端）：8–32 位；登录仍只校验非空
NEW_PASSWORD_MIN = 8
NEW_PASSWORD_MAX = 32
#: 兼容旧常量名（注册密码下限，与 NEW_PASSWORD_MIN 共用同一规则，勿单独修改）
MIN_REGISTER_PASSWORD_LENGTH = NEW_PASSWORD_MIN

#: 注册账号规则（F）：6–20 位字母/数字，至少含 1 个字母
REGISTER_USERNAME_MIN = 6
REGISTER_USERNAME_MAX = 20
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")

#: 昵称规则（F）：1–20 字符
NICKNAME_MIN = 1
NICKNAME_MAX = 20

#: 账号输入框过滤（G）：输入时只保留合法字符（不 trim、不做全角转半角）
#: - register / login：均仅 ASCII 字母/数字，上限 20（不再兼容 _ - 老账号）
_USERNAME_INPUT_PATTERNS: dict[str, re.Pattern[str]] = {
    "register": re.compile(r"[^A-Za-z0-9]"),
    "login": re.compile(r"[^A-Za-z0-9]"),
}
_USERNAME_INPUT_LIMITS: dict[str, int] = {
    "register": REGISTER_USERNAME_MAX,
    "login": MAX_USERNAME_LENGTH,
}

_SENSITIVE_KEY_PARTS = ("pass", "secret", "token", "credential")


def validate_username(raw: Any) -> str:
    """登录用用户名：去首尾空白、1-20 字符、不含控制字符（登录不套注册新规）。"""
    username = str(raw or "").strip()
    if not username:
        raise ValidationError("请输入用户名")
    if len(username) > MAX_USERNAME_LENGTH:
        raise ValidationError(f"用户名最多 {MAX_USERNAME_LENGTH} 个字符")
    if any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise ValidationError("用户名不能包含控制字符")
    return username


def validate_register_username(raw: Any) -> str:
    """注册账号（F）：6–20 位字母或数字，且至少包含 1 个字母。"""
    username = str(raw or "").strip()
    if not username:
        raise ValidationError("请输入账号")
    if not (
        REGISTER_USERNAME_MIN <= len(username) <= REGISTER_USERNAME_MAX
    ):
        raise ValidationError(
            f"账号需为 {REGISTER_USERNAME_MIN}–{REGISTER_USERNAME_MAX} 位字母或数字"
        )
    if not _ALNUM_RE.fullmatch(username):
        raise ValidationError("账号只能包含字母和数字")
    if not _HAS_LETTER_RE.search(username):
        raise ValidationError("账号至少包含 1 个字母")
    return username


def _username_input_mode(mode: str) -> str:
    normalized = str(mode or "").strip().lower()
    if normalized not in _USERNAME_INPUT_PATTERNS:
        raise ValueError(f"未知账号输入模式：{mode!r}")
    return normalized


def sanitize_username_input(text: Any, mode: str = "register") -> str:
    """账号输入框即时过滤（纯函数，供 UI 在 textChanged/粘贴时调用）。

    - ``mode="register"``：仅 ASCII 字母和数字（中文、emoji、空格、全角字符、
      ``_ - .`` 等一律删除），长度截断到 20；
    - ``mode="login"``：与注册一致，仅 ASCII 字母和数字，截断到 20
      （不再兼容 ``dsh_test`` 等下划线老账号）；
    - 不做全角转半角、不 strip（非法空白直接删除）；粘贴时返回过滤后的合法部分。
    """
    normalized = _username_input_mode(mode)
    cleaned = _USERNAME_INPUT_PATTERNS[normalized].sub("", str(text or ""))
    return cleaned[: _USERNAME_INPUT_LIMITS[normalized]]


def sanitized_cursor_position(text: Any, cursor_position: Any, mode: str = "register") -> int:
    """过滤后光标位置：按“光标前保留的合法字符数”回退，而不是跳到末尾。

    ``cursor_position`` 超过文本长度时按文本末尾处理；非法字符被删除后，
    光标向左移动相应数量，截断时不超过最大长度。
    """
    raw = str(text or "")
    try:
        cursor = int(cursor_position)
    except (TypeError, ValueError):
        cursor = len(raw)
    cursor = max(0, min(cursor, len(raw)))
    prefix = sanitize_username_input(raw[:cursor], mode)
    return min(len(prefix), _USERNAME_INPUT_LIMITS[_username_input_mode(mode)])


def validate_nickname(raw: Any) -> str:
    """昵称（F）：1–20 字符，去首尾空白、不含控制字符（允许中文/空格）。"""
    nickname = str(raw or "").strip()
    if not nickname:
        raise ValidationError("请输入昵称")
    if len(nickname) > NICKNAME_MAX:
        raise ValidationError(f"昵称最多 {NICKNAME_MAX} 个字符")
    if any(ord(char) < 32 or ord(char) == 127 for char in nickname):
        raise ValidationError("昵称不能包含控制字符")
    return nickname


def validate_password(raw: Any) -> str:
    """登录密码：只要求非空；**不 strip**（密码可能包含空格）。"""
    password = "" if raw is None else str(raw)
    if password == "":
        raise ValidationError("请输入密码")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"密码最长 {MAX_PASSWORD_LENGTH} 位")
    return password


def _validate_password_length(
    raw: Any, minimum: int, maximum: int, label: str
) -> str:
    """注册/改密共用长度规则；密码不 strip（可能包含空格）。"""
    password = "" if raw is None else str(raw)
    if len(password) < minimum:
        raise ValidationError(f"{label}至少 {minimum} 位")
    if len(password) > maximum:
        raise ValidationError(f"{label}最多 {maximum} 位")
    return password


def validate_register_password(raw: Any) -> str:
    """注册密码：与改密共用 8–64 规则（登录密码仍只校验非空）。"""
    return _validate_password_length(raw, NEW_PASSWORD_MIN, NEW_PASSWORD_MAX, "密码")


def validate_new_password(raw: Any) -> str:
    """修改密码（F）：新密码 8–64 位。"""
    return _validate_password_length(raw, NEW_PASSWORD_MIN, NEW_PASSWORD_MAX, "新密码")


def validate_password_change(old: Any, new: Any, confirm: Any) -> tuple[str, str]:
    """修改密码表单校验：旧密码非空、新密码 8–64、两次输入一致。"""
    old_password = validate_password(old)
    new_password = validate_new_password(new)
    confirmation = "" if confirm is None else str(confirm)
    if new_password != confirmation:
        raise ValidationError("两次输入的新密码不一致")
    if old_password == new_password:
        raise ValidationError("新密码不能与旧密码相同")
    return old_password, new_password


def validate_login_input(username: Any, password: Any) -> tuple[str, str]:
    return validate_username(username), validate_password(password)


def validate_register_input(username: Any, password: Any, confirm: Any) -> tuple[str, str]:
    name = validate_register_username(username)
    first = validate_register_password(password)
    second = "" if confirm is None else str(confirm)
    if first != second:
        raise ValidationError("两次输入的密码不一致")
    return name, first


def sanitize_user(user: Mapping[str, Any] | None) -> dict[str, Any]:
    """清洗用户信息：去掉任何可能含密码/密钥/token 的字段，保证不落盘敏感数据。"""
    if not isinstance(user, Mapping):
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in user.items():
        text_key = str(key)
        lowered = text_key.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[text_key] = value
        elif isinstance(value, Mapping):
            # 只保留一层扁平标量，避免把嵌套的敏感结构写盘
            nested = sanitize_user(value)
            if nested:
                cleaned[text_key] = nested
    return cleaned
