"""E3b：手动选择游戏窗口（标题/PID/尺寸/exe）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout


class WindowPickerDialog(QDialog):
    def __init__(self, candidates, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择游戏窗口")
        self.resize(720, 460)
        self._candidates = list(candidates)
        self._selected = None
        layout = QVBoxLayout(self)
        hint = QLabel("选择游戏窗口后，客户端会优先按该窗口的标题/进程名抓帧（仅窗口模式）。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.list_widget = QListWidget()
        for candidate in self._candidates:
            text = (
                f"PID {candidate.pid} · {candidate.title or '(无标题)'} · "
                f"{candidate.client_width}×{candidate.client_height} · "
                f"{candidate.process_label}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.accept())
        layout.addWidget(self.list_widget, stretch=1)
        if not self._candidates:
            hint.setText("当前没有可见的候选窗口。请先启动游戏，并确认不是最小化。")
        self.refresh_button = QPushButton("刷新列表")
        self.cancel_button = QPushButton("取消")
        self.ok_button = QPushButton("使用此窗口")
        self.ok_button.setObjectName("Primary")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        if self._candidates:
            self.list_widget.setCurrentRow(0)
        row = QVBoxLayout()
        row.addWidget(self.ok_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def _on_row_changed(self, row: int) -> None:
        self._selected = self._candidates[row] if 0 <= row < len(self._candidates) else None

    def selected_candidate(self):
        return self._selected
