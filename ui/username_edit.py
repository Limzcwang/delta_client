"""账号输入框：输入/粘贴即时过滤非法字符，保留光标位置；IME 组合期间不拆字。"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QWidget

from core.validation import sanitize_username_input, sanitized_cursor_position


class UsernameLineEdit(QLineEdit):
    """只允许账号合法字符的 QLineEdit。

    - ``mode="register"``：ASCII 字母/数字（≤20）；
    - ``mode="login"``：字母/数字 + ``_ -``（≤32，兼容老账号）；
    - 中文输入法组合（preedit）期间跳过清洗，提交上屏后再过滤，避免打断输入法；
    - 过滤造成文本变化时按“光标前非法字符数”回退光标，而不是跳到末尾。
    """

    def __init__(self, mode: str = "login", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "login" if str(mode).lower() == "login" else "register"
        self._ime_composing = False
        self._applying = False
        self.textChanged.connect(self._on_text_changed)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        normalized = "login" if str(mode).lower() == "login" else "register"
        if normalized == self._mode:
            return
        self._mode = normalized
        # 模式切换后现有可能含新模式下非法字符（如注册页的 _），立即清洗
        self._apply_sanitize()

    # ---------- 内部 ----------
    def _on_text_changed(self, _text: str) -> None:
        if self._applying or self._ime_composing:
            return
        self._apply_sanitize()

    def _apply_sanitize(self) -> None:
        raw = self.text()
        sanitized = sanitize_username_input(raw, self._mode)
        if sanitized == raw:
            return
        cursor = sanitized_cursor_position(raw, self.cursorPosition(), self._mode)
        self._applying = True
        try:
            # 不 blockSignals：外部 textChanged（实时提示）仍需收到最终文本；
            # _applying 标记防止本槽递归。
            self.setText(sanitized)
            self.setCursorPosition(min(cursor, len(sanitized)))
        finally:
            self._applying = False

    def inputMethodEvent(self, event) -> None:  # noqa: N802 - Qt 覆盖
        """IME 组合期间不拆字；上屏（commit）后再清洗。"""
        self._ime_composing = bool(event.preeditString())
        try:
            super().inputMethodEvent(event)
        finally:
            composing = self._ime_composing
            self._ime_composing = False
            if not composing:
                self._apply_sanitize()
