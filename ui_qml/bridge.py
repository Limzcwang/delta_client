"""H1：QML 与 Widgets 业务层的桥接对象。"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ui_qml.models import LoginHistoryModel, RoomListModel


class LobbyBridge(QObject):
    refresh_requested = Signal()
    create_requested = Signal()
    join_requested = Signal(str)
    settings_requested = Signal()
    profile_requested = Signal()
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._user_name = "DeltaQA01"
        self._server_text = "https://deltachat.icu:8443"
        self._mode_text = "LIVE"
        self._status_text = "✓ 登录成功：DeltaQA01"
        self._selected_code = ""
        self.public_model = RoomListModel()
        self.my_model = RoomListModel()

    @Property(str, notify=changed)
    def userName(self) -> str:  # noqa: N802
        return self._user_name

    @Property(str, notify=changed)
    def serverText(self) -> str:  # noqa: N802
        return self._server_text

    @Property(str, notify=changed)
    def modeText(self) -> str:  # noqa: N802
        return self._mode_text

    @Property(str, notify=changed)
    def statusText(self) -> str:  # noqa: N802
        return self._status_text

    @Property(str, notify=changed)
    def selectedCode(self) -> str:  # noqa: N802
        return self._selected_code

    @Property(int, notify=changed)
    def myRoomsCount(self) -> int:  # noqa: N802
        return self.my_model.count

    def set_user(self, name: str) -> None:
        self._user_name = str(name or "-")
        self.changed.emit()

    def set_mode(self, is_mock: bool, server_url: str) -> None:
        self._mode_text = "MOCK" if is_mock else "LIVE"
        self._server_text = str(server_url or "")
        self.changed.emit()

    def set_status(self, text: str) -> None:
        self._status_text = str(text or "")
        self.changed.emit()

    @Slot(str)
    def select_room(self, code: str) -> None:
        self._selected_code = str(code or "")
        self.changed.emit()

    def set_my_rooms(self, rooms) -> None:
        self.my_model.set_rooms(rooms)
        self.changed.emit()

    @Slot()
    def refresh(self) -> None:
        self.refresh_requested.emit()

    @Slot()
    def create(self) -> None:
        self.create_requested.emit()

    @Slot(str)
    def join(self, code: str) -> None:
        if code:
            self.join_requested.emit(str(code))

    @Slot()
    def settings(self) -> None:
        self.settings_requested.emit()

    @Slot()
    def profile(self) -> None:
        self.profile_requested.emit()


class LoginBridge(QObject):
    login_requested = Signal(str, str)
    register_requested = Signal(str, str)
    history_selected = Signal(str)
    history_delete_requested = Signal(str)
    history_clear_requested = Signal()
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._history_entries: list[dict[str, object]] = []
        self._error = ""
        self._loading = False
        self._register = False
        self._history_visible = False
        self._confirm_clear = False
        self._account = ""
        self._password = ""
        self.history_model = LoginHistoryModel()

    @Property(str, notify=changed)
    def errorText(self) -> str:  # noqa: N802
        return self._error

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(bool, notify=changed)
    def registerMode(self) -> bool:  # noqa: N802
        return self._register

    @Property(bool, notify=changed)
    def historyVisible(self) -> bool:  # noqa: N802
        return self._history_visible

    @Property(bool, notify=changed)
    def confirmClearVisible(self) -> bool:  # noqa: N802
        return self._confirm_clear

    @Property("QVariantList", notify=changed)
    def historyEntries(self):  # noqa: N802
        return list(self._history_entries)

    @Slot(str, result=str)
    def historyTooltip(self, username: str) -> str:  # noqa: N802
        for entry in self._history_entries:
            if str(entry.get("username", "")) == str(username):
                when = str(entry.get("timeText", "") or "-")
                return f"{username}\n最近登录：{when}   （含本机保存的密码）"
        return str(username)

    @Property(str, notify=changed)
    def account(self) -> str:
        return self._account

    @Property(str, notify=changed)
    def password(self) -> str:
        return self._password

    def set_entries(self, entries: Any) -> None:
        self.history_model.set_entries(entries)
        self._history_entries = [
            {
                "username": str(getattr(entry, "username", "") or ""),
                "timeText": str(getattr(entry, "last_used_text", "") or ""),
                "hasPassword": bool(getattr(entry, "has_password", False)),
            }
            for entry in entries
        ]
        self.changed.emit()

    def set_error(self, text: str) -> None:
        self._error = str(text)
        self._loading = False
        self.changed.emit()

    def set_busy(self, busy: bool) -> None:
        self._loading = bool(busy)
        self.changed.emit()

    def apply_saved_login(self, username: str, password: str, *, expired: bool = False) -> None:
        self._account = username
        self._password = password or ""
        self._history_visible = False
        self._error = "密码已过期，请重新输入" if expired else ""
        self.changed.emit()

    def show_success(self, text: str) -> None:
        self._error = ""
        self.changed.emit()

    @Slot()
    def toggle_mode(self) -> None:
        self._register = not self._register
        self._error = ""
        self.changed.emit()

    @Slot()
    def toggle_history(self) -> None:
        self._history_visible = not self._history_visible
        self.changed.emit()

    @Slot()
    def hide_history(self) -> None:
        if self._history_visible:
            self._history_visible = False
            self.changed.emit()
        self._confirm_clear = False

    @Slot(str, str)
    def submit(self, username: str, password: str) -> None:
        self._account = str(username or "")
        self._password = str(password or "")
        self._error = ""
        self._loading = True
        self.changed.emit()
        if self._register:
            self.register_requested.emit(self._account, self._password)
        else:
            self.login_requested.emit(self._account, self._password)

    @Slot(str)
    def select_history(self, username: str) -> None:
        self._history_visible = False
        self.history_selected.emit(str(username))

    def select_history_index(self, index: int) -> None:
        if 0 <= int(index) < self.history_model.rowCount():
            username = self.history_model.data(self.history_model.index(int(index), 0), self.history_model.UsernameRole)
            if username:
                self.select_history(str(username))

    @Slot(str)
    def delete_history(self, username: str) -> None:
        self.history_delete_requested.emit(str(username))

    @Slot()
    def clear_history(self) -> None:
        self.request_clear_history()

    @Slot()
    def request_clear_history(self) -> None:
        if not self._history_entries:
            return
        self._confirm_clear = True
        self.changed.emit()

    @Slot()
    def cancel_clear_history(self) -> None:
        self._confirm_clear = False
        self.changed.emit()

    @Slot()
    def confirm_clear_history(self) -> None:
        if not self._confirm_clear:
            return
        self._confirm_clear = False
        self._history_entries = []
        self.history_model.set_entries([])
        self.changed.emit()
        self.history_clear_requested.emit()

    @Slot()
    def cancel(self) -> None:
        self._loading = False
        self._error = ""
        self.changed.emit()
