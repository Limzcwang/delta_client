"""会话状态：JWT 与当前用户信息（内存 + 可选落盘，绝不落盘密码）。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from core.validation import sanitize_user
from state.paths import session_path

SESSION_FILENAME = "session.json"
SESSION_VERSION = 1


def default_session_path() -> Path:
    """会话文件默认路径：``%APPDATA%\\DeltaClient\\session.json``。"""
    return session_path()


class Session:
    """登录态。

    安全约定：
    - token 可只存在内存（``persist_token=False``，默认）；
    - 开启落盘时只写 ``token`` 与清洗后的用户信息，**不写密码/任何凭据**；
    - :meth:`clear` 会同时删除落盘文件。
    """

    def __init__(
        self,
        token: str | None = None,
        user: Mapping[str, Any] | None = None,
        *,
        persist_token: bool = False,
        persist_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.token: str | None = str(token).strip() if token else None
        self.user: dict[str, Any] = sanitize_user(user)
        self.persist_token = bool(persist_token)
        self.persist_path = Path(persist_path).expanduser() if persist_path else default_session_path()

    # ---------- 查询 ----------
    @property
    def has_token(self) -> bool:
        return bool(self.token)

    @property
    def is_logged_in(self) -> bool:
        return bool(self.token or self.user)

    @property
    def username(self) -> str:
        """账号（仅个人资料/设置页对自己展示）。"""
        return str(self.user.get("username") or self.user.get("name") or "")

    @property
    def nickname(self) -> str:
        """昵称（F：展示层统一用昵称；旧协议缺 nickname 时回退 username）。"""
        return str(self.user.get("nickname") or "")

    @property
    def display_name(self) -> str:
        return self.nickname or self.username or "未命名用户"

    @property
    def user_id(self) -> str:
        value = self.user.get("id") or self.user.get("user_id") or self.user.get("userId")
        return str(value) if value is not None else ""

    def authorization_header(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SESSION_VERSION,
            "token": self.token,
            "user": sanitize_user(self.user),
        }

    # ---------- 变更 ----------
    def set_login(self, token: str | None, user: Mapping[str, Any] | None = None) -> None:
        self.token = str(token).strip() if token else None
        self.user = sanitize_user(user)
        self.save()

    def update_user(self, user: Mapping[str, Any] | None) -> dict[str, Any]:
        """本地资料更新（F）：合并昵称等字段并落盘（token 不变、不退出登录）。"""
        if isinstance(user, Mapping):
            merged = dict(self.user)
            merged.update(sanitize_user(user))
            self.user = merged
            self.save()
        return dict(self.user)

    def set_persist_token(self, enabled: bool) -> None:
        self.persist_token = bool(enabled)
        if not self.persist_token:
            self.remove_file()
        elif self.token:
            self.save()

    def clear(self) -> None:
        self.token = None
        self.user = {}
        self.remove_file()

    # ---------- 落盘 ----------
    def save(self) -> Path | None:
        """按需落盘；未开启持久化或没有 token 时不写文件。"""
        if not self.persist_token or not self.token:
            return None
        target = self.persist_path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.to_dict()
        tmp_fd, tmp_name = tempfile.mkstemp(prefix=".delta_session.", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            try:
                os.chmod(tmp_name, 0o600)
            except OSError:
                pass  # Windows 上权限位语义有限，忽略
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return target

    def remove_file(self) -> None:
        try:
            self.persist_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    @classmethod
    def from_file(
        cls,
        path: str | os.PathLike[str] | None = None,
        *,
        persist_token: bool = True,
    ) -> "Session | None":
        """读取落盘会话；文件缺失/损坏/无 token 时返回 None。"""
        target = Path(path).expanduser() if path else default_session_path()
        try:
            with target.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        token = data.get("token")
        if not isinstance(token, str) or not token.strip():
            return None
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        session = cls(token, user, persist_token=persist_token, persist_path=target)
        session.token = token.strip()
        return session

    def __repr__(self) -> str:  # pragma: no cover - 调试用，避免打印 token
        state = "logged-in" if self.is_logged_in else "anonymous"
        return f"Session({state}, user={self.username!r}, token={'***' if self.token else None})"
