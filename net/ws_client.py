"""WebSocket 客户端（websockets）：认证、心跳、指数退避重连与消息分发。

按 PROTOCOL.md §6 实现：
- 连接后第一条业务消息为 ``{"type":"auth","token":...}``；
- 收到 ``auth_ok`` 视为连接成功（退避计数清零）；
- 心跳：PROTOCOL PR#9 §6.1 服务端每 30s 下发 heartbeat，客户端 25s 主动 ping，
  90s 无任何消息判定失联并重连；
- 指数退避：1s/2s/4s… 上限 30s（:mod:`core.backoff`）；
- 未知消息类型原样交给回调，由 UI 忽略（协议要求客户端不因新增消息崩溃）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Mapping

from core import protocol
from core.backoff import ReconnectBackoff
from core.models import now_ms
from core.ws_close import AUTH_FAILED, REPLACED, RESTARTING, classify_close, classify_open_error

logger = logging.getLogger(__name__)

MessageCallback = Callable[[dict[str, Any]], None]
StateCallback = Callable[[str, dict[str, Any]], None]


class WsAuthError(Exception):
    """服务端返回 auth_error（token 过期/无效），重连没有意义。"""


class WsClient:
    """可重连的 WebSocket 客户端；回调在 asyncio 线程执行，UI 需自行切回主线程。"""

    is_mock = False

    def __init__(
        self,
        url: str,
        token: str,
        *,
        on_message: MessageCallback | None = None,
        on_state: StateCallback | None = None,
        heartbeat_interval: float = 25.0,
        heartbeat_timeout: float = 90.0,
        connect_timeout: float = 10.0,
        backoff: ReconnectBackoff | None = None,
        connect_factory: Callable[[str], Awaitable[Any]] | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.on_message = on_message
        self.on_state = on_state
        self.heartbeat_interval = float(heartbeat_interval)
        self.heartbeat_timeout = float(heartbeat_timeout)
        self.connect_timeout = float(connect_timeout)
        self.backoff = backoff or ReconnectBackoff(base=1.0, factor=2.0, max_delay=30.0)
        self._connect_factory = connect_factory
        self._ws: Any = None
        self._stopped = False
        self._state = "idle"
        self._last_rx = 0.0
        self._last_ping_epoch = 0
        self._last_ping_loop = 0.0
        self._stop_event = asyncio.Event()
        self._canvas_save_waiters: list[asyncio.Future] = []
        self.server_time: int | None = None
        self._close_code: int | None = None
        self._close_reason: str = ""

    # ---------- 状态 ----------
    @property
    def state(self) -> str:
        return self._state

    @property
    def connected(self) -> bool:
        return self._state == "connected"

    def _set_state(self, state: str, **info: Any) -> None:
        self._state = state
        callback = self.on_state
        if callback is None:
            return
        try:
            callback(state, info)
        except Exception:  # pragma: no cover - 回调异常不应拖垮连接
            logger.exception("WS 状态回调异常")

    def _emit(self, message: dict[str, Any]) -> None:
        callback = self.on_message
        if callback is None:
            return
        try:
            callback(message)
        except Exception:  # pragma: no cover
            logger.exception("WS 消息回调异常")

    # ---------- 连接 ----------
    def _import_websockets(self) -> Any:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - 依赖缺失时才触发
            raise RuntimeError("缺少 websockets 依赖，请先执行 pip install -r requirements.txt") from exc
        return websockets

    async def _open(self) -> Any:
        if self._connect_factory is not None:
            return await self._connect_factory(self.url)
        websockets = self._import_websockets()
        try:
            return await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    ping_interval=None,  # 应用层心跳，避免与协议 heartbeat 混淆
                    open_timeout=self.connect_timeout,
                    close_timeout=2,
                ),
                timeout=self.connect_timeout + 2,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"连接 {self.url} 超时") from exc

    async def run(self) -> None:
        """持续运行：连接 -> 认证 -> 收发；断开后按退避自动重连，直到 :meth:`close`。"""
        if self._stopped:  # close() 可能先于 run() 被调用
            self._set_state("stopped")
            return
        self._stop_event = asyncio.Event()
        self.backoff.reset()
        while not self._stopped:
            self._set_state("connecting", url=self.url)
            ws: Any = None
            try:
                ws = await self._open()
                await self._serve(ws)
            except WsAuthError as exc:
                self._set_state("auth_failed", message=str(exc))
                return
            except asyncio.CancelledError:
                raise
            except RuntimeError as exc:  # 依赖缺失等不可重试错误
                self._set_state("error", message=str(exc))
                return
            except Exception as exc:
                action = classify_open_error(exc)
                if action == AUTH_FAILED:
                    logger.info("WebSocket 握手认证失败：%s", exc)
                    self._set_state("auth_failed", message="登录已失效")
                    return
                logger.info("WebSocket 连接中断：%s", exc)
                self._set_state("reconnecting", error=str(exc))
            finally:
                if ws is not None:
                    try:
                        self._close_code = getattr(ws, "close_code", None)
                        self._close_reason = str(getattr(ws, "close_reason", "") or "")
                    except Exception:
                        self._close_code = None
                        self._close_reason = ""
                    try:
                        await ws.close()
                    except Exception:
                        pass
                self._ws = None
            action = classify_close(self._close_code, self._close_reason)
            if action == REPLACED:
                self._set_state("replaced", message="账号已在其他设备登录")
                return
            if action == AUTH_FAILED:
                self._set_state("auth_failed", message="登录已失效")
                return
            if action == RESTARTING:
                self._set_state("server_restarting", message="服务器更新中，正在重连")
            if self._stopped:
                break
            delay = self.backoff.next_delay()
            self._set_state("waiting", delay=delay)
            await self._sleep_or_stop(delay)
        self._set_state("stopped")

    async def _sleep_or_stop(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _serve(self, ws: Any) -> None:
        self._ws = ws
        loop = asyncio.get_running_loop()
        self._last_rx = loop.time()
        await ws.send(json.dumps(protocol.auth_message(self.token)))
        self._set_state("authenticating", url=self.url)
        heartbeat = asyncio.create_task(self._heartbeat_loop(ws), name="delta-ws-heartbeat")
        watchdog = asyncio.create_task(self._watchdog(ws), name="delta-ws-watchdog")
        try:
            async for raw in ws:
                self._last_rx = loop.time()
                message = protocol.parse_json_message(raw)
                if message is None:
                    continue
                mtype = protocol.message_type(message)
                if mtype == protocol.WS_AUTH_OK:
                    self.backoff.reset()
                    server_time = message.get("server_time")
                    if server_time is not None:
                        try:
                            self.server_time = int(server_time)
                        except (TypeError, ValueError):
                            self.server_time = None
                    self._set_state(
                        "connected",
                        user=message.get("user"),
                        heartbeat_interval_ms=message.get("heartbeat_interval_ms"),
                        server_time=self.server_time,
                    )
                elif mtype == protocol.WS_AUTH_ERROR:
                    text = str(message.get("message") or "认证失败，请重新登录")
                    self._set_state("auth_error", code=message.get("code"), message=text)
                    raise WsAuthError(text)
                elif mtype == protocol.WS_CANVAS_SNAPSHOT_SAVED:
                    self._resolve_save_waiters(message)
                elif mtype == "server_restarting":
                    self._set_state(
                        "server_restarting",
                        message=str(message.get("message") or "服务器更新中，正在重连"),
                    )
                elif mtype == protocol.WS_PONG:
                    try:
                        now_epoch = int(time.time() * 1000)
                        message["_client_sent_ms"] = int(self._last_ping_epoch or message.get("ts") or 0)
                        if self._last_ping_loop:
                            message["_rtt_ms"] = max(
                                0.0, (asyncio.get_running_loop().time() - self._last_ping_loop) * 1000
                            )
                    except Exception:  # noqa: BLE001
                        pass
                self._emit(message)
        finally:
            for task in (heartbeat, watchdog):
                task.cancel()
            await asyncio.gather(heartbeat, watchdog, return_exceptions=True)
            self._resolve_save_waiters(None)

    async def _heartbeat_loop(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                self._last_ping_epoch = now_ms()
                self._last_ping_loop = asyncio.get_running_loop().time()
                await ws.send(json.dumps(protocol.ping_message(self._last_ping_epoch)))
            except Exception:
                return

    async def _watchdog(self, ws: Any) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(min(5.0, max(1.0, self.heartbeat_timeout / 3.0)))
            idle = loop.time() - self._last_rx
            if idle > self.heartbeat_timeout:
                self._set_state("reconnecting", error=f"心跳超时（{idle:.0f}s 未收到服务端消息）")
                try:
                    await ws.close()
                except Exception:
                    pass
                return

    # ---------- 发送 ----------
    async def _send(self, payload: dict[str, Any]) -> bool:
        ws = self._ws
        if ws is None or not self.connected:
            return False
        try:
            await ws.send(json.dumps(payload, ensure_ascii=False))
            return True
        except Exception:
            return False

    async def join_room(self, room_code: str, password: str | None = None) -> bool:
        return await self._send(protocol.join_room_message(room_code, password))

    async def leave_room(self, room_id_or_code: str) -> bool:
        return await self._send(protocol.leave_room_message(room_id_or_code))

    async def send_chat(
        self,
        content: str,
        client_msg_id: str | None = None,
        room_id: str | None = None,
    ) -> str | None:
        """发送聊天消息，返回 ``client_msg_id``（发送失败返回 None）。

        - ``client_msg_id`` 由调用方预先提供并登记，服务端广播会原样回传，
          客户端据此把「发送中」更新为「已发送」，不重复插入；
        - ``room_id`` 服务端不读取（用会话房间），仅用于联调日志/扩展。
        """
        client_msg_id = client_msg_id or protocol.make_client_msg_id()
        sent = await self._send(protocol.chat_send_message(content, client_msg_id, room_id))
        return client_msg_id if sent else None

    async def send_canvas_op(self, op: dict[str, Any], rev: int, room_id: str) -> bool:
        """发送一条画板增量；``rev`` 由调用方保证每连接单调递增。"""
        return await self._send(protocol.canvas_op_message(room_id, rev, op))

    async def send_skill_update(
        self,
        room_id: str,
        captured_at: int,
        skills: Any,
        operator_id: str = "",
        operator_name: str = "",
    ) -> bool:
        """E2/E3a：上报本机技能状态（服务端时钟口径的 captured_at）。"""
        return await self._send(
            protocol.skill_share_update_message(
                room_id, captured_at, skills, operator_id, operator_name
            )
        )

    async def send_skill_off(self, room_id: str | None = None) -> bool:
        """E2：关闭技能共享。"""
        return await self._send(protocol.skill_share_off_message(room_id))

    async def save_canvas_snapshot(
        self,
        strokes: list[dict[str, Any]],
        rev: int,
        room_id: str,
        timeout: float = 3.0,
    ) -> dict[str, Any] | None:
        """发送全量画板快照并等待 ``canvas_snapshot_saved`` ack；超时返回 None。"""
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self._canvas_save_waiters.append(waiter)
        sent = await self._send(
            protocol.canvas_snapshot_save_message(room_id, rev, strokes)
        )
        if not sent:
            self._canvas_save_waiters.remove(waiter)
            return None
        try:
            return await asyncio.wait_for(waiter, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            if waiter in self._canvas_save_waiters:
                self._canvas_save_waiters.remove(waiter)

    def _resolve_save_waiters(self, payload: dict[str, Any] | None = None) -> None:
        for waiter in list(self._canvas_save_waiters):
            if not waiter.done():
                waiter.set_result(payload)
        self._canvas_save_waiters.clear()

    async def close(self) -> None:
        """停止重连并关闭当前连接（可重复调用）。"""
        self._stopped = True
        self._resolve_save_waiters(None)
        try:
            self._stop_event.set()
        except RuntimeError:
            pass
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
