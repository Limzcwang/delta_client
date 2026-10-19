"""房间号/房间名/可见性校验（纯逻辑，PROTOCOL.md §4）。"""

from __future__ import annotations

import re
from typing import Any, Mapping

ROOM_CODE_LENGTH = 5
ROOM_CODE_PATTERN = re.compile(r"^[A-Z0-9]{5}$")
MAX_ROOM_NAME_LENGTH = 32
MAX_ROOM_PASSWORD_LENGTH = 64
VISIBILITIES = ("public", "private")


class ValidationError(ValueError):
    """用户输入校验失败（UI 直接展示 message）。"""


def normalize_room_code(raw: Any) -> str:
    """房间号统一转大写并去掉首尾空白（PROTOCOL.md §4）。"""
    return str(raw or "").strip().upper()


def is_valid_room_code(code: Any) -> bool:
    """判断房间号是否合法（输入会先规范化：去空白 + 转大写）。"""
    return bool(ROOM_CODE_PATTERN.fullmatch(normalize_room_code(code)))


def room_reference(raw: Any) -> str:
    """房间引用：5 位房间号规范化为大写，其它（如内部 room_id）原样保留。

    PROTOCOL §3.2 起路径参数为 ``{room_id_or_code}``，客户端可能同时拿到
    code 与内部 id；内部 id 往往是大小写敏感的字符串，不能盲目 upper()。
    """
    text = str(raw or "").strip()
    return normalize_room_code(text) if is_valid_room_code(text) else text


def validate_room_code(raw: Any) -> str:
    """校验并返回规范化房间号，非法时抛 :class:`ValidationError`。"""
    code = normalize_room_code(raw)
    if not code:
        raise ValidationError("请输入房间号")
    if not is_valid_room_code(code):
        raise ValidationError("房间号必须是 5 位大写字母或数字（A-Z / 0-9）")
    return code


def validate_room_name(raw: Any) -> str:
    """房间名：1-32 字符，不允许换行/制表等控制字符。"""
    name = str(raw or "").strip()
    if not name:
        raise ValidationError("请输入房间名称")
    if len(name) > MAX_ROOM_NAME_LENGTH:
        raise ValidationError(f"房间名称最多 {MAX_ROOM_NAME_LENGTH} 个字符")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValidationError("房间名称不能包含控制字符")
    return name


def validate_visibility(raw: Any) -> str:
    """可见性只能是 ``public`` / ``private``（也接受中文/布尔别名）。"""
    if isinstance(raw, bool):
        return "private" if raw else "public"
    text = str(raw or "").strip().lower()
    if text in ("public", "公开", "公开房间"):
        return "public"
    if text in ("private", "私有", "私有房间", "私密"):
        return "private"
    raise ValidationError("房间可见性必须是 public 或 private")


def validate_room_password(password: Any, visibility: str) -> str | None:
    """私有房间必须有密码；公开房间忽略密码。密码不 strip（允许空格）。"""
    if visibility != "private":
        return None
    if password is None or str(password) == "":
        raise ValidationError("私有房间必须设置密码")
    text = str(password)
    if len(text) > MAX_ROOM_PASSWORD_LENGTH:
        raise ValidationError(f"房间密码最多 {MAX_ROOM_PASSWORD_LENGTH} 个字符")
    return text


def room_has_password(room: Mapping[str, Any]) -> bool:
    """判断房间是否上锁，兼容目标字段与 A 现状字段。"""
    for key in ("has_password", "hasPassword", "password_required", "is_private", "private", "locked"):
        if key in room:
            value = room.get(key)
            if isinstance(value, str):
                if value.strip().lower() in ("1", "true", "yes", "private"):
                    return True
            elif value:
                return True
    domain = room.get("domain")
    if isinstance(domain, (int, str)):
        try:
            if int(domain) == 2:  # A 现状：1 公共 / 2 私有
                return True
        except (TypeError, ValueError):
            pass
    return False
