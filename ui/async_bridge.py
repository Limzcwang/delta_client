"""Qt 与 asyncio 的桥接：单后台事件循环 + 主线程回调投递。

PySide6 是同步事件循环，aiohttp/websockets 是 asyncio；这里用一个后台线程跑
asyncio loop，所有网络协程都通过 :meth:`AsyncBridge.submit` 提交，结果在 Qt 主线程
的定时器里回调，避免跨线程直接操作控件。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
from typing import Any, Callable, Coroutine

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)

SuccessCallback = Callable[[Any], None]
ErrorCallback = Callable[[BaseException], None]


class AsyncBridge(QObject):
    """在专用线程里运行 asyncio 事件循环，并提供线程安全的回调投递。"""

    POLL_INTERVAL_MS = 30

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="delta-async-loop", daemon=True)
        self._ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._pending: list[tuple[concurrent.futures.Future, SuccessCallback | None, ErrorCallback | None]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._drain)
        self._started = False

    # ---------- 生命周期 ----------
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()
        self._timer.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._timer.stop()
        for future, _, _ in list(self._pending):
            future.cancel()
        self._pending.clear()
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except RuntimeError:
            pass
        self._thread.join(timeout=2.0)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    # ---------- 提交任务 ----------
    def submit(
        self,
        coro: Coroutine[Any, Any, Any],
        on_success: SuccessCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> concurrent.futures.Future:
        """提交协程；``on_success``/``on_error`` 在 Qt 主线程执行。"""
        if not self._started or not self._thread.is_alive():
            coro.close()
            raise RuntimeError("异步桥未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if on_success is not None or on_error is not None:
            self._pending.append((future, on_success, on_error))
        return future

    # ---------- 后台 -> UI ----------
    def post(self, callback: Callable[[], None]) -> None:
        """从 asyncio 线程投递一个函数到 Qt 主线程执行。"""
        self._ui_queue.put(callback)

    # ---------- 主线程轮询 ----------
    def _drain(self) -> None:
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:  # pragma: no cover - 单个 UI 回调异常不应中断轮询
                logger.exception("异步回调（UI 队列）执行异常")

        for item in list(self._pending):
            future, on_success, on_error = item
            if not future.done():
                continue
            self._pending.remove(item)
            try:
                result = future.result()
            except concurrent.futures.CancelledError:
                continue
            except BaseException as exc:  # noqa: BLE001 - 统一交给 on_error
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception:  # pragma: no cover
                        logger.exception("异步错误回调执行异常")
                else:
                    logger.warning("异步任务失败且未提供错误回调：%s", exc)
            else:
                if on_success is not None:
                    try:
                        on_success(result)
                    except Exception:  # pragma: no cover
                        logger.exception("异步成功回调执行异常")

    # ---------- 线程入口 ----------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:  # pragma: no cover
                pass
            self._loop.close()
