"""登录/注册输入校验与用户信息清洗（纯逻辑）。"""

from __future__ import annotations

import re
from typing import Any, Mapping

from core.rooms import ValidationError

MAX_USERNAME_LENGTH = 32
MAX_PASSWORD_LENGTH = 128
MIN_REGISTER_PASSWORD_LENGTH = 6

#: 注册账号规则（F）：6–20 位字母/数字，至少含 1 个字母
REGISTER_USERNAME_MIN = 6
REGISTER_USERNAME_MAX = 20
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")
_HAS_LETTER_RE = re.compile(r"[A-Za-z]")

#: 昵称规则（F）：1–20 字符
NICKNAME_MIN = 1
NICKNAME_MAX = 20

#: 修改密码规则（F）：新密码 8–64 位
NEW_PASSWORD_MIN = 8
NEW_PASSWORD_MAX = 64

_SENSITIVE_KEY_PARTS = ("pass", "secret", "token", "credential")


def validate_username(raw: Any) -> str:
    """登录用用户名：去首尾空白、1-32 字符、不含控制字符（登录不套注册新规）。"""
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


def validate_register_password(raw: Any) -> str:
    password = validate_password(raw)
    if len(password) < MIN_REGISTER_PASSWORD_LENGTH:
        raise ValidationError(f"密码至少 {MIN_REGISTER_PASSWORD_LENGTH} 位")
    return password


def validate_new_password(raw: Any) -> str:
    """修改密码（F）：新密码 8–64 位。"""
    password = "" if raw is None else str(raw)
    if len(password) < NEW_PASSWORD_MIN:
        raise ValidationError(f"新密码至少 {NEW_PASSWORD_MIN} 位")
    if len(password) > NEW_PASSWORD_MAX:
        raise ValidationError(f"新密码最多 {NEW_PASSWORD_MAX} 位")
    return password


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
