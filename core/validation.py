"""登录/注册输入校验与用户信息清洗（纯逻辑）。"""

from __future__ import annotations

from typing import Any, Mapping

from core.rooms import ValidationError

MAX_USERNAME_LENGTH = 32
MAX_PASSWORD_LENGTH = 128
MIN_REGISTER_PASSWORD_LENGTH = 6

_SENSITIVE_KEY_PARTS = ("pass", "secret", "token", "credential")


def validate_username(raw: Any) -> str:
    """用户名：去首尾空白、1-32 字符、不含控制字符。"""
    username = str(raw or "").strip()
    if not username:
        raise ValidationError("请输入用户名")
    if len(username) > MAX_USERNAME_LENGTH:
        raise ValidationError(f"用户名最多 {MAX_USERNAME_LENGTH} 个字符")
    if any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise ValidationError("用户名不能包含控制字符")
    return username


def validate_password(raw: Any) -> str:
    """登录密码：只要求非空；**不 strip**（密码可能包含空格）。"""
    password = "" if raw is None else str(raw)
    if password == "":
        raise ValidationError("请输入密码")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"密码最长 {MAX_PASSWORD_LENGTH} 位")
    return password


def validate_register_password(raw: Any) -> str:
    password = validate_password(raw)
    if len(password) < MIN_REGISTER_PASSWORD_LENGTH:
        raise ValidationError(f"密码至少 {MIN_REGISTER_PASSWORD_LENGTH} 位")
    return password


def validate_login_input(username: Any, password: Any) -> tuple[str, str]:
    return validate_username(username), validate_password(password)


def validate_register_input(username: Any, password: Any, confirm: Any) -> tuple[str, str]:
    name = validate_username(username)
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
