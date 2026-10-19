"""E2 技能 CD 面板：队友技能状态、倒计时、就绪高亮与模拟共享开关。"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.skills import (
    SLOT_ABILITY,
    SLOT_LABELS,
    SLOT_THROWABLE,
    SLOT_ULTIMATE,
    SKILL_READY,
    SKILL_UNKNOWN,
    SkillSlot,
    SkillState,
    format_countdown,
    format_percent,
)

_SLOT_ORDER = (SLOT_ULTIMATE, SLOT_ABILITY, SLOT_THROWABLE)
_COLORS = {
    SKILL_READY: "#ffb61f",
    "charging": "#5fb7ff",
    SKILL_UNKNOWN: "#71808f",
}


class SkillSlotWidget(QWidget):
    """单个技能槽：大招环形百分比；技能/投掷物充能 + CD 倒计时。"""

    def __init__(self, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.slot = SkillSlot(kind=kind)
        self.captured_at = 0
        self.server_now = 0
        self.pulse = False
        self.setMinimumSize(82, 92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(SLOT_LABELS.get(kind, kind))

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 覆盖
        return QSize(96, 96)

    def set_data(self, slot: SkillSlot, captured_at: int, server_now: int, pulse: bool = False) -> None:
        self.slot = slot
        self.captured_at = int(captured_at)
        self.server_now = int(server_now)
        self.pulse = bool(pulse)
        state = self.effective_state()
        self.setProperty("skillState", state)
        self.setToolTip(f"{SLOT_LABELS.get(self.kind, self.kind)}：{self.text_lines()[1]}")
        self.update()

    def effective_state(self) -> str:
        return self.slot.effective_state(self.captured_at, self.server_now)

    def remaining_now(self) -> int:
        return self.slot.remaining_now(self.captured_at, self.server_now)

    def text_lines(self) -> tuple[str, str, str]:
        state = self.effective_state()
        title = SLOT_LABELS.get(self.kind, self.kind)
        if state == SKILL_UNKNOWN:
            return title, "?", "未共享"
        if self.kind == SLOT_ULTIMATE:
            main = format_percent(self.slot.percent)
        else:
            if self.slot.max_charges:
                main = f"{self.slot.charges}/{self.slot.max_charges}"
            elif state == SKILL_READY:
                main = "就绪"
            else:
                main = "—"
        if state == SKILL_READY:
            return title, main, "就绪"
        return title, main, format_countdown(self.remaining_now())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        state = self.effective_state()
        color = QColor(_COLORS.get(state, _COLORS[SKILL_UNKNOWN]))
        painter.setBrush(QColor("#1a222c"))
        border = QPen(color, 2)
        if state == SKILL_READY and self.pulse:
            border.setColor(QColor("#ffe08a"))
            border.setWidth(3)
        painter.setPen(border)
        painter.drawRoundedRect(rect, 8, 8)

        title, main, sub = self.text_lines()
        painter.setPen(QPen(QColor("#8b98a8")))
        title_font = QFont(self.font())
        title_font.setPointSize(8)
        painter.setFont(title_font)
        painter.drawText(QRectF(0, 5, self.width(), 16), Qt.AlignmentFlag.AlignHCenter, title)

        painter.setPen(QPen(color))
        main_font = QFont(self.font())
        main_font.setPointSize(14 if self.kind != SLOT_ULTIMATE else 15)
        main_font.setBold(True)
        painter.setFont(main_font)
        if self.kind == SLOT_ULTIMATE and state != SKILL_UNKNOWN:
            ring_rect = QRectF(self.width() / 2 - 24, 23, 48, 48)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#2b3440"), 5))
            painter.drawEllipse(ring_rect)
            painter.setPen(QPen(color, 5))
            painter.drawArc(ring_rect, 90 * 16, -int(3.6 * self.slot.percent * 16))
            painter.setPen(QPen(color))
            painter.drawText(
                QRectF(0, 32, self.width(), 30),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                main,
            )
        else:
            painter.drawText(
                QRectF(0, 30, self.width(), 32),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                main,
            )

        painter.setPen(QPen(color if state == SKILL_READY else QColor("#8b98a8")))
        sub_font = QFont(self.font())
        sub_font.setPointSize(9)
        painter.setFont(sub_font)
        painter.drawText(
            QRectF(0, 66, self.width(), 18),
            Qt.AlignmentFlag.AlignHCenter,
            sub,
        )
        painter.end()


class SkillRow(QFrame):
    """一条队友技能行：头像首字母 + 昵称/干员名 + 3 个固定槽位。"""

    def __init__(self, state: SkillState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.user_id = state.user_id
        self.state = state
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.avatar = QLabel(state.avatar_letter)
        self.avatar.setObjectName("SkillAvatar")
        self.avatar.setFixedSize(30, 30)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.avatar)
        names = QVBoxLayout()
        names.setSpacing(1)
        self.name_label = QLabel(state.display_name)
        self.name_label.setObjectName("SkillName")
        self.operator_label = QLabel(state.operator or "干员未共享")
        self.operator_label.setObjectName("Hint")
        names.addWidget(self.name_label)
        names.addWidget(self.operator_label)
        header.addLayout(names, stretch=1)
        self.status_label = QLabel()
        self.status_label.setObjectName("Hint")
        header.addWidget(self.status_label)
        root.addLayout(header)

        slots = QHBoxLayout()
        slots.setSpacing(6)
        self.slot_widgets: dict[str, SkillSlotWidget] = {}
        for kind in _SLOT_ORDER:
            widget = SkillSlotWidget(kind)
            self.slot_widgets[kind] = widget
            slots.addWidget(widget, stretch=1)
        root.addLayout(slots)
        self.update_state(state, int(time.time() * 1000), pulse=False)

    def update_state(self, state: SkillState, server_now: int, pulse: bool = False) -> None:
        self.state = state
        if state.display_name != self.name_label.text():
            self.name_label.setText(state.display_name)
            self.avatar.setText(state.avatar_letter)
        self.operator_label.setText(state.operator or "干员未共享")
        unshared = state.is_unshared(server_now)
        self.status_label.setText("未共享" if unshared else "已共享")
        self.status_label.setStyleSheet("color: #ffd071;" if unshared else "color: #6fdc8c;")
        for kind, widget in self.slot_widgets.items():
            widget.set_data(state.slot(kind), state.captured_at, server_now, pulse=pulse)


class SkillPanel(QWidget):
    """房间内技能标签页：每行一个队友，倒计时每秒刷新。"""

    sharing_toggled = Signal(bool)
    simulate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._states: dict[str, SkillState] = {}
        self._rows: dict[str, SkillRow] = {}
        self._clock_offset_ms = 0
        self._pulse = False
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("技能共享（E2）")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.share_check = QCheckBox("共享我的技能")
        self.share_check.setChecked(False)
        self.share_check.toggled.connect(self._on_share_toggled)
        header.addWidget(self.share_check)
        self.simulate_button = QPushButton("模拟我的技能")
        self.simulate_button.setObjectName("Link")
        self.simulate_button.clicked.connect(self.simulate_requested.emit)
        header.addWidget(self.simulate_button)
        root.addLayout(header)

        hint = QLabel("默认关闭；开启后 2 次/秒限频上报 · 左大招 / 中技能 / 右投掷物 · 30 分钟未更新=未共享")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(6)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        root.addWidget(self.scroll, stretch=1)

        self.empty_label = QLabel("还没有队友共享技能")
        self.empty_label.setObjectName("Hint")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty_label)
        self._sync_empty()

    # ---------- 数据 ----------
    @property
    def sharing_enabled(self) -> bool:
        return self.share_check.isChecked()

    def set_sharing(self, enabled: bool) -> None:
        self.share_check.blockSignals(True)
        self.share_check.setChecked(bool(enabled))
        self.share_check.blockSignals(False)

    def set_clock_offset(self, offset_ms: int) -> None:
        self._clock_offset_ms = int(offset_ms)
        self._tick()

    def server_now_ms(self) -> int:
        return int(time.time() * 1000) + self._clock_offset_ms

    def states(self) -> list[SkillState]:
        return list(self._states.values())

    def set_states(self, states: list[SkillState]) -> None:
        for row in list(self._rows.values()):
            row.deleteLater()
            row.setParent(None)
        self._rows.clear()
        self._states.clear()
        for state in states:
            if state.user_id:
                self._states[state.user_id] = state
        for state in self._states.values():
            self._add_row(state)
        self._sync_empty()

    def upsert(self, state: SkillState) -> None:
        if not state.user_id:
            return
        existed = state.user_id in self._rows
        self._states[state.user_id] = state
        if existed:
            self._rows[state.user_id].update_state(state, self.server_now_ms(), self._pulse)
        else:
            self._add_row(state)
        self._sync_empty()

    def remove(self, user_id: str) -> None:
        state = self._states.pop(str(user_id), None)
        row = self._rows.pop(str(user_id), None)
        if row is not None:
            self.list_layout.removeWidget(row)
            row.deleteLater()
        if state is not None:
            self._sync_empty()

    def clear(self) -> None:
        self.set_states([])

    def _add_row(self, state: SkillState) -> None:
        row = SkillRow(state, self.list_widget)
        self._rows[state.user_id] = row
        self.list_layout.insertWidget(self.list_layout.count() - 1, row)

    def _sync_empty(self) -> None:
        has_rows = bool(self._rows)
        self.scroll.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)

    # ---------- 刷新 ----------
    def _tick(self) -> None:
        self._pulse = not self._pulse
        server_now = self.server_now_ms()
        for row in self._rows.values():
            row.update_state(row.state, server_now, self._pulse)

    def _on_share_toggled(self, enabled: bool) -> None:
        self.sharing_toggled.emit(bool(enabled))
