"""WS 关闭/握手错误分类：401/403/顶号停止重连，网络/重启继续。"""

from __future__ import annotations

REPLACED = "replaced"
AUTH_FAILED = "auth_failed"
AUTH_ERROR = AUTH_FAILED  # 兼容旧调用
RESTARTING = "server_restarting"
RECONNECT = "reconnect"


def classify_close(code: int | None, reason: str = "") -> str:
    text = str(reason or "").lower()
    if code == 4001 or "replaced" in text or "顶号" in text or "another device" in text:
        return REPLACED
    if code in (401, 403, 4003, 4401):
        return AUTH_FAILED
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text:
        return AUTH_FAILED
    if code == 1012 or "restart" in text or "更新" in text:
        return RESTARTING
    return RECONNECT


def _exception_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    for owner in (response, exc):
        for attr in ("status_code", "status", "code"):
            value = getattr(owner, attr, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def classify_open_error(exc: BaseException) -> str:
    """websockets.InvalidStatus 等握手异常：401/403 为 auth_failed。"""
    status = _exception_status(exc)
    if status in (401, 403):
        return AUTH_FAILED
    text = str(exc).lower()
    if "401" in text or "403" in text or "unauthorized" in text or "forbidden" in text:
        return AUTH_FAILED
    return RECONNECT
