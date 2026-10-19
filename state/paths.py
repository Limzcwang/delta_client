"""P1：Windows 用户数据目录、旧版路径迁移与日志路径（纯标准库）。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable

APP_NAME = "DeltaClient"
DATA_DIR_ENV = "DELTA_DATA_DIR"
CONFIG_ENV = "DELTA_CLIENT_CONFIG"
SESSION_ENV = "DELTA_SESSION_FILE"
SAVED_LOGINS_ENV = "DELTA_SAVED_LOGINS_FILE"
LOG_ENV = "DELTA_LOG_FILE"

LEGACY_CONFIG_NAME = ".delta_client.json"
LEGACY_SESSION_NAME = ".delta_client_session.json"


def app_data_dir() -> Path:
    """``%APPDATA%\\DeltaClient``；``DELTA_DATA_DIR`` 可覆盖（便携/测试）。"""
    override = str(os.environ.get(DATA_DIR_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    appdata = str(os.environ.get("APPDATA", "") or "").strip()
    if appdata:
        return Path(appdata) / APP_NAME
    return Path.home() / ".delta_client"


def _env_path(name: str, default: Path) -> Path:
    override = str(os.environ.get(name, "") or "").strip()
    return Path(override).expanduser() if override else default


def config_path() -> Path:
    return _env_path(CONFIG_ENV, app_data_dir() / "config.json")


def session_path() -> Path:
    return _env_path(SESSION_ENV, app_data_dir() / "session.json")


def saved_logins_path() -> Path:
    return _env_path(SAVED_LOGINS_ENV, app_data_dir() / "saved_logins.json")


def log_path() -> Path:
    return _env_path(LOG_ENV, app_data_dir() / "logs" / "client.log")


def legacy_config_path() -> Path:
    return Path.home() / LEGACY_CONFIG_NAME


def legacy_session_path() -> Path:
    return Path.home() / LEGACY_SESSION_NAME


def _backup_path(path: Path) -> Path:
    """找一个不覆盖已有备份的 ``.bak`` 名称。"""
    candidate = path.with_name(path.name + ".bak")
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = path.with_name(f"{path.name}.bak.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _migrate_file(source: Path, target: Path) -> Path | None:
    """复制旧文件到新路径，并把旧文件改名备份；失败时返回 None。"""
    if not source.is_file() or target.exists():
        return None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        backup = _backup_path(source)
        os.replace(source, backup)
        return backup
    except OSError:
        return None


def migrate_legacy_data() -> list[tuple[Path, Path]]:
    """首次启动：迁移 ``~/.delta_client*.json`` 到数据目录，保留旧文件备份。

    返回 ``(旧路径, 新路径)`` 列表。迁移失败不阻塞启动。
    """
    migrated: list[tuple[Path, Path]] = []
    for source, target in (
        (legacy_config_path(), config_path()),
        (legacy_session_path(), session_path()),
    ):
        backup = _migrate_file(source, target)
        if backup is not None:
            migrated.append((source, target))
    return migrated


def ensure_data_dirs(paths: Iterable[Path] | None = None) -> None:
    """预创建数据/日志目录；目录不可写时静默忽略。"""
    targets = list(paths) if paths is not None else [app_data_dir(), log_path().parent]
    for target in targets:
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
