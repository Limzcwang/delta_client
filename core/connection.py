"""连通性自检结果模型：``/health`` + ``/api/v1/rooms?page=1`` 探测。

纯逻辑（只依赖 :mod:`core.errors`），UI 与单测都不需要网络。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.errors import ApiError, ErrorKind

CATEGORY_LABELS: dict[str, str] = {
    "ok": "正常",
    "timeout": "超时",
    "network": "网络不可达",
    "auth": "鉴权失效",
    "server": "服务端错误",
    "http_error": "HTTP 错误",
    "unexpected": "未知错误",
}


@dataclass(frozen=True)
class ProbeResult:
    """单个探测项（health / rooms）的结果。"""

    name: str
    ok: bool
    category: str = "ok"
    detail: str = ""
    status: int | None = None
    elapsed_ms: int | None = None

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)


def probe_ok(name: str, detail: str, *, status: int = 200, elapsed_ms: int | None = None) -> ProbeResult:
    return ProbeResult(name=name, ok=True, category="ok", detail=detail, status=status, elapsed_ms=elapsed_ms)


def probe_from_error(name: str, exc: BaseException, elapsed_ms: int | None = None) -> ProbeResult:
    """把探测异常归类成 UI 可直接展示的结果（超时/网络/鉴权/服务端/HTTP 错误）。"""
    if isinstance(exc, ApiError):
        if exc.kind == ErrorKind.TIMEOUT:
            category = "timeout"
        elif exc.kind == ErrorKind.NETWORK:
            category = "network"
        elif exc.is_auth_error:
            category = "auth"
        elif exc.kind == ErrorKind.SERVER:
            category = "server"
        else:
            category = "http_error"
        detail = exc.user_message
        return ProbeResult(
            name=name,
            ok=False,
            category=category,
            detail=detail,
            status=exc.status,
            elapsed_ms=elapsed_ms,
        )
    return ProbeResult(
        name=name,
        ok=False,
        category="unexpected",
        detail=str(exc).strip() or CATEGORY_LABELS["unexpected"],
        elapsed_ms=elapsed_ms,
    )


def _elapsed_text(elapsed_ms: int | None) -> str:
    return f"{elapsed_ms}ms" if elapsed_ms is not None else "-"


@dataclass(frozen=True)
class ConnectionCheck:
    """一次连通性测试的完整结果。"""

    server_url: str
    health: ProbeResult
    rooms: ProbeResult
    rooms_count: int | None = None

    @property
    def ok(self) -> bool:
        return self.health.ok and self.rooms.ok

    def format_text(self) -> str:
        lines = [f"服务器：{self.server_url}"]
        if self.health.ok:
            lines.append(f"HTTP 可达：✅ /health 200（{_elapsed_text(self.health.elapsed_ms)}）")
        else:
            lines.append(f"HTTP 可达：❌ {self.health.category_label}：{self.health.detail}")

        if self.rooms.ok:
            count = "?" if self.rooms_count is None else str(self.rooms_count)
            lines.append(
                f"房间接口：✅ /api/v1/rooms 200（{_elapsed_text(self.rooms.elapsed_ms)}，{count} 个房间）"
            )
        elif self.rooms.category == "auth":
            lines.append(f"鉴权失效：❌ {self.rooms.detail}")
        elif self.rooms.category == "timeout":
            lines.append(f"房间接口：❌ 超时：{self.rooms.detail}")
        elif self.rooms.category == "network":
            lines.append(f"房间接口：❌ 网络不可达：{self.rooms.detail}")
        else:
            lines.append(f"房间接口：❌ {self.rooms.category_label}：{self.rooms.detail}")
        return "\n".join(lines)


__all__ = [
    "CATEGORY_LABELS",
    "ConnectionCheck",
    "ProbeResult",
    "probe_from_error",
    "probe_ok",
]
