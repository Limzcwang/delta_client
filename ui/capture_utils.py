"""抓帧辅助：在抓屏前隐藏客户端窗口，避免 mss 抓到设置页/房间自身。"""

from __future__ import annotations

import time
from typing import Any, Callable


def grab_frame_hidden(
    widget: Any,
    source: Any,
    *,
    delay: float = 0.2,
    only_if_active: bool = False,
    sleep: Callable[[float], None] | None = None,
    process_events: Callable[[], None] | None = None,
) -> Any:
    """隐藏 widget 所在顶层窗口 -> 等待重绘 -> source.grab() -> finally 恢复。"""
    from PySide6.QtWidgets import QApplication

    window = widget.window() if hasattr(widget, "window") else widget
    process = process_events or QApplication.processEvents
    waiter = sleep or time.sleep
    try:
        visible = bool(window.isVisible())
        active = True
        if only_if_active and hasattr(window, "isActiveWindow"):
            active = bool(window.isActiveWindow())
        should_hide = visible and active
    except Exception:  # noqa: BLE001
        visible = False
        should_hide = False
    try:
        if should_hide:
            window.hide()
            process()
            waiter(delay)
            process()
        return source.grab()
    finally:
        if should_hide:
            window.show()
            try:
                window.raise_()
            except Exception:  # noqa: BLE001
                pass
            process()
