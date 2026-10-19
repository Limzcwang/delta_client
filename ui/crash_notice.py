"""启动时上次异常退出提示（单次、可打开日志目录）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget


def show_previous_crash_notice(parent: QWidget | None, info: dict[str, Any], log_path: str | Path) -> bool:
    """返回是否打开了日志目录；不重复弹窗。"""
    step = str(info.get("step") or "未知")
    when = str(info.get("time") or "-")
    path = Path(log_path)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Delta Client")
    box.setText("上次异常退出")
    box.setInformativeText(
        f"最后操作：{step}\n时间：{when}\n日志：{path}\n\n可将该日志提供给开发者排查。"
    )
    open_button = box.addButton("打开日志目录", QMessageBox.ButtonRole.ActionRole)
    box.addButton("关闭", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is open_button:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        return True
    return False
