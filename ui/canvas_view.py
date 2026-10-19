"""共享画板控件（D）：1920×1080 逻辑画布、归一化坐标、画笔/橡皮/清空/撤销重做。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.canvas import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    DEFAULT_COLOR,
    DEFAULT_WIDTH,
    CanvasDocument,
)

CANVAS_BG = QColor("#f7f8fa")
CANVAS_BORDER = QColor("#364252")


class CanvasSurface(QWidget):
    """可绘制表面：把鼠标坐标换算为 0–1 归一化坐标，渲染笔画。"""

    stroke_finished = Signal(list)  # list[dict]：已按 512 点分段后的 op

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.document = CanvasDocument()
        self.tool = "pen"
        self.color = DEFAULT_COLOR
        self.stroke_width = DEFAULT_WIDTH
        self._drawing = False
        self._points: list[QPointF] = []
        self.setMinimumSize(280, 220)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ---------- 坐标换算 ----------
    def canvas_rect(self) -> QRectF:
        """在控件中心按 16:9 等比缩放画布区域。"""
        width = float(self.width())
        height = float(self.height())
        target_ratio = CANVAS_WIDTH / CANVAS_HEIGHT
        if width / height > target_ratio:
            draw_height = height
            draw_width = height * target_ratio
        else:
            draw_width = width
            draw_height = width / target_ratio
        left = (width - draw_width) / 2.0
        top = (height - draw_height) / 2.0
        return QRectF(left, top, draw_width, draw_height)

    def _to_normalized(self, position: QPointF) -> tuple[float, float] | None:
        rect = self.canvas_rect()
        if not rect.contains(position):
            return None
        x = (position.x() - rect.left()) / rect.width()
        y = (position.y() - rect.top()) / rect.height()
        return (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0))

    def _to_widget(self, rect: QRectF, x: float, y: float) -> QPointF:
        return QPointF(rect.left() + x * rect.width(), rect.top() + y * rect.height())

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
        if point is None:
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
        # 过滤过密采样点，减少 op 大小
        if abs(last.x() - point[0]) * CANVAS_WIDTH < 1.0 and abs(last.y() - point[1]) * CANVAS_HEIGHT < 1.0:
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
    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#151a21"))

        rect = self.canvas_rect()
        painter.fillRect(rect, CANVAS_BG)
        painter.setPen(QPen(CANVAS_BORDER, 1))
        painter.drawRect(rect)

        scale = rect.width() / CANVAS_WIDTH
        for op in self.document.ops:
            if op.get("kind") != "stroke":
                continue
            points = op.get("points") or []
            if not points:
                continue
            color = QColor(op.get("tool") == "eraser" and CANVAS_BG.name() or op.get("color", DEFAULT_COLOR))
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

        # 正在绘制的临时笔画
        if self._drawing and self._points:
            pen = QPen(
                QColor(CANVAS_BG.name() if self.tool == "eraser" else self.color),
                max(1.0, float(self.stroke_width) * scale),
            )
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawPolyline(
                [self._to_widget(rect, p.x(), p.y()) for p in self._points]
            )

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


class CanvasView(QWidget):
    """画板面板：工具栏 + 绘制表面。"""

    stroke_finished = Signal(list)
    clear_requested = Signal()

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

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.pen_button = QPushButton("画笔")
        self.pen_button.setCheckable(True)
        self.pen_button.setChecked(True)
        self.eraser_button = QPushButton("橡皮")
        self.eraser_button.setCheckable(True)
        self.color_button = QPushButton("颜色")
        self.color_button.setStyleSheet(
            f"QPushButton {{ border: 2px solid {DEFAULT_COLOR}; }}"
        )
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 32)
        self.width_spin.setValue(DEFAULT_WIDTH)
        self.width_spin.setPrefix("粗细 ")
        self.undo_button = QPushButton("撤销")
        self.redo_button = QPushButton("重做")
        self.clear_button = QPushButton("清空")
        self.clear_button.setObjectName("Danger")

        toolbar.addWidget(self.pen_button)
        toolbar.addWidget(self.eraser_button)
        toolbar.addWidget(self.color_button)
        toolbar.addWidget(self.width_spin)
        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        toolbar.addWidget(self.clear_button)
        layout.addLayout(toolbar)

        self.surface = CanvasSurface()
        layout.addWidget(self.surface, stretch=1)

        hint = QLabel("逻辑画布 1920×1080 · 协议坐标 0–1 · 撤销/重做仅本地 · 离开房间时自动保存快照")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.pen_button.clicked.connect(lambda: self._select_tool("pen"))
        self.eraser_button.clicked.connect(lambda: self._select_tool("eraser"))
        self.color_button.clicked.connect(self._pick_color)
        self.width_spin.valueChanged.connect(self.surface.set_width)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.clear_button.clicked.connect(self._clear)

    # ---------- 工具栏 ----------
    def _select_tool(self, tool: str) -> None:
        self.surface.set_tool(tool)
        self.pen_button.setChecked(tool == "pen")
        self.eraser_button.setChecked(tool == "eraser")

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.surface.color), self, "选择画笔颜色")
        if color.isValid():
            self.surface.set_color(color.name().upper())
            self.color_button.setStyleSheet(
                f"QPushButton {{ border: 2px solid {color.name().upper()}; }}"
            )

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
