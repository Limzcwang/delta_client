"""抓帧辅助：仅隐藏与游戏窗口相交的自家窗口，避免主窗口闪烁。"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable


def select_windows_to_hide(windows: Iterable[Any], game_rect: Any) -> list[Any]:
    """从候选顶层窗口中挑出可见且与 game_rect 相交的窗口。"""
    selected: list[Any] = []
    for window in windows:
        try:
            if not bool(window.isVisible()):
                continue
            geometry = window.frameGeometry()
            if game_rect is None or geometry.intersects(game_rect):
                selected.append(window)
        except Exception:  # noqa: BLE001
            continue
    return selected


def _to_qrect(game_rect: Any):
    from PySide6.QtCore import QRect

    if game_rect is None:
        return None
    if isinstance(game_rect, QRect):
        return game_rect
    try:
        x, y, width, height = (int(value) for value in game_rect)
    except Exception:  # noqa: BLE001
        return None
    return QRect(x, y, max(1, width), max(1, height))


def grab_frame_hidden(
    widget: Any,
    source: Any,
    *,
    game_rect: Any = None,
    windows: Iterable[Any] | None = None,
    delay: float = 0.12,
    only_if_active: bool = False,
    sleep: Callable[[float], None] | None = None,
    process_events: Callable[[], None] | None = None,
) -> Any:
    """隐藏与游戏窗口相交的客户端窗口 -> 等待重绘 -> source.grab() -> finally 恢复。"""
    from PySide6.QtWidgets import QApplication

    process = process_events or QApplication.processEvents
    waiter = sleep or time.sleep
    rect = _to_qrect(game_rect)
    if windows is None:
        if rect is None:
            candidates = [widget.window() if hasattr(widget, "window") else widget]
        else:
            candidates = list(QApplication.topLevelWidgets())
    else:
        candidates = list(windows)
    targets: list[Any] = []
    try:
        targets = select_windows_to_hide(candidates, rect)
        if only_if_active and hasattr(widget, "window"):
            if not bool(widget.window().isActiveWindow()):
                targets = []
    except Exception:  # noqa: BLE001
        targets = []
    try:
        for window in targets:
            try:
                window.hide()
            except RuntimeError:
                pass
        if targets:
            process()
            waiter(delay)
            process()
        return source.grab()
    finally:
        for window in targets:
            try:
                window.show()
                window.raise_()
            except (RuntimeError, AttributeError):
                pass
        if targets:
            process()


__all__ = ["grab_frame_hidden", "select_windows_to_hide"]
