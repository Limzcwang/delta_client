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
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from core import protocol
from core.errors import ApiError, ErrorKind, api_error_from_exception, api_error_from_response
from core.models import Room, parse_room_list
from core.protocol import extract_token, extract_user, unwrap_payload
from core.rooms import normalize_room_code


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
        code = normalize_room_code(room_code)
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
                "POST", protocol.room_leave_path(normalize_room_code(room_code)), json_body={}
            )
        except ApiError as exc:
            if exc.status == 404:
                return  # 房间已关闭/路由未实现：离开是尽力而为
            raise

    async def get_me(self) -> dict[str, Any]:
        body = await self.request_data("GET", protocol.API_V1_ME)
        return dict(body) if isinstance(body, Mapping) else {}

    @staticmethod
    def _room_from_payload(body: Any) -> Room:
        if isinstance(body, Mapping):
            room = body.get("room")
            if isinstance(room, Mapping):
                return Room.from_api(room)
            return Room.from_api(body)
        return Room.from_api({})
