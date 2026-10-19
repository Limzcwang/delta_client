"""WS 关闭原因分类：顶号/认证失效停止重连，其余网络原因继续。"""

from __future__ import annotations

REPLACED = "replaced"
AUTH_ERROR = "auth_error"
RESTARTING = "server_restarting"
RECONNECT = "reconnect"


def classify_close(code: int | None, reason: str = "") -> str:
    text = str(reason or "").lower()
    if code == 4001 or "replaced" in text or "顶号" in text or "another device" in text:
        return REPLACED
    if code in (4003, 4401):
        return AUTH_ERROR
    if code == 1012 or "restart" in text or "更新" in text:
        return RESTARTING
    return RECONNECT
