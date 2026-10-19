"""历史账号与加密密码存储（H2）。

- 文件：``%APPDATA%\\DeltaClient\\saved_logins.json``（可用 ``DELTA_SAVED_LOGINS_FILE`` 覆盖，
  与配置/会话同目录的约定由部署环境决定；不存在 APPDATA 时回退 ``~/.delta_client/``）；
- 密码用 Windows DPAPI 加密后 base64 存入 ``secret``；DPAPI 不可用时只保存账号、**绝不存明文**；
- 最多 5 个账号，按 ``last_used_at`` 倒序，超出淘汰最旧；
- 密码有效期 30 天（``expires_at = saved_at + 30d``，到期即不再自动带出）。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
import tempfile
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from core.validation import sanitize_username_input

SAVED_LOGINS_FILENAME = "saved_logins.json"
SAVED_LOGINS_VERSION = 1
MAX_SAVED_LOGINS = 5
PASSWORD_TTL_SECONDS = 30 * 24 * 60 * 60

#: DPAPI 标志：不弹 UI（服务/无交互环境也能加密）
CRYPTPROTECT_UI_FORBIDDEN = 0x1


class CryptoUnavailable(RuntimeError):
    """DPAPI 不可用（非 Windows / 调用失败）。"""


@dataclass(frozen=True)
class SavedLoginInfo:
    """供 UI 展示的条目（不含任何密文/明文密码）。"""

    username: str
    saved_at: float
    expires_at: float
    last_used_at: float
    has_password: bool
    expired: bool

    @property
    def last_used_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.last_used_at))

    @property
    def status_text(self) -> str:
        if self.has_password and self.expired:
            return "密码已过期，需重新输入"
        if self.has_password:
            return "已保存密码"
        return "需重新输入密码"


@dataclass
class SavedLogin:
    username: str
    secret: str = ""
    saved_at: float = 0.0
    expires_at: float = 0.0
    last_used_at: float = 0.0


def default_saved_logins_path() -> Path:
    """默认存储路径；``DELTA_SAVED_LOGINS_FILE`` 优先（测试/便携用）。"""
    override = str(os.environ.get("DELTA_SAVED_LOGINS_FILE", "") or "").strip()
    if override:
        return Path(override).expanduser()
    appdata = str(os.environ.get("APPDATA", "") or "").strip()
    if appdata:
        return Path(appdata) / "DeltaClient" / SAVED_LOGINS_FILENAME
    return Path.home() / ".delta_client" / SAVED_LOGINS_FILENAME


# ---------- Windows DPAPI ----------
def _blob_from_bytes(data: bytes) -> tuple[Any, Any]:
    buffer = ctypes.create_string_buffer(data)
    blob_type = _DATA_BLOB  # 延迟到调用时确保类已定义
    blob = blob_type(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt32():
    if sys.platform != "win32":
        raise CryptoUnavailable("DPAPI 仅 Windows 可用")
    try:
        return ctypes.windll.crypt32  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise CryptoUnavailable(f"无法加载 crypt32：{exc}") from exc


def _local_free(pointer: Any) -> None:
    try:
        ctypes.windll.kernel32.LocalFree(pointer)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def dpapi_protect(plaintext: str) -> str:
    """DPAPI 加密并 base64；失败抛 :class:`CryptoUnavailable`（调用方不得回退明文）。"""
    if sys.platform != "win32":
        raise CryptoUnavailable("DPAPI 仅 Windows 可用")
    crypt32 = _crypt32()
    data = str(plaintext).encode("utf-8")
    in_blob, in_buffer = _blob_from_bytes(data)
    out_blob = _DATA_BLOB()
    crypt32.CryptProtectData.restype = wintypes.BOOL
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "DeltaClient saved login",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    del in_buffer
    if not ok:
        raise CryptoUnavailable("CryptProtectData 调用失败")
    try:
        cipher = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _local_free(out_blob.pbData)
    return base64.b64encode(cipher).decode("ascii")


def dpapi_unprotect(token: str) -> str:
    """DPAPI 解密 base64 密文；任何失败抛 :class:`CryptoUnavailable`。"""
    if sys.platform != "win32":
        raise CryptoUnavailable("DPAPI 仅 Windows 可用")
    try:
        cipher = base64.b64decode(str(token).encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise CryptoUnavailable("保存的密码密文格式错误") from exc
    crypt32 = _crypt32()
    in_blob, in_buffer = _blob_from_bytes(cipher)
    out_blob = _DATA_BLOB()
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    del in_buffer
    if not ok:
        raise CryptoUnavailable("CryptUnprotectData 调用失败")
    try:
        plain = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        _local_free(out_blob.pbData)
    try:
        return plain.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise CryptoUnavailable("解密结果不是 UTF-8") from exc


class SavedLogins:
    """历史账号仓库（可注入时钟与加解密器，便于测试 30 天边界/DPAPI 降级）。"""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        clock: Callable[[], float] | None = None,
        protector: Callable[[str], str] | None = None,
        unprotector: Callable[[str], str] | None = None,
        max_entries: int = MAX_SAVED_LOGINS,
        ttl_seconds: int = PASSWORD_TTL_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser() if path else default_saved_logins_path()
        self._clock = clock or time.time
        self._protector = protector or dpapi_protect
        self._unprotector = unprotector or dpapi_unprotect
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._entries: list[SavedLogin] = []
        self.load()

    # ---------- 文件 ----------
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            self._entries = []
            return
        if not isinstance(raw, Mapping):
            self._entries = []
            return
        entries: list[SavedLogin] = []
        for item in raw.get("entries", []):
            if not isinstance(item, Mapping):
                continue
            username = sanitize_username_input(item.get("username"), "login")
            if not username:
                continue
            entries.append(
                SavedLogin(
                    username=username,
                    secret=str(item.get("secret") or ""),
                    saved_at=_as_float(item.get("saved_at")),
                    expires_at=_as_float(item.get("expires_at")),
                    last_used_at=_as_float(item.get("last_used_at")),
                )
            )
        entries.sort(key=lambda entry: entry.last_used_at, reverse=True)
        self._entries = entries[: self.max_entries]

    def save(self) -> Path | None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": SAVED_LOGINS_VERSION,
                "entries": [
                    {
                        "username": entry.username,
                        "secret": entry.secret,
                        "saved_at": entry.saved_at,
                        "expires_at": entry.expires_at,
                        "last_used_at": entry.last_used_at,
                    }
                    for entry in self._entries
                ],
            }
            fd, tmp = tempfile.mkstemp(
                prefix=".delta_saved_logins.", suffix=".tmp", dir=str(self.path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                try:
                    os.chmod(tmp, 0o600)
                except OSError:
                    pass
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            return self.path
        except OSError:
            return None

    # ---------- 查询 ----------
    def __len__(self) -> int:
        return len(self._entries)

    def raw_entries(self) -> list[SavedLogin]:
        """返回副本（测试/诊断用，含密文，不含明文）。"""
        return [
            SavedLogin(
                username=entry.username,
                secret=entry.secret,
                saved_at=entry.saved_at,
                expires_at=entry.expires_at,
                last_used_at=entry.last_used_at,
            )
            for entry in self._entries
        ]

    def now(self) -> float:
        return float(self._clock())

    def is_expired(self, entry: SavedLogin, now: float | None = None) -> bool:
        moment = self.now() if now is None else float(now)
        return moment >= entry.expires_at

    def infos(self) -> list[SavedLoginInfo]:
        now = self.now()
        return [
            SavedLoginInfo(
                username=entry.username,
                saved_at=entry.saved_at,
                expires_at=entry.expires_at,
                last_used_at=entry.last_used_at,
                has_password=bool(entry.secret),
                expired=self.is_expired(entry, now),
            )
            for entry in self._entries
        ]

    def recent_info(self) -> SavedLoginInfo | None:
        infos = self.infos()
        return infos[0] if infos else None

    def password_for(self, username: str) -> str | None:
        entry = self._find(username)
        if entry is None or not entry.secret:
            return None
        if self.is_expired(entry):
            return None
        try:
            return str(self._unprotector(entry.secret))
        except Exception:  # noqa: BLE001 - 解密失败按无密码处理
            return None

    def _find(self, username: str) -> SavedLogin | None:
        normalized = sanitize_username_input(username, "login")
        if not normalized:
            return None
        return next((entry for entry in self._entries if entry.username == normalized), None)

    # ---------- 变更 ----------
    def upsert(self, username: str, password: str | None = None) -> SavedLogin | None:
        normalized = sanitize_username_input(username, "login")
        if not normalized:
            return None
        now = self.now()
        existing = self._find(normalized)
        secret = ""
        if password:
            try:
                secret = str(self._protector(str(password)))
            except Exception:  # noqa: BLE001 - DPAPI 不可用：只存账号，绝不存明文
                secret = ""
        elif existing is not None:
            secret = existing.secret
        entry = SavedLogin(
            username=normalized,
            secret=secret,
            saved_at=now,
            expires_at=now + self.ttl_seconds,
            last_used_at=now,
        )
        self._entries = [item for item in self._entries if item.username != normalized]
        self._entries.insert(0, entry)
        self._entries.sort(key=lambda item: item.last_used_at, reverse=True)
        self._entries = self._entries[: self.max_entries]
        self.save()
        return entry

    def mark_password_invalid(self, username: str) -> bool:
        """清除该账号保存的密码（保留账号）；返回是否找到条目。"""
        entry = self._find(username)
        if entry is None:
            return False
        entry.secret = ""
        self.save()
        return True

    # 兼容语义更清晰的调用名
    clear_password = mark_password_invalid

    def remove(self, username: str) -> bool:
        normalized = sanitize_username_input(username, "login")
        before = len(self._entries)
        self._entries = [item for item in self._entries if item.username != normalized]
        if len(self._entries) == before:
            return False
        self.save()
        return True

    def clear(self) -> None:
        self._entries = []
        self.save()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
