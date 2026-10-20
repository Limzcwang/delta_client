"""SwitchRow：左侧标题+说明，右侧 AnimatedSwitch；统一 Widgets 开关行。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.animated_switch import AnimatedSwitch


class SwitchRow(QWidget):
    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        hint: str = "",
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SwitchRow")
        self.setMinimumHeight(38 if not hint else 52)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(12)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SwitchTitle")
        self.title_label.setWordWrap(False)
        text.addWidget(self.title_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("Hint")
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        text.addWidget(self.hint_label)
        root.addLayout(text, stretch=1)
        self.switch = AnimatedSwitch(checked=checked)
        self.switch.toggled.connect(self.toggled.emit)
        root.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.setToolTip(title if not hint else f"{title}\n{hint}")

    def isChecked(self) -> bool:  # noqa: N802
        return self.switch.isChecked()

    def setChecked(self, checked: bool, animate: bool = True) -> None:  # noqa: N802
        checked = bool(checked)
        changed = checked != self.switch.isChecked()
        self.switch.setChecked(checked, animate=animate)
        if changed:
            self.toggled.emit(checked)

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        self.switch.blockSignals(block)
        return super().blockSignals(block)
