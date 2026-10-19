"""HTTP API 客户端（aiohttp）：Base URL、JWT、超时与错误映射的统一封装。

按 PROTOCOL.md 目标契约实现（``/api/v1``），同时保留两个过渡兼容分支：

- 登录：``POST /api/v1/auth/login`` 404 时回退到 A 现状 ``POST /api/users/login``
  （无 token，仅用于后端 B 阶段上线前演示）；
- 公共房间列表：``GET /api/v1/rooms`` 404 时回退到 A 现状 ``GET /api/room/public/list``。
  TODO(协议对齐): B 阶段落地后删除回退分支，见 PROTOCOL.md §10 兼容策略。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from core import protocol
from core.canvas import CanvasSnapshot, parse_canvas_snapshot
from core.connection import ConnectionCheck, ProbeResult, probe_from_error, probe_ok
from core.errors import ApiError, ErrorKind, api_error_from_exception, api_error_from_response
from core.models import (
    ChatPage,
    MyRoomsPage,
    Room,
    RoomDetail,
    parse_chat_page,
    parse_my_rooms_page,
    parse_room_detail,
    parse_room_list,
)
from core.protocol import extract_token, extract_user, unwrap_payload
from core.rooms import room_reference


@dataclass(frozen=True)
class LoginResult:
    """登录结果：token 可能为 None（A 现状后端还不发 JWT）。"""

    token: str | None = None
    user: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def has_token(self) -> bool:
        return bool(self.token)


def _decode_body(text: str) -> Any:
    """尽量把响应文本解析成 JSON；失败时原样返回文本（用于错误提示）。"""
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


class ApiClient:
    """异步 HTTP 客户端。``token_provider`` 每次请求时读取最新 token。"""

    is_mock = False

    def __init__(
        self,
        base_url: str,
        token_provider: Callable[[], str | None] | None = None,
        *,
        timeout: float = 15.0,
        protocol_version: int = protocol.PROTOCOL_VERSION,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self._token_provider = token_provider
        self.timeout = float(timeout)
        self.protocol_version = int(protocol_version)
        self._session: Any = None
        self._aiohttp: Any = None

    # ---------- 基础设施 ----------
    def _import_aiohttp(self) -> Any:
        if self._aiohttp is None:
            try:
                import aiohttp  # 延迟导入：核心逻辑/单测不需要 aiohttp
            except ImportError as exc:  # pragma: no cover - 依赖缺失时才触发
                raise ApiError(
                    ErrorKind.NETWORK,
                    "缺少 aiohttp 依赖，请先执行 pip install -r requirements.txt",
                    detail=exc,
                ) from exc
            self._aiohttp = aiohttp
        return self._aiohttp

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _token(self) -> str | None:
        if callable(self._token_provider):
            try:
                return self._token_provider()
            except Exception:
                return None
        return None

    def _headers(self, auth: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"{protocol.CLIENT_NAME}/{protocol.CLIENT_VERSION}",
            "X-Protocol-Version": str(self.protocol_version),
            "X-Request-Id": protocol.make_request_id(),
        }
        token = self._token()
        if auth and token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _ensure_session(self) -> Any:
        aiohttp = self._import_aiohttp()
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"User-Agent": f"{protocol.CLIENT_NAME}/{protocol.CLIENT_VERSION}"},
            )
        return self._session

    async def close(self) -> None:
        session, self._session = self._session, None
        if session is not None and not session.closed:
            await session.close()

    # ---------- 请求 ----------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        try:
            session = await self._ensure_session()
            async with session.request(
                method,
                self.url(path),
                json=dict(json_body) if json_body is not None else None,
                params=dict(params) if params is not None else None,
                headers=self._headers(auth=auth),
            ) as response:
                text = await response.text()
                body = _decode_body(text)
                if response.status >= 400:
                    raise api_error_from_response(response.status, body)
                return body
        except ApiError:
            raise
        except asyncio.CancelledError:  # pragma: no cover - 取消不应被包装
            raise
        except Exception as exc:
            raise api_error_from_exception(exc) from exc

    async def request_data(self, method: str, path: str, **kwargs: Any) -> Any:
        return unwrap_payload(await self._request(method, path, **kwargs))

    # ---------- 认证 ----------
    async def login(self, username: str, password: str) -> LoginResult:
        """登录：优先目标接口；后端未就绪（404）时回退 A 现状接口。"""
        payload = {"username": username, "password": password}
        try:
            body = await self._request("POST", protocol.API_V1_LOGIN, json_body=payload, auth=False)
            return self._login_result(body, username)
        except ApiError as exc:
            if exc.status != 404:
                raise
        # TODO(协议对齐): B 阶段后删除该兼容分支
        body = await self._request("POST", protocol.API_LOGIN_LEGACY, json_body=payload, auth=False)
        result = self._login_result(body, username)
        return LoginResult(token=None, user=result.user, raw=body)

    def _login_result(self, body: Any, fallback_username: str) -> LoginResult:
        token = extract_token(body)
        user = extract_user(body) or {"username": fallback_username}
        return LoginResult(token=token, user=dict(user), raw=body)

    async def register(self, username: str, password: str) -> dict[str, Any]:
        """注册：B2b 已提供 ``POST /api/v1/auth/register``（响应同登录），404 时回退 A 现状接口。"""
        payload = {"username": username, "password": password}
        try:
            body = await self._request("POST", protocol.API_V1_REGISTER, json_body=payload, auth=False)
        except ApiError as exc:
            if exc.status != 404:
                raise
            # TODO(协议对齐): 旧后端兼容分支，确认所有环境升级后可删除
            body = await self._request(
                "POST", protocol.API_REGISTER_LEGACY, json_body=payload, auth=False
            )
        data = unwrap_payload(body)
        if isinstance(data, Mapping):
            return dict(data)
        return {"username": username}

    # ---------- 房间 ----------
    async def list_rooms(self) -> list[Room]:
        """公共房间列表：目标 ``GET /api/v1/rooms``，404 时回退 A 现状接口。"""
        try:
            body = await self.request_data("GET", protocol.API_V1_ROOMS)
            return parse_room_list(body)
        except ApiError as exc:
            if exc.status != 404:
                raise
        # TODO(协议对齐): B 阶段后删除该兼容分支
        legacy_body = await self._request("GET", protocol.API_ROOMS_LEGACY)
        return parse_room_list(unwrap_payload(legacy_body))

    async def list_my_rooms(self, page: int = 1, page_size: int = 20) -> MyRoomsPage:
        """H1「我的房间」：``GET /api/v1/rooms/mine?page=1&page_size=20``。"""
        body = await self.request_data(
            "GET",
            protocol.API_V1_MY_ROOMS,
            params={"page": max(1, int(page)), "page_size": max(1, int(page_size))},
        )
        return parse_my_rooms_page(body)

    async def create_room(self, name: str, visibility: str, password: str | None = None) -> Room:
        payload: dict[str, Any] = {"name": name, "visibility": visibility}
        if visibility == "private" and password:
            payload["password"] = password
        try:
            body = await self.request_data("POST", protocol.API_V1_ROOMS, json_body=payload)
        except ApiError as exc:
            if exc.status == 404:
                raise ApiError(
                    ErrorKind.NOT_FOUND,
                    "服务端尚未提供创建房间接口（PROTOCOL B 阶段），请切换 Mock 模式演示",
                    status=404,
                    detail=exc.detail,
                ) from exc
            raise
        return self._room_from_payload(body)

    async def join_room(self, room_code: str, password: str | None = None) -> Room:
        code = room_reference(room_code)
        payload: dict[str, Any] = {}
        if password:
            payload["password"] = password
        try:
            body = await self.request_data(
                "POST", protocol.room_join_path(code), json_body=payload
            )
        except ApiError as exc:
            if exc.status == 404 and exc.kind == ErrorKind.NOT_FOUND:
                raise ApiError(
                    ErrorKind.NOT_FOUND,
                    "服务端尚未提供加入房间接口（PROTOCOL B 阶段），请切换 Mock 模式演示",
                    status=404,
                    detail=exc.detail,
                ) from exc
            raise
        return self._room_from_payload(body)

    async def leave_room(self, room_code: str) -> None:
        try:
            await self._request(
                "POST", protocol.room_leave_path(room_reference(room_code)), json_body={}
            )
        except ApiError as exc:
            if exc.status == 404:
                return  # 房间已关闭/路由未实现：离开是尽力而为
            raise

    async def kick_member(self, room_id_or_code: str, user_id: str) -> dict[str, Any]:
        """H3：房主移出成员 ``POST /api/v1/rooms/{room_id_or_code}/kick``。"""
        body = await self.request_data(
            "POST",
            protocol.room_kick_path(room_reference(room_id_or_code)),
            json_body={"user_id": str(user_id)},
        )
        return dict(body) if isinstance(body, Mapping) else {}

    async def get_room_detail(self, room_id_or_code: str) -> RoomDetail:
        """房间详情（PROTOCOL PR#9 §3.2：``GET /api/v1/rooms/{room_id_or_code}``）。

        WS ``room_joined`` 丢失/重连失败时用它的 ``members`` 兜底成员展示。
        """
        body = await self.request_data("GET", protocol.room_detail_path(room_reference(room_id_or_code)))
        detail = parse_room_detail(body)
        if detail is None:
            raise ApiError(ErrorKind.UNKNOWN, "房间详情响应格式异常", detail=body)
        return detail

    async def get_messages(
        self,
        room_id_or_code: str,
        *,
        before: str | None = None,
        limit: int = 50,
    ) -> ChatPage:
        """聊天历史（PROTOCOL C）：按 ``created_at`` 倒序返回一页。

        ``before`` 为上一页最后一条消息 id（字符串，服务端按 created_at 过滤）；
        向上翻页时把它传回即可。
        """
        params: dict[str, Any] = {"limit": max(1, min(100, int(limit)))}
        if before:
            params["before"] = str(before)
        body = await self.request_data(
            "GET",
            protocol.room_messages_path(room_reference(room_id_or_code)),
            params=params,
        )
        return parse_chat_page(body)

    async def get_canvas(self, room_id_or_code: str) -> CanvasSnapshot:
        """画板快照（PROTOCOL D）：``GET /api/v1/rooms/{ref}/canvas``。

        ``room_joined.canvas_snapshot`` 缺失/为空时用作 fallback；无快照时服务端
        返回 ``strokes:[], rev:0``。
        """
        body = await self.request_data(
            "GET", protocol.room_canvas_path(room_reference(room_id_or_code))
        )
        return parse_canvas_snapshot(body)

    async def check_connection(self) -> ConnectionCheck:
        """连通性自检：``/health`` + ``GET /api/v1/rooms?page=1``。

        分别归类 HTTP 可达 / 鉴权失效 / 超时 / 网络 / 服务端错误，供设置页展示。
        """
        health = await self._probe_health()
        rooms, rooms_count = await self._probe_rooms()
        return ConnectionCheck(
            server_url=self.base_url,
            health=health,
            rooms=rooms,
            rooms_count=rooms_count,
        )

    async def _probe_health(self) -> ProbeResult:
        started = time.monotonic()
        try:
            body = await self._request("GET", protocol.API_HEALTH, auth=False)
        except Exception as exc:  # noqa: BLE001 - 探测不抛出，统一转结果（CancelledError 不吞）
            error = exc if isinstance(exc, ApiError) else api_error_from_exception(exc)
            return probe_from_error("health", error, elapsed_ms=_elapsed_ms(started))
        status_text = ""
        if isinstance(body, Mapping):
            status_text = str(body.get("status") or body.get("message") or "").strip()
        detail = "/health 200" + (f"（{status_text}）" if status_text else "")
        return probe_ok("health", detail, status=200, elapsed_ms=_elapsed_ms(started))

    async def _probe_rooms(self) -> tuple[ProbeResult, int | None]:
        started = time.monotonic()
        try:
            body = await self._request(
                "GET", protocol.API_V1_ROOMS, params={"page": 1}
            )
        except Exception as exc:  # noqa: BLE001 - 同上，CancelledError 继续向上传播
            error = exc if isinstance(exc, ApiError) else api_error_from_exception(exc)
            return probe_from_error("rooms", error, elapsed_ms=_elapsed_ms(started)), None
        rooms = parse_room_list(unwrap_payload(body))
        detail = f"/api/v1/rooms 200（{len(rooms)} 个房间）"
        return probe_ok("rooms", detail, status=200, elapsed_ms=_elapsed_ms(started)), len(rooms)

    async def get_me(self) -> dict[str, Any]:
        body = await self.request_data("GET", protocol.API_V1_ME)
        return dict(body) if isinstance(body, Mapping) else {}

    # ---------- F：个人资料 / 房间管理 ----------
    async def update_nickname(self, nickname: str) -> dict[str, Any]:
        """修改昵称：``PATCH /api/v1/users/me`` body ``{"nickname": ...}``（F 契约）。

        后端响应形如 ``{"user": {...}}``；兼容直接返回 user 字段的实现。
        """
        body = await self.request_data(
            "PATCH", protocol.API_V1_ME, json_body={"nickname": nickname}
        )
        if isinstance(body, Mapping):
            user = body.get("user")
            if isinstance(user, Mapping):
                return dict(user)
            return dict(body)
        return {"nickname": nickname}

    async def change_password(self, old_password: str, new_password: str) -> None:
        """修改密码：``POST /api/v1/users/me/password``（F 契约）。

        body ``{"old_password","new_password"}``；成功 200，token 继续有效。
        错误由后端 ``data.error_code`` 提供：``WRONG_OLD_PASSWORD`` /
        ``INVALID_NEW_PASSWORD``，客户端统一映射为用户文案。
        """
        await self._request(
            "POST",
            protocol.API_V1_ME_PASSWORD,
            json_body={"old_password": old_password, "new_password": new_password},
        )

    async def update_room(
        self,
        room_id_or_code: str,
        *,
        name: str | None = None,
        password: str | None = None,
    ) -> Room:
        """房主修改房间名/密码：``PATCH /api/v1/rooms/{room_id_or_code}``（F）。"""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if password is not None:
            payload["password"] = password
        body = await self.request_data(
            "PATCH",
            protocol.room_detail_path(room_reference(room_id_or_code)),
            json_body=payload,
        )
        return self._room_from_payload(body)

    async def delete_room(self, room_id_or_code: str) -> bool:
        """房主删除/关闭房间：``DELETE /api/v1/rooms/{room_id_or_code}``（F）。"""
        body = await self.request_data(
            "DELETE", protocol.room_detail_path(room_reference(room_id_or_code))
        )
        if isinstance(body, Mapping):
            return bool(body.get("closed", True))
        return True

    @staticmethod
    def _room_from_payload(body: Any) -> Room:
        if isinstance(body, Mapping):
            room = body.get("room")
            if isinstance(room, Mapping):
                return Room.from_api(room)
            return Room.from_api(body)
        return Room.from_api({})


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))
