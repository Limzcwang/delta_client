"""画板工具栏矢量图标（QPainter 绘制，不依赖外部图标库/emoji）。"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_SIZE = 48


def _new_painter() -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pixmap, painter


def _pen(color: str, width: float = 2.4) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def make_tool_icon(kind: str, color: str = "#e6edf5", width: int = 4) -> QIcon:
    """生成 48×48 矢量图标：pen/eraser/palette/width/undo/redo/trash。"""
    pixmap, painter = _new_painter()
    try:
        painter.setPen(_pen(color))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if kind == "pen":
            nib = QPainterPath()
            nib.moveTo(15, 34)
            nib.lineTo(31, 10)
            nib.lineTo(38, 16)
            nib.lineTo(21, 39)
            nib.lineTo(13, 40)
            nib.closeSubpath()
            painter.drawPath(nib)
            painter.drawLine(QPointF(16, 32), QPointF(24, 38))
        elif kind == "eraser":
            body = QPainterPath()
            body.moveTo(12, 31)
            body.lineTo(27, 12)
            body.lineTo(39, 21)
            body.lineTo(24, 40)
            body.lineTo(13, 40)
            body.closeSubpath()
            painter.drawPath(body)
            painter.drawLine(QPointF(21, 19), QPointF(33, 28))
        elif kind == "palette":
            painter.drawEllipse(QRectF(9, 9, 30, 30))
            dot_colors = (color, "#ffb61f", "#ff6b6b", "#6fdc8c")
            for index, dot in enumerate(dot_colors):
                painter.setBrush(QColor(dot))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QRectF(14 + index * 5.5, 14 + (index % 2) * 5, 5, 5))
        elif kind == "width":
            widths = (2.0, 4.0, 7.0)
            for index, line_width in enumerate(widths):
                painter.setPen(_pen(color, line_width))
                painter.drawLine(
                    QPointF(12, 16 + index * 8), QPointF(36, 16 + index * 8)
                )
        elif kind in ("undo", "redo"):
            rect = QRectF(12, 14, 26, 22)
            if kind == "undo":
                painter.drawArc(rect, 30 * 16, 150 * 16)
                arrow = QPainterPath()
                arrow.moveTo(14, 17)
                arrow.lineTo(24, 15)
                arrow.lineTo(19, 27)
                arrow.closeSubpath()
            else:
                painter.drawArc(rect, 0 * 16, 150 * 16)
                arrow = QPainterPath()
                arrow.moveTo(36, 17)
                arrow.lineTo(26, 15)
                arrow.lineTo(31, 27)
                arrow.closeSubpath()
            painter.setBrush(QColor(color))
            painter.drawPath(arrow)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        elif kind == "trash":
            painter.drawLine(QPointF(14, 16), QPointF(36, 16))
            painter.drawLine(QPointF(20, 12), QPointF(30, 12))
            painter.drawRoundedRect(QRectF(16, 16, 18, 22), 3, 3)
            painter.drawLine(QPointF(23, 22), QPointF(23, 33))
            painter.drawLine(QPointF(29, 22), QPointF(29, 33))
        else:
            painter.drawEllipse(QRectF(15, 15, 18, 18))
    finally:
        painter.end()
    return QIcon(pixmap)
