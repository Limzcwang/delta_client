"""P1：文件日志（2MB×3 轮转）与敏感字段脱敏。"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from state.paths import ensure_data_dirs, log_path

MAX_LOG_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3
_HANDLER_FLAG = "_delta_client_file_handler"

_SENSITIVE_PATTERNS = (
    re.compile(
        r"(?i)\b(password|passwd|token|access_token|refresh_token|jwt|authorization)\b"
        r"(\s*[=:]\s*)([^\s,;\"']+)"
    ),
    re.compile(r'(?i)("(?:password|token|access_token|refresh_token|jwt)"\s*:\s*")[^"]+(")'),
)


def redact_sensitive(text: object) -> str:
    """把日志文本里的密码/token 值替换为 ``***``。"""
    value = str(text)
    for pattern in _SENSITIVE_PATTERNS:
        value = pattern.sub(lambda match: match.group(1) + match.group(2) + "***", value)
    return value


class SensitiveFilter(logging.Filter):
    """日志落盘前统一脱敏（不改业务日志内容）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_sensitive(record.getMessage())
        record.args = ()
        return True


def setup_logging(
    path: str | Path | None = None,
    *,
    max_bytes: int = MAX_LOG_BYTES,
    backup_count: int = BACKUP_COUNT,
    level: int = logging.INFO,
) -> Path:
    """初始化根日志：``%APPDATA%\\DeltaClient\\logs\\client.log``，按大小轮转。"""
    target = Path(path).expanduser() if path is not None else log_path()
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001
                pass
    if path is None:
        ensure_data_dirs([target.parent])
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(target),
            maxBytes=max(1024, int(max_bytes)),
            backupCount=max(1, int(backup_count)),
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        return target
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(SensitiveFilter())
    setattr(handler, _HANDLER_FLAG, True)
    root.addHandler(handler)
    return target


def shutdown_logging() -> None:
    """关闭本模块添加的文件 handler（测试/退出用）。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # noqa: BLE001
                pass
