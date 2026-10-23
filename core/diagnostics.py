"""0.2.12 内建诊断：内存环形缓冲，纯文本批量上传。"""
from __future__ import annotations
import json, logging, time, uuid
from collections import deque
from typing import Any
logger=logging.getLogger(__name__)

class DiagnosticsBuffer:
    def __init__(self, version: str = "", max_events: int = 2000):
        self.version = str(version)
        self.client_diag_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.events: deque[dict[str, Any]] = deque(maxlen=max(1, int(max_events)))
    def record(self, kind: str, payload: dict[str, Any]) -> None:
        kind = str(kind or "event")
        if kind not in ("env", "tick", "event"):
            kind = "event"
        self.events.append({"kind": kind, "payload": dict(payload or {})})
    def drain(self) -> list[dict[str, Any]]:
        events = list(self.events); self.events.clear(); return events
    def batch(self) -> dict[str, Any]:
        events = self.drain()
        # 512KB 上限：超限丢最旧事件，避免请求被服务端裁剪。
        while events and len(json.dumps(events, ensure_ascii=False).encode("utf-8")) > 512 * 1024:
            events.pop(0)
        return {
            "client_diag_id": self.client_diag_id,
            "session_id": self.session_id,
            "client_version": self.version,
            "events": events,
        }
    async def upload(self, server_url: str, token: str | None = None, *, timeout: float = 8.0) -> bool:
        events = self.drain()
        if not events:
            return True
        payload = {"client_diag_id": self.client_diag_id, "session_id": self.session_id,
                   "client_version": self.version, "events": events}
        headers = {"X-Diag-Id": self.client_diag_id}
        if token: headers["Authorization"] = f"Bearer {token}"
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.post(f"{server_url}/api/v1/diagnostics/batch", json=payload, headers=headers) as resp:
                    return resp.status < 400
        except Exception as exc:  # noqa: BLE001
            logger.debug("diagnostics upload failed: %s", exc)
            return False
