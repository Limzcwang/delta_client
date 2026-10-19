"""E3b1：HUD 标定对话框（实时帧框选技能栏，自动等分 3 槽，导入/导出 JSON）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.hud_profile import HudProfile, Roi


def qimage_from_frame(frame: Any) -> QImage:
    """numpy BGR/BGRA 或 QImage -> QImage（深拷贝，帧可释放）。"""
    if isinstance(frame, QImage):
        return frame.copy()
    try:
        import numpy as np  # type: ignore[import-not-found]

        array = np.asarray(frame)
        if array.ndim == 2:
            return QImage(
                array.data, array.shape[1], array.shape[0], int(array.strides[0]), QImage.Format.Format_Grayscale8
            ).copy()
        if array.ndim == 3 and array.shape[2] >= 3:
            return QImage(
                array.data,
                array.shape[1],
                array.shape[0],
                int(array.strides[0]),
                QImage.Format.Format_BGR888,
            ).copy()
    except Exception:  # noqa: BLE001
        pass
    return QImage()


class PreviewWidget(QWidget):
    """显示一帧并允许拖拽框选技能栏；叠加 3 槽等分预览。"""

    selection_changed = Signal(object)  # Roi

    def __init__(self, image: QImage, profile: HudProfile, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image = image
        self.profile = profile
        self._pixmap = QPixmap.fromImage(image)
        self._selection = profile.skill_bar
        self._drag_start: QPoint | None = None
        self._drag_current: QPoint | None = None
        self.setMinimumSize(640, 400)
        self.setMouseTracking(True)

    def image_rect(self) -> QRect:
        if self._pixmap.isNull():
            return QRect()
        scaled = self._pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        return QRect(x, y, scaled.width(), scaled.height())

    def widget_to_image(self, point: QPoint) -> QPoint:
        rect = self.image_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return QPoint(0, 0)
        x = int((point.x() - rect.x()) * self.image.width() / rect.width())
        y = int((point.y() - rect.y()) * self.image.height() / rect.height())
        return QPoint(
            max(0, min(x, self.image.width() - 1)),
            max(0, min(y, self.image.height() - 1)),
        )

    def image_to_widget_rect(self, roi: Roi) -> QRect:
        rect = self.image_rect()
        if rect.width() <= 0 or self.image.width() <= 0:
            return QRect()
        sx = rect.width() / self.image.width()
        sy = rect.height() / self.image.height()
        return QRect(
            rect.x() + int(roi.x * sx),
            rect.y() + int(roi.y * sy),
            max(1, int(roi.width * sx)),
            max(1, int(roi.height * sy)),
        )

    def set_selection(self, roi: Roi) -> None:
        self._selection = roi
        self.profile.skill_bar = roi
        self.profile.slots = None
        self.selection_changed.emit(roi)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#10151c"))
        if not self._pixmap.isNull():
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(self.image_rect(), self._pixmap)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bar_rect = self.image_to_widget_rect(self.profile.skill_bar)
        painter.setPen(QPen(QColor("#ffb61f"), 2))
        painter.setBrush(QColor(255, 182, 31, 35))
        painter.drawRect(bar_rect)

        for index, roi in enumerate(self.profile.slot_rois()):
            slot_rect = self.image_to_widget_rect(roi)
            painter.setPen(QPen(QColor("#5fb7ff"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(slot_rect)
            painter.setPen(QPen(QColor("#e6edf5")))
            painter.drawText(slot_rect.adjusted(4, 2, 0, 0), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, str(index))

        if self._drag_start is not None and self._drag_current is not None:
            drag = QRect(self._drag_start, self._drag_current).normalized()
            painter.setPen(QPen(QColor("#8be3a8"), 2))
            painter.setBrush(QColor(139, 227, 168, 30))
            painter.drawRect(drag)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._drag_current = self._drag_start
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_start is not None:
            self._drag_current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or self._drag_start is None:
            return
        self._drag_current = event.position().toPoint()
        first = self.widget_to_image(self._drag_start)
        second = self.widget_to_image(self._drag_current)
        self._drag_start = None
        self._drag_current = None
        roi = Roi.from_quad((first.x(), first.y()), (second.x(), second.y()))
        if roi.width < 8 or roi.height < 8:
            self.update()
            return
        self.set_selection(roi)


class HudCalibrationDialog(QDialog):
    """技能栏整体框选 -> 自动等分 3 槽；可保存/导入/导出 profile。"""

    def __init__(
        self,
        frame: Any,
        profile: HudProfile | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("HUD 标定")
        self.resize(960, 660)
        self.profile = profile or HudProfile()
        image = qimage_from_frame(frame)
        if image.isNull() and isinstance(frame, (str, Path)):
            image = QImage(str(frame))
        self._build(image)

    def _build(self, image: QImage) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        title = QLabel("在截图上框选「技能栏整体」，自动等分为 3 槽（大招/技能/投掷物）")
        title.setWordWrap(True)
        root.addWidget(title)

        self.preview = PreviewWidget(image, self.profile)
        self.preview.selection_changed.connect(self._on_selection)
        root.addWidget(self.preview, stretch=1)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        root.addWidget(self.info_label)
        self._update_info()

        row = QHBoxLayout()
        self.save_button = QPushButton("使用此标定")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.accept)
        self.export_button = QPushButton("导出 JSON")
        self.export_button.clicked.connect(self._export)
        self.import_button = QPushButton("导入 JSON")
        self.import_button.clicked.connect(self._import)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(self.import_button)
        row.addWidget(self.export_button)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(self.save_button)
        root.addLayout(row)

    def _on_selection(self, roi: Roi) -> None:
        self.profile.skill_bar = roi
        self.profile.slots = None
        self._update_info()

    def _update_info(self) -> None:
        slots = self.profile.slot_rois()
        self.info_label.setText(
            f"技能栏：({self.profile.skill_bar.x},{self.profile.skill_bar.y}) "
            f"{self.profile.skill_bar.width}×{self.profile.skill_bar.height}；"
            + " / ".join(f"{index}:{roi.width}×{roi.height}" for index, roi in enumerate(slots))
        )

    def set_selection(self, roi: Roi) -> None:
        self.preview.set_selection(roi)
        self._update_info()

    def result_profile(self) -> HudProfile:
        self.profile.slots = None
        return self.profile

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出标定", "hud_profile.json", "JSON (*.json)")
        if not path:
            return
        try:
            self.profile.save(path)
            self.info_label.setText(f"已导出：{path}")
        except OSError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入标定", "", "JSON (*.json)")
        if not path:
            return
        loaded = HudProfile.load(path)
        self.profile = loaded
        self.preview.profile = loaded
        self.preview.set_selection(loaded.skill_bar)
        self._update_info()
