"""与 QML ToggleSwitch 同视觉的 Widgets 开关（QPropertyAnimation 150ms）。"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class AnimatedSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None, checked: bool = False) -> None:
        super().__init__(parent)
        self._checked = bool(checked)
        self._knob = 1.0 if checked else 0.0
        self._hover = False
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def isChecked(self) -> bool:  # noqa: N802
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True) -> None:  # noqa: N802
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._knob)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
        else:
            self._knob = 1.0 if checked else 0.0
            self.update()

    def _get_knob(self) -> float:
        return self._knob

    def _set_knob(self, value: float) -> None:
        self._knob = float(value)
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def toggle(self) -> None:
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.toggle()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(1.0 if self.isEnabled() else 0.4)

        if self._checked:
            track = QColor("#ffb91f" if self._hover else "#f5a800")
            knob = QColor("#10131a")
            border = QColor(0, 0, 0, 90)
        else:
            track = QColor("#2c3d57" if self._hover else "#26344d")
            knob = QColor("#8b98ab")
            border = QColor(255, 255, 255, 90)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)

        x = 3.0 + 18.0 * max(0.0, min(1.0, self._knob))
        painter.setBrush(knob)
        painter.setPen(QPen(border, 1))
        painter.drawEllipse(QRectF(x, 3, 16, 16))
        painter.end()
