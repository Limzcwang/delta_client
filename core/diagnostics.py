"""0.2.12 内建诊断：内存环形缓冲，纯文本分批上传。"""
from __future__ import annotations
import gzip, json, logging, time, uuid
from collections import deque
from typing import Any
logger=logging.getLogger(__name__)
MAX_BATCH_BYTES=512*1024
MAX_GZIP_BYTES=128*1024

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
    def _envelope(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        return {"client_diag_id": self.client_diag_id, "session_id": self.session_id,
                "client_version": self.version, "events": events}
    def split_batches(self, events: list[dict[str, Any]], *, max_bytes: int = MAX_BATCH_BYTES,
                      gzip_enabled: bool = False, max_gzip_bytes: int = MAX_GZIP_BYTES) -> list[dict[str, Any]]:
        batches: list[dict[str, Any]] = []
        current: list[dict[str, Any]] = []
        def fits(candidate):
            payload = self._envelope(candidate)
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return len(raw) <= max_bytes and (not gzip_enabled or len(gzip.compress(raw, 6)) <= max_gzip_bytes)
        for event in events:
            candidate = current + [event]
            if fits(candidate):
                current = candidate
                continue
            if current:
                batches.append(self._envelope(current)); current = [event]
            else:
                # 单条超大也保留，避免丢整批；服务端可裁剪
                current = [event]
        if current:
            batches.append(self._envelope(current))
        return batches
    def batch(self) -> dict[str, Any]:
        events = self.drain()
        return self.split_batches(events)[0] if events else self._envelope([])
    async def upload(self, server_url: str, token: str | None = None, *, timeout: float = 8.0, gzip_enabled: bool = False) -> bool:
        events = self.drain()
        if not events:
            return True
        batches = self.split_batches(events, gzip_enabled=gzip_enabled)
        headers = {"X-Diag-Id": self.client_diag_id}
        if token: headers["Authorization"] = f"Bearer {token}"
        ok_any = False
        try:
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                for payload in batches:
                    try:
                        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        h = dict(headers)
                        if gzip_enabled:
                            body = gzip.compress(body, 6); h["Content-Encoding"] = "gzip"
                        async with session.post(f"{server_url}/api/v1/diagnostics/batch", data=body,
                                                headers={**h, "Content-Type": "application/json"}) as resp:
                            if resp.status < 400:
                                ok_any = True
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("diagnostics batch failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("diagnostics upload failed: %s", exc)
        return ok_any
