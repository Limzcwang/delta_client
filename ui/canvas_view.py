"""共享画板控件（D/H4）：底图 letterbox、图片区域归一化、透明笔画层、图标工具栏。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.canvas import (
    DEFAULT_COLOR,
    DEFAULT_WIDTH,
    CanvasDocument,
)
from core.canvas_geometry import (
    AspectSize,
    canvas_to_normalized,
    fit_aspect_size,
    normalized_to_canvas,
)
from ui.canvas_icons import make_tool_icon

#: 内置底图尺寸兜底（assets/canvas_map.png 实际 1105×1260）
MAP_WIDTH = 1105
MAP_HEIGHT = 1260
CANVAS_BG = QColor("#10151c")
_MAP_RELATIVE = Path("assets") / "canvas_map.png"


def map_asset_path() -> Path:
    """底图路径：环境变量优先；PyInstaller 下取 _MEIPASS/assets。"""
    import os

    override = str(os.environ.get("DELTA_CANVAS_MAP", "") or "").strip()
    if override:
        return Path(override).expanduser()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / _MAP_RELATIVE


class CanvasSurface(QWidget):
    """底图 + 透明笔画层：坐标以图片显示区域为 0–1 基准。"""

    stroke_finished = Signal(list)  # list[dict]：已按 512 点分段后的 op

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = CanvasDocument()
        self.tool = "pen"
        self.color = DEFAULT_COLOR
        self.stroke_width = DEFAULT_WIDTH
        self._drawing = False
        self._points: list[QPointF] = []
        self.map_pixmap = self._load_map()
        if self.map_pixmap is not None and not self.map_pixmap.isNull():
            self.map_size = (self.map_pixmap.width(), self.map_pixmap.height())
        else:
            self.map_size = (MAP_WIDTH, MAP_HEIGHT)
        self.setMinimumSize(280, 220)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    @staticmethod
    def _load_map():
        from PySide6.QtGui import QPixmap

        path = map_asset_path()
        pixmap = QPixmap(str(path))
        return pixmap if not pixmap.isNull() else QPixmap()

    # ---------- 坐标换算 ----------
    def canvas_rect(self) -> QRectF:
        """画布控件内部就是底图，无 letterbox/裁切；整块控件即图片区域。"""
        return QRectF(0.0, 0.0, float(self.width()), float(self.height()))

    def _to_normalized(self, position: QPointF) -> tuple[float, float] | None:
        return canvas_to_normalized(position.x(), position.y(), self.width(), self.height())

    def _to_widget(self, rect: QRectF, x: float, y: float) -> QPointF:
        px, py = normalized_to_canvas(x, y, rect.width(), rect.height())
        return QPointF(px, py)

    # ---------- 交互 ----------
    def set_tool(self, tool: str) -> None:
        self.tool = "eraser" if tool == "eraser" else "pen"

    def set_color(self, color: str) -> None:
        self.color = color

    def set_width(self, width: int) -> None:
        self.stroke_width = max(1, min(32, int(width)))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt 覆盖
        if event.button() != Qt.MouseButton.LeftButton:
            return
        point = self._to_normalized(event.position())
        if point is None:  # 指针不在图片显示区域（cover 下通常整个视口都可画）
            return
        self._drawing = True
        self._points = [QPointF(point[0], point[1])]
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing:
            return
        point = self._to_normalized(event.position())
        if point is None:
            return
        last = self._points[-1]
        # 过滤过密采样点：按画布宽度换算 1px
        if (
            abs(last.x() - point[0]) * self.width() < 1.0
            and abs(last.y() - point[1]) * self.height() < 1.0
        ):
            return
        self._points.append(QPointF(point[0], point[1]))
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing:
            return
        self._drawing = False
        points = self._points
        self._points = []
        if not points:
            self.update()
            return
        normalized = [(p.x(), p.y()) for p in points]
        ops = self.document.add_stroke(normalized, self.color, self.stroke_width, self.tool)
        self.update()
        if ops:
            self.stroke_finished.emit(ops)

    # ---------- 渲染 ----------
    def _paint_layer(self, layer: QImage, rect: QRectF) -> None:
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(rect)
        scale = rect.width() / max(1, self.map_size[0])
        for op in self.document.ops:
            self._paint_stroke(painter, rect, op, scale)
        if self._drawing and self._points:
            self._paint_stroke(
                painter,
                rect,
                {
                    "tool": self.tool,
                    "color": self.color,
                    "width": self.stroke_width,
                    "points": [{"x": p.x(), "y": p.y()} for p in self._points],
                },
                scale,
            )
        painter.end()

    def _paint_stroke(self, painter: QPainter, rect: QRectF, op, scale: float) -> None:
        if op.get("kind") not in (None, "stroke"):
            return
        points = op.get("points") or []
        if not points:
            return
        eraser = op.get("tool") == "eraser"
        # 关键：底图存在时橡皮不再涂背景色，而是在透明层上 Clear
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Clear
            if eraser
            else QPainter.CompositionMode.CompositionMode_SourceOver
        )
        color = QColor(0, 0, 0, 0) if eraser else QColor(op.get("color", DEFAULT_COLOR))
        width = max(1.0, float(op.get("width", DEFAULT_WIDTH)) * scale)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        path = [self._to_widget(rect, float(p["x"]), float(p["y"])) for p in points]
        if len(path) == 1:
            painter.drawPoint(path[0])
        else:
            painter.drawPolyline(path)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), CANVAS_BG)

        rect = self.canvas_rect()
        if not self.map_pixmap.isNull():
            painter.drawPixmap(rect, self.map_pixmap, QRectF(self.map_pixmap.rect()))
        else:
            painter.fillRect(rect, QColor("#f7f8fa"))

        # 笔画画在透明层，橡皮 Clear 该层，最后叠加到底图上
        layer = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
        layer.fill(Qt.GlobalColor.transparent)
        self._paint_layer(layer, rect)
        painter.setClipRect(rect)
        painter.drawImage(0, 0, layer)
        painter.setClipping(False)

    # ---------- 对外操作 ----------
    def draw_stroke(
        self,
        points,
        color: str | None = None,
        width: int | None = None,
        tool: str | None = None,
    ) -> list[dict]:
        """程序化完成一笔（用于演示/冒烟测试），会像鼠标绘制一样发出信号。"""
        ops = self.document.add_stroke(
            points,
            color or self.color,
            self.stroke_width if width is None else width,
            tool or self.tool,
        )
        self.update()
        if ops:
            self.stroke_finished.emit(ops)
        return ops

    def load_snapshot(self, strokes) -> None:
        self.document.apply_snapshot(strokes)
        self.update()

    def apply_remote_op(self, op) -> None:
        self.document.apply_remote_op(op)
        self.update()

    def clear(self) -> None:
        self.document.clear()
        self.update()

    def undo(self) -> None:
        self.document.undo()
        self.update()

    def redo(self) -> None:
        self.document.redo()
        self.update()

    def reset(self) -> None:
        self.document.reset()
        self.update()

    def snapshot_strokes(self) -> list[dict]:
        return self.document.snapshot_strokes()


class CanvasHost(QWidget):
    """宿主：按底图宽高比等比计算画布尺寸，居中放置；剩余区域由普通背景留白。"""

    def __init__(self, surface: CanvasSurface, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.surface = surface
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(surface, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(220)

    def size_for_space(self, width: int, height: int) -> AspectSize:
        return fit_aspect_size(width, height, *self.surface.map_size)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 覆盖
        super().resizeEvent(event)
        target = self.size_for_space(self.width(), self.height())
        self.surface.setFixedSize(max(1, int(target.width)), max(1, int(target.height)))


class CanvasView(QWidget):
    """画板面板：底部图标工具栏 + 带底图的绘制表面。"""

    stroke_finished = Signal(list)
    clear_requested = Signal()

    _WIDTHS = (2, 4, 6, 8, 12)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()
        self.surface.stroke_finished.connect(self.stroke_finished.emit)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("画板协同（D）")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.surface = CanvasSurface()
        self.host = CanvasHost(self.surface)
        layout.addWidget(self.host, stretch=1)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)
        self.pen_button = self._tool_button("pen", "画笔 (P)", "P", checkable=True)
        self.eraser_button = self._tool_button("eraser", "橡皮 (E)", "E", checkable=True)
        self.color_button = self._tool_button("palette", "颜色 (C)", "C")
        self.width_button = self._tool_button("width", f"粗细 (W)：{self.surface.stroke_width}", "W")
        self.undo_button = self._tool_button("undo", "撤销 (Ctrl+Z)", "Ctrl+Z")
        self.redo_button = self._tool_button("redo", "重做 (Ctrl+Shift+Z)", "Ctrl+Shift+Z")
        self.clear_button = self._tool_button("trash", "清空画板 (Ctrl+Delete)", "Ctrl+Delete")
        self.pen_button.setChecked(True)
        self.tool_buttons = [
            self.pen_button,
            self.eraser_button,
            self.color_button,
            self.width_button,
            self.undo_button,
            self.redo_button,
            self.clear_button,
        ]
        for button in self.tool_buttons:
            toolbar.addWidget(button, stretch=1)
        layout.addLayout(toolbar)

        hint = QLabel("画布随底图 1105×1260 等比缩放（外部留白）· 坐标以画布 0–1 · 撤销/重做仅本地")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.pen_button.clicked.connect(lambda: self._select_tool("pen"))
        self.eraser_button.clicked.connect(lambda: self._select_tool("eraser"))
        self.color_button.clicked.connect(self._pick_color)
        self.width_button.clicked.connect(self._cycle_width)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.clear_button.clicked.connect(self._clear)

    def _tool_button(
        self, kind: str, tooltip: str, shortcut: str, *, checkable: bool = False
    ) -> QToolButton:
        button = QToolButton()
        button.setObjectName("CanvasTool")
        button.setToolTip(tooltip)
        button.setIcon(make_tool_icon(kind))
        button.setIconSize(QSize(26, 26))
        button.setFixedHeight(44)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setCheckable(checkable)
        if checkable:
            button.setAutoExclusive(False)
        button.setShortcut(QKeySequence(shortcut))
        return button

    # ---------- 工具栏 ----------
    def _select_tool(self, tool: str) -> None:
        self.surface.set_tool(tool)
        self.pen_button.setChecked(tool == "pen")
        self.eraser_button.setChecked(tool == "eraser")

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.surface.color), self, "选择画笔颜色")
        if color.isValid():
            self.surface.set_color(color.name().upper())
            self.color_button.setIcon(make_tool_icon("palette", color.name().upper()))

    def _cycle_width(self) -> None:
        widths = list(self._WIDTHS)
        current = self.surface.stroke_width
        index = widths.index(current) if current in widths else -1
        next_width = widths[(index + 1) % len(widths)]
        self.surface.set_width(next_width)
        self.width_button.setIcon(make_tool_icon("width", width=next_width))
        self.width_button.setToolTip(f"粗细 (W)：{next_width}")

    def _undo(self) -> None:
        self.surface.undo()

    def _redo(self) -> None:
        self.surface.redo()

    def _clear(self) -> None:
        if self.surface.document.is_empty:
            return
        self.surface.clear()
        self.clear_requested.emit()

    # ---------- 对外 ----------
    def load_snapshot(self, strokes) -> None:
        self.surface.load_snapshot(strokes)

    def apply_remote_op(self, op) -> None:
        self.surface.apply_remote_op(op)

    def reset(self) -> None:
        self.surface.reset()

    def snapshot_strokes(self) -> list[dict]:
        return self.surface.snapshot_strokes()

    @property
    def is_empty(self) -> bool:
        return self.surface.document.is_empty

    def stroke_count(self) -> int:
        return self.surface.document.count
