"""E4：技能 CD 悬浮窗（无边框/置顶/鼠标穿透/编辑模式/跟随游戏窗口）。"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from typing import Any, Callable, Iterable

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from core.operators import OperatorCatalog
from core.skills import SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState, format_countdown
from state.crash_logging import set_current_step

logger = logging.getLogger(__name__)

OVERLAY_WIDTH = 300
ROW_HEIGHT = 44
HEADER_HEIGHT = 24
PADDING = 8
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def _widget_alive(widget: Any) -> bool:
    """PySide 对象已被 C++ 销毁时返回 False，避免解引用失效 HWND。"""
    try:
        from shiboken6 import isValid  # type: ignore[import-not-found]

        if not bool(isValid(widget)):
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


def _widget_visible(widget: Any) -> bool:
    try:
        return bool(widget.isVisible())
    except (RuntimeError, AttributeError):
        return False


def _apply_win32_topmost(widget: Any) -> bool:
    """强制置顶 + WS_EX_NOACTIVATE（Windows）；失败只记录 debug。"""
    if sys.platform != "win32":
        return False
    if not _widget_alive(widget) or not _widget_visible(widget):
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = int(widget.winId())
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        ok = bool(user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags))
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.debug("悬浮窗置顶失败：%s", exc)
        return False


class SkillOverlay(QWidget):
    """紧凑技能条：每队友一行，三槽 CD；默认鼠标穿透，编辑模式可拖动。"""

    position_changed = Signal(int, int)
    edit_mode_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.setWindowOpacity(0.30)
        self.states: list[SkillState] = []
        self.catalog: OperatorCatalog | None = None
        self.status = "等待游戏窗口"
        self._edit_mode = False
        self._scale = 1.0
        self._drag_offset: QPoint | None = None
        self._drag_axis: str | None = None
        self._server_now: Callable[[], int] = lambda: int(time.time() * 1000)
        self._base_opacity = 0.30
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.update)
        self._timer.start()
        self.resize(OVERLAY_WIDTH, 100)

    # ---------- 配置 ----------
    def set_scale(self, scale: float) -> None:
        self._scale = max(0.6, min(2.0, float(scale)))
        self.resize(max(160, int(OVERLAY_WIDTH * self._scale)), max(48, self._content_height()))
        self.update()

    @property
    def scale(self) -> float:
        return self._scale

    def set_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(max(0.10, min(1.0, float(opacity))))

    @property
    def opacity(self) -> float:
        return float(self.windowOpacity())

    def set_states(self, states: Iterable[SkillState], catalog: OperatorCatalog | None = None) -> None:
        self.states = list(states)
        self.catalog = catalog
        self.status = "" if self.states else "等待队友共享技能"
        self.resize(self.width(), max(48, self._content_height()))
        self.update()

    def set_status(self, status: str) -> None:
        self.status = str(status)
        self.update()

    def set_server_now(self, provider: Callable[[], int]) -> None:
        self._server_now = provider

    def set_edit_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._edit_mode:
            return
        self._edit_mode = enabled
        self.setCursor(Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not enabled)
        # 编辑时完全可见；退出恢复用户配置（默认 30%）。
        self.setWindowOpacity(1.0 if enabled else max(0.10, min(1.0, self._base_opacity)))
        if enabled:
            self._drag_axis = None
        if enabled and self.isVisible():
            self.raise_()
        self.edit_mode_changed.emit(enabled)

    @property
    def edit_mode(self) -> bool:
        return self._edit_mode

    def drag_handle_rect(self) -> QRect:
        """编辑模式中心单一四向拖动手柄（28×28）。"""
        size = 28
        return QRect(self.width() // 2 - size // 2, self.height() // 2 - size // 2 - 4, size, size)

    def _draw_cross_handle(self, painter: QPainter) -> None:
        rect = self.drag_handle_rect()
        painter.setPen(QPen(QColor("#f5a800"), 1))
        painter.setBrush(QColor(24, 34, 53, 235))
        painter.drawRoundedRect(rect, 7, 7)
        center = rect.center()
        cx, cy = center.x(), center.y()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#f5a800"))
        # 横向/纵向连杆
        painter.drawRoundedRect(QRect(cx - 9, cy - 2, 18, 4), 1, 1)
        painter.drawRoundedRect(QRect(cx - 2, cy - 9, 4, 18), 1, 1)
        # 四向实心箭头
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            path = QPainterPath()
            if dx == 0:
                tip = QPoint(cx, cy + dy * 10)
                a = QPoint(cx - 5, cy + dy * 4)
                b = QPoint(cx + 5, cy + dy * 4)
            else:
                tip = QPoint(cx + dx * 10, cy)
                a = QPoint(cx + dx * 4, cy - 5)
                b = QPoint(cx + dx * 4, cy + 5)
            path.moveTo(tip)
            path.lineTo(a)
            path.lineTo(b)
            path.closeSubpath()
            painter.drawPath(path)
        painter.setPen(QColor("#8b98ab"))
        font = QFont(self.font())
        font.setPointSize(7)
        painter.setFont(font)
        painter.drawText(
            QRect(rect.left() - 20, rect.bottom() + 1, rect.width() + 40, 14),
            Qt.AlignmentFlag.AlignHCenter, "拖动移动",
        )

    def _content_height(self) -> int:
        scale = self._scale
        rows = max(1, len(self.states))
        return int((HEADER_HEIGHT + rows * ROW_HEIGHT + PADDING) * scale)

    def _teammate_name(self, state: SkillState) -> str:
        operator = self.catalog.resolve(state.operator_id, state.operator) if self.catalog else None
        return operator.display_name if operator is not None else (state.operator or state.display_name)

    def _slot_text(self, state: SkillState, kind: str) -> str:
        slot = state.slot(kind)
        server_now = int(self._server_now())
        remaining = slot.remaining_now(state.captured_at, server_now)
        state_name = slot.effective_state(state.captured_at, server_now)
        if state_name == "unknown":
            return "?"
        if state_name == "ready":
            return "就绪"
        if kind == SLOT_ULTIMATE:
            return f"{int(slot.percent)}% {format_countdown(remaining)}"
        return format_countdown(remaining)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setBrush(QColor(12, 18, 26, 210))
        painter.setPen(QPen(QColor("#ffb61f" if self._edit_mode else "#2a3542"), 2 if self._edit_mode else 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)

        scale = self._scale
        font = QFont(self.font())
        font.setPointSize(max(7, int(9 * scale)))
        painter.setFont(font)
        painter.setPen(QColor("#8b98a8"))
        painter.drawText(
            QRect(PADDING, 4, self.width() - PADDING * 2, int(HEADER_HEIGHT * scale)),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "技能共享" + (" · 编辑模式" if self._edit_mode else ""),
        )

        if not self.states:
            painter.setPen(QColor("#ffd071"))
            painter.drawText(
                QRect(PADDING, int(HEADER_HEIGHT * scale), self.width() - PADDING * 2, int(ROW_HEIGHT * scale)),
                Qt.AlignmentFlag.AlignCenter,
                self.status,
            )
            painter.end()
            return

        y = HEADER_HEIGHT * scale
        for state in self.states:
            name = self._teammate_name(state)
            painter.setPen(QColor("#e6edf5"))
            painter.drawText(
                QRect(int(PADDING * scale), int(y + 2), int(104 * scale), int(ROW_HEIGHT * scale)),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                name[:8],
            )
            texts = [self._slot_text(state, kind) for kind in (SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)]
            x = int(100 * scale)
            column = int(64 * scale)
            for index, text in enumerate(texts):
                slot = state.slot((SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)[index])
                ready = slot.effective_state(state.captured_at, int(self._server_now())) == "ready"
                painter.setPen(QColor("#ffb61f" if ready else "#9fc8ef"))
                painter.drawText(
                    QRect(x + index * column, int(y), column, int(ROW_HEIGHT * scale)),
                    Qt.AlignmentFlag.AlignCenter,
                    text,
                )
            y += ROW_HEIGHT * scale
        if self._edit_mode:
            self._draw_cross_handle(painter)
        painter.end()

    # ---------- 编辑模式拖动 ----------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_mode or event.button() != Qt.MouseButton.LeftButton:
            return
        # 中心十字手柄：自由拖动（x/y 同时跟随）。
        self._drag_axis = None
        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_mode or self._drag_offset is None:
            return
        self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self._drag_offset = None
            self._drag_axis = None
            self.position_changed.emit(self.x(), self.y())


class OverlayController:
    """500ms 跟随游戏窗口；无窗口/最小化时隐藏，不预判独占全屏。"""

    #: 说明文字，不再作为 attach 前的错误判定
    FULLSCREEN_HINT = "若游戏为独占全屏，悬浮窗可能被覆盖，请使用无边框窗口"

    def __init__(
        self,
        overlay: SkillOverlay,
        window_provider: Callable[[], Any],
        screen_provider: Callable[[], tuple[int, int]],
        interval_ms: int = 500,
    ) -> None:
        self.overlay = overlay
        self.window_provider = window_provider
        self.screen_provider = screen_provider
        self._timer = QTimer()
        self._timer.setInterval(max(250, int(interval_ms)))
        self._timer.timeout.connect(self.follow)
        self.enabled = False
        self.attached = False
        self.last_reason = ""
        self.fixed_position: tuple[int, int] | None = None
        self._base_opacity = 0.30
        self.paused = False
        self.pause_reason = ""
        self._pause_depth = 0
        self._last_geometry: tuple[tuple[int, int, int, int], tuple[int, int]] | None = None
        self._last_position: tuple[int, int] | None = None
        self._last_follow_reason = ""
        self._last_log_reason = ""

    def start(self) -> None:
        self.enabled = True
        self.paused = False
        self.pause_reason = ""
        self._pause_depth = 0
        self._timer.start()
        self.follow(force=True)

    def stop(self) -> None:
        self.enabled = False
        self.paused = False
        self._pause_depth = 0
        self._timer.stop()
        if _widget_alive(self.overlay):
            try:
                self.overlay.hide()
            except RuntimeError:
                pass
        self.attached = False

    def pause(self, reason: str = "modal") -> None:
        """模态对话框/抓帧 hide 前暂停 follow 定时器（可嵌套）。"""
        self._pause_depth += 1
        self.paused = True
        self.pause_reason = str(reason)
        self._timer.stop()

    def resume(self, delay_ms: int = 100) -> None:
        """恢复 follow；延迟 100ms 避开 hide/show 重建 HWND 的窗口。"""
        if self._pause_depth > 0:
            self._pause_depth -= 1
        if self._pause_depth > 0:
            return
        if not self.enabled:
            self.paused = False
            self.pause_reason = ""
            return
        self.paused = False
        self.pause_reason = ""

        def _resume_follow() -> None:
            if self.enabled and not self.paused:
                self._timer.start()
                self.follow(force=True)

        if delay_ms > 0:
            QTimer.singleShot(int(delay_ms), _resume_follow)
        else:
            _resume_follow()

    def set_opacity(self, opacity: float) -> None:
        self._base_opacity = float(opacity)
        self.overlay._base_opacity = self._base_opacity
        if not self.overlay.edit_mode:
            self.overlay.set_opacity(self._base_opacity)

    def reset_position(self) -> None:
        self.follow(force=True)

    def follow(self, force: bool = False) -> None:
        if not self.enabled or self.paused:
            return
        if not _widget_alive(self.overlay):
            self._timer.stop()
            return
        # 防御：模态对话框（设置/标定/弹窗）期间不碰原生窗口
        if QApplication.activeModalWidget() is not None:
            self.last_reason = "模态对话框打开，悬浮窗跟随暂停"
            if _widget_alive(self.overlay):
                self.overlay.set_status(self.last_reason)
            return
        window = self.window_provider()
        if window is None:
            self.attached = False
            self._reason("等待游戏窗口")
            return
        if getattr(window, "is_minimized", False):
            self.attached = False
            self._reason("游戏窗口已最小化，悬浮窗已隐藏")
            return
        rect = tuple(int(value) for value in window.client_rect)
        target = (rect[0] + rect[2] - self.overlay.width() - 20,
                  rect[1] + rect[3] - self.overlay.height() - 170)
        if self.fixed_position is not None:
            target = (int(self.fixed_position[0]), int(self.fixed_position[1]))
        target = (max(rect[0], target[0]), max(rect[1], target[1]))
        geometry_changed = self._last_geometry != (rect, (self.overlay.width(), self.overlay.height()))
        position_changed = self._last_position != target
        if position_changed:
            self.overlay.move(*target)
            self._last_position = target
        if not self.overlay.isVisible():
            self.overlay.show()
        self.overlay.set_status("")
        if not self.overlay.edit_mode and (force or not self.attached or geometry_changed):
            if not self.attached:
                set_current_step("overlay_attach")
            if _widget_alive(self.overlay):
                _apply_win32_topmost(self.overlay)
                self.overlay.raise_()
            self._last_geometry = (rect, (self.overlay.width(), self.overlay.height()))
            if not self.attached:
                set_current_step("running")
        self.attached = True
        self.last_reason = "已附加"
        if self._last_log_reason != self.last_reason:
            logger.debug("overlay_attach 状态：%s", self.last_reason)
            self._last_log_reason = self.last_reason

    def _reason(self, text: str) -> None:
        self.last_reason = text
        if self._last_log_reason != text:
            logger.debug("overlay_attach 状态：%s", text)
            self._last_log_reason = text
        if not _widget_alive(self.overlay):
            return
        if text:
            self.overlay.set_status(text)
        if _widget_visible(self.overlay):
            self.overlay.hide()
