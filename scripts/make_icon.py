"""生成多尺寸应用图标 assets/app.ico（地图缩略 + 橙色画板笔触）。"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "assets" / "canvas_map.png"
OUT_PATH = ROOT / "assets" / "app.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_icon(size: int, source: QImage) -> bytes:
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#10151c"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    if not source.isNull():
        scaled = source.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - size) // 2)
        y = max(0, (scaled.height() - size) // 2)
        painter.drawImage(0, 0, scaled.copy(x, y, size, size))
        painter.fillRect(QRectF(0, 0, size, size), QColor(8, 14, 22, 90))

    # 画板笔触风格：橙色折线 + 半透明高光
    path = QPainterPath()
    path.moveTo(QPointF(size * 0.18, size * 0.70))
    path.cubicTo(
        QPointF(size * 0.34, size * 0.36),
        QPointF(size * 0.54, size * 0.78),
        QPointF(size * 0.82, size * 0.28),
    )
    painter.setPen(
        QPen(
            QColor("#ffb61f"),
            max(2.0, size * 0.085),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )
    painter.drawPath(path)
    painter.setPen(
        QPen(
            QColor(255, 255, 255, 90),
            max(1.0, size * 0.025),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    painter.drawPath(path)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    canvas.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(entries: list[tuple[int, bytes]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = bytearray()
    payload = bytearray()
    for size, png in entries:
        dimension = 0 if size >= 256 else size
        directory += struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(png),
            offset,
        )
        payload += png
        offset += len(png)
    path.write_bytes(header + bytes(directory) + bytes(payload))


def main() -> int:
    source = QImage(str(MAP_PATH)) if MAP_PATH.is_file() else QImage()
    entries = [(size, render_icon(size, source)) for size in SIZES]
    write_ico(entries, OUT_PATH)
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes, {len(SIZES)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
