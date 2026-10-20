"""E2 技能 CD 面板：队友技能状态、倒计时、就绪高亮与模拟共享开关。"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.operators import Operator, OperatorCatalog
from ui.switch_row import SwitchRow
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
_SLOT_INDEX = {SLOT_ULTIMATE: 0, SLOT_ABILITY: 1, SLOT_THROWABLE: 2}
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
        self.skill_name = ""
        self.cd_known = True
        self.setMinimumSize(82, 104)
        self.setFixedHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(SLOT_LABELS.get(kind, kind))

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt 覆盖
        return QSize(96, 104)

    def name_rect(self) -> QRectF:
        return QRectF(8, 4, max(1, self.width() - 16), 20)

    def middle_rect(self) -> QRectF:
        return QRectF((self.width() - 54) / 2, 28, 54, 54)

    def bottom_rect(self) -> QRectF:
        return QRectF(8, 88, max(1, self.width() - 16), 14)

    def set_data(
        self,
        slot: SkillSlot,
        captured_at: int,
        server_now: int,
        pulse: bool = False,
        *,
        skill_name: str = "",
        cd_known: bool = True,
    ) -> None:
        self.slot = slot
        self.captured_at = int(captured_at)
        self.server_now = int(server_now)
        self.pulse = bool(pulse)
        self.skill_name = str(skill_name or "")
        self.cd_known = bool(cd_known)
        state = self.effective_state()
        self.setProperty("skillState", state)
        title, main, _sub = self.text_lines()
        self.setToolTip(f"{title}：{main}")
        self.update()

    def effective_state(self) -> str:
        return self.slot.effective_state(self.captured_at, self.server_now)

    def remaining_now(self) -> int:
        return self.slot.remaining_now(self.captured_at, self.server_now)

    def text_lines(self) -> tuple[str, str, str]:
        title = self.skill_name or SLOT_LABELS.get(self.kind, self.kind)
        if not self.cd_known:
            return title, "CD未知", "CD未知"
        state = self.effective_state()
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
        state = self.effective_state()
        color = QColor(_COLORS.get(state, _COLORS[SKILL_UNKNOWN]))
        painter.setBrush(QColor("#0c1320"))
        painter.setPen(QPen(QColor("#24334e"), 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)

        title, main, sub = self.text_lines()
        # 名称行：4–24，单行省略 + 完整 tooltip
        name_rect = self.name_rect()
        name_font = QFont(self.font())
        name_font.setPixelSize(11)
        painter.setFont(name_font)
        metrics = QFontMetrics(name_font)
        elided = metrics.elidedText(title, Qt.TextElideMode.ElideMiddle, int(name_rect.width()))
        painter.setPen(QPen(QColor("#8b98a8")))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)
        self.setToolTip(f"{title}：{main}" if elided == title else f"{title}：{main}")

        # 中间区：28–82。大招/百分比用固定 54px 圆环，充能型用大号计数。
        middle = self.middle_rect()
        center = middle.center()
        use_ring = self.kind == SLOT_ULTIMATE and self.cd_known and state != SKILL_UNKNOWN
        if use_ring:
            ring = QRectF(center.x() - 27, center.y() - 27, 54, 54)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(59, 130, 196, 64), 5))
            painter.drawEllipse(ring)
            painter.setPen(QPen(QColor("#3b82c4"), 5))
            painter.drawArc(ring, 90 * 16, -int(3.6 * self.slot.percent * 16))
            pct_font = QFont(self.font())
            pct_font.setPixelSize(13)
            pct_font.setBold(True)
            painter.setFont(pct_font)
            painter.setPen(QPen(QColor("#7fb3e0")))
            painter.drawText(ring, Qt.AlignmentFlag.AlignCenter, main)
        elif state == SKILL_UNKNOWN or not self.cd_known:
            center_font = QFont(self.font())
            center_font.setPixelSize(14)
            painter.setFont(center_font)
            painter.setPen(QPen(QColor("#71808f")))
            painter.drawText(middle, Qt.AlignmentFlag.AlignCenter, "?")
        else:
            # 充能/就绪：大号计数（例如 1/2），20px bold
            count_font = QFont(self.font())
            count_font.setPixelSize(20)
            count_font.setBold(True)
            painter.setFont(count_font)
            painter.setPen(QPen(QColor("#7fb3e0")))
            painter.drawText(middle, Qt.AlignmentFlag.AlignCenter, main if main not in ("—",) else "—")

        # 底部行：88–102，12px muted；与中区至少 6px
        bottom_font = QFont(self.font())
        bottom_font.setPixelSize(12)
        painter.setFont(bottom_font)
        painter.setPen(QPen(color if state == SKILL_READY else QColor("#8b98a8")))
        painter.drawText(self.bottom_rect(), Qt.AlignmentFlag.AlignCenter, sub)
        painter.end()


_AVATAR_SIZE = 22
_AVATAR_RADIUS = 4
_AVATAR_CACHE: dict[str, QPixmap] = {}


def _clip_avatar(source: QPixmap) -> QPixmap:
    """缩放 22×22 并做圆角裁剪 + 1px 边框；透明区域用于圆角。"""
    target = QPixmap(_AVATAR_SIZE, _AVATAR_SIZE)
    target.fill(Qt.GlobalColor.transparent)
    scaled = source.scaled(
        _AVATAR_SIZE,
        _AVATAR_SIZE,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, _AVATAR_SIZE, _AVATAR_SIZE, _AVATAR_RADIUS, _AVATAR_RADIUS)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.setClipping(False)
    painter.setPen(QPen(QColor("#24334e"), 1))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(0.5, 0.5, _AVATAR_SIZE - 1, _AVATAR_SIZE - 1, _AVATAR_RADIUS, _AVATAR_RADIUS)
    painter.end()
    return target


def _fallback_avatar(letter: str) -> QPixmap:
    """未知干员：昵称首字 + 深蓝渐变底，圆角 4、字号 11。"""
    pixmap = QPixmap(_AVATAR_SIZE, _AVATAR_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, _AVATAR_SIZE, _AVATAR_SIZE, _AVATAR_RADIUS, _AVATAR_RADIUS)
    gradient = QLinearGradient(0, 0, _AVATAR_SIZE, _AVATAR_SIZE)
    gradient.setColorAt(0.0, QColor("#2b3b52"))
    gradient.setColorAt(1.0, QColor("#162235"))
    painter.fillPath(path, gradient)
    painter.setPen(QPen(QColor("#24334e"), 1))
    painter.drawPath(path)
    font = QFont()
    font.setPixelSize(11)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(QColor("#c8d3e1")))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, (letter or "?")[:1])
    painter.end()
    return pixmap


class SkillRow(QFrame):
    """一条队友技能行：干员头像/昵称 + 昵称/干员名 + 3 个固定槽位。"""

    def __init__(
        self,
        state: SkillState,
        parent: QWidget | None = None,
        *,
        server_now: int | None = None,
        operator: Operator | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(180)
        self.user_id = state.user_id
        self.state = state
        self.operator_def = operator
        self._avatar_key = ""
        self._avatar_source = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        header = QHBoxLayout()
        header.setSpacing(8)
        self.avatar = QLabel(state.avatar_letter)
        self.avatar.setObjectName("SkillAvatar")
        self.avatar.setFixedSize(22, 22)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.avatar)
        self.squad_badge = QLabel(self.avatar)
        self.squad_badge.setObjectName("SquadBadge")
        self.squad_badge.setFixedSize(13, 13)
        self.squad_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.squad_badge.setStyleSheet(
            "QLabel#SquadBadge { background:#f5a800; color:#10131a; border-radius:6px; "
            "font-size:10px; font-weight:700; }"
        )
        self.squad_badge.move(11, -3)
        self.squad_badge.hide()
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
        self.update_state(
            state,
            int(server_now) if server_now is not None else int(time.time() * 1000),
            pulse=False,
        )

    def update_state(
        self,
        state: SkillState,
        server_now: int,
        pulse: bool = False,
        *,
        operator: Operator | None = None,
    ) -> None:
        if operator is not None:
            self.operator_def = operator
        self.state = state
        if state.display_name != self.name_label.text():
            self.name_label.setText(state.display_name)
        self._apply_avatar(state)
        operator = self.operator_def
        self.operator_label.setText(
            (operator.display_name if operator is not None else (state.operator or "干员未共享"))
        )
        self._apply_squad_number(state.squad_number)
        unshared = state.is_unshared(server_now)
        self.status_label.setText("未共享" if unshared else "● 已共享")
        self.status_label.setStyleSheet("color: #ffd071;" if unshared else "color: #5fc98e;")
        for kind, widget in self.slot_widgets.items():
            meta = operator.skill(_SLOT_INDEX[kind]) if operator is not None else None
            widget.set_data(
                state.slot(kind),
                state.captured_at,
                server_now,
                pulse=pulse,
                skill_name=meta.name if meta is not None else "",
                cd_known=meta.cd_known if meta is not None else True,
            )

    def _apply_squad_number(self, number: int | None) -> None:
        if number in (1, 2, 3):
            self.squad_badge.setText(str(number))
            self.squad_badge.show()
            self.squad_badge.raise_()
        else:
            self.squad_badge.hide()

    def _apply_avatar(self, state: SkillState) -> None:
        """按干员文件加载头像；缓存按 operator_id；缺失时用首字渐变占位。"""
        operator = self.operator_def
        if operator is not None and operator.avatar_available():
            key = str(operator.id or "")
            pixmap = _AVATAR_CACHE.get(key)
            if pixmap is None:
                source = QPixmap(str(operator.avatar_path()))
                if not source.isNull():
                    pixmap = _clip_avatar(source)
                    _AVATAR_CACHE[key] = pixmap
            if pixmap is not None:
                self.avatar.setText("")
                self.avatar.setPixmap(pixmap)
                self._avatar_source = "operator"
                self._avatar_key = key
                return
        self._avatar_source = "fallback"
        self.avatar.setText("")
        self.avatar.setPixmap(_fallback_avatar(state.avatar_letter))
        self._avatar_key = f"name:{state.display_name}"


class SkillPanel(QWidget):
    """房间内技能标签页：每行一个队友，倒计时每秒刷新。"""

    sharing_toggled = Signal(bool)
    simulate_requested = Signal()
    capture_requested = Signal()
    settings_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        clock=None,
        catalog: OperatorCatalog | None = None,
    ) -> None:
        super().__init__(parent)
        self._states: dict[str, SkillState] = {}
        self._rows: dict[str, SkillRow] = {}
        self._clock_offset_ms = 0
        self._pulse = False
        self._catalog = catalog if catalog is not None else OperatorCatalog()
        self._server_now_provider = None
        # 可注入时钟（测试冻结时间）；默认使用本机时间
        self._clock = clock or (lambda: int(time.time() * 1000))
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
        title = QLabel("技能共享 (E2)")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.share_check = SwitchRow("共享我的技能", "", False)
        self.share_check.title_label.setStyleSheet("color: #f5a800; font-weight: 700;")
        self.share_check.setFixedWidth(150)
        self.share_check.toggled.connect(self._on_share_toggled)
        header.addWidget(self.share_check)
        self.simulate_button = QPushButton("模拟我的技能")
        self.simulate_button.setObjectName("Link")
        self.simulate_button.clicked.connect(self.simulate_requested.emit)
        self.simulate_button.hide()
        self.capture_button = QPushButton("识别 HUD")
        self.capture_button.setObjectName("Link")
        self.capture_button.setToolTip("截取游戏窗口并识别技能栏（E3b）")
        self.capture_button.clicked.connect(self.capture_requested.emit)
        self.capture_button.hide()
        self.settings_button = QPushButton("技能设置")
        self.settings_button.setObjectName("Ghost")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        header.addWidget(self.settings_button)
        root.addLayout(header)

        hint = QLabel("默认关闭；开启后 2 次/秒限频上报 · 左大招 / 中技能 / 右投掷物 · 30 分钟未更新=未共享")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollBar:vertical { background: #0c1320; width: 8px; margin: 0; }"
            "QScrollBar::handle:vertical { background: #24334e; min-height: 28px; border-radius: 4px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 8, 0)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        root.addWidget(self.scroll, stretch=1)

        self.empty_label = QLabel("暂无成员共享技能")
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

    def set_operator_catalog(self, catalog: OperatorCatalog) -> None:
        self._catalog = catalog if catalog is not None else OperatorCatalog()
        if self._states:
            self.set_states(self.states())

    def set_clock_offset(self, offset_ms: int) -> None:
        self._clock_offset_ms = int(offset_ms)
        self._tick()

    def set_server_now_provider(self, provider) -> None:
        """注入服务器时间估计（ready_at 模式用单调时钟驱动）。"""
        self._server_now_provider = provider

    def server_now_ms(self) -> int:
        if self._server_now_provider is not None:
            try:
                return int(self._server_now_provider())
            except Exception:  # noqa: BLE001
                pass
        return int(self._clock()) + self._clock_offset_ms

    def pause_updates(self) -> None:
        self._timer.stop()

    def resume_updates(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

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
            operator = self._catalog.resolve(state.operator_id, state.operator)
            self._rows[state.user_id].update_state(
                state, self.server_now_ms(), self._pulse, operator=operator
            )
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
        operator = self._catalog.resolve(state.operator_id, state.operator)
        row = SkillRow(
            state,
            self.list_widget,
            server_now=self.server_now_ms(),
            operator=operator,
        )
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
