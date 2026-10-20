"""H3：QML 连接/个人资料桥接属性与信号。"""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Property, QObject, Signal, Slot

from config import AppConfig, DEFAULT_SERVER_URL
from core.validation import ValidationError, validate_password_change


class ConnBridge(QObject):
    changed = Signal()
    test_requested = Signal(str, str)
    save_requested = Signal()
    reset_requested = Signal()
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._server = DEFAULT_SERVER_URL
        self._ws = ""
        self._mock = False
        self._token = False
        self._result = ""
        self._testing = False
        self._error = ""

    def _bump(self) -> None:
        self.changed.emit()

    def _get_server(self) -> str:
        return self._server

    def _set_server(self, value: str) -> None:
        self._server = str(value or "")
        self._bump()

    server = Property(str, _get_server, _set_server, notify=changed)

    def _get_ws(self) -> str:
        return self._ws

    def _set_ws(self, value: str) -> None:
        self._ws = str(value or "")
        self._bump()

    ws = Property(str, _get_ws, _set_ws, notify=changed)

    def _get_mock(self) -> bool:
        return self._mock

    def _set_mock(self, value: bool) -> None:
        self._mock = bool(value)
        self._bump()

    useMock = Property(bool, _get_mock, _set_mock, notify=changed)

    def _get_token(self) -> bool:
        return self._token

    def _set_token(self, value: bool) -> None:
        self._token = bool(value)
        self._bump()

    saveToken = Property(bool, _get_token, _set_token, notify=changed)

    @Property(str, notify=changed)
    def resultText(self) -> str:  # noqa: N802
        return self._result

    @Property(bool, notify=changed)
    def testing(self) -> bool:
        return self._testing

    @Property(str, notify=changed)
    def errorText(self) -> str:  # noqa: N802
        return self._error

    def apply_config(self, config: AppConfig) -> None:
        self._server = config.server_url
        self._ws = config.ws_url or ""
        self._mock = config.use_mock
        self._token = config.persist_token
        self._result = ""
        self._error = ""
        self._testing = False
        self._bump()

    def result_config(self, base: AppConfig) -> AppConfig:
        from config import normalize_server_url, normalize_ws_url

        server = normalize_server_url(self._server)
        ws = normalize_ws_url(self._ws) if self._ws.strip() else None
        return replace(base, server_url=server, ws_url=ws, use_mock=self._mock, persist_token=self._token)

    def set_testing(self, testing: bool) -> None:
        self._testing = bool(testing)
        self._bump()

    def set_test_result(self, text: str, ok: bool | None = None) -> None:
        self._testing = False
        self._result = str(text)
        self._bump()

    def set_error(self, text: str) -> None:
        self._error = str(text)
        self._result = ""
        self._testing = False
        self._bump()

    @Slot()
    def test(self) -> None:
        self.test_requested.emit(self._server, self._ws)

    @Slot()
    def save(self) -> None:
        self.save_requested.emit()

    @Slot()
    def reset(self) -> None:
        self.apply_config(AppConfig())
        self.reset_requested.emit()

    @Slot()
    def back(self) -> None:
        self.back_requested.emit()


class ProfileBridge(QObject):
    changed = Signal()
    nickname_requested = Signal(str)
    password_requested = Signal(str, str)
    logout_requested = Signal()
    back_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._account = ""
        self._nickname = ""
        self._nickname_result = ""
        self._password_result = ""
        self._busy = False

    @Property(str, notify=changed)
    def account(self) -> str:
        return self._account

    def _get_nickname(self) -> str:
        return self._nickname

    def _set_nickname(self, value: str) -> None:
        self._nickname = str(value or "")
        self.changed.emit()

    nickname = Property(str, _get_nickname, _set_nickname, notify=changed)

    @Property(str, notify=changed)
    def nicknameResult(self) -> str:  # noqa: N802
        return self._nickname_result

    @Property(str, notify=changed)
    def passwordResult(self) -> str:  # noqa: N802
        return self._password_result

    def set_account(self, account: str, nickname: str) -> None:
        self._account = str(account or "")
        self._nickname = str(nickname or "")
        self.changed.emit()

    def set_nickname_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.changed.emit()

    def set_nickname_result(self, text: str, ok: bool | None = None) -> None:
        self._busy = False
        self._nickname_result = str(text)
        self.changed.emit()

    def set_password_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.changed.emit()

    def set_password_result(self, text: str, ok: bool | None = None) -> None:
        self._busy = False
        self._password_result = str(text)
        self.changed.emit()

    @Slot(str)
    def save_nickname(self, nickname: str) -> None:
        self._nickname = str(nickname or "")
        self.nickname_requested.emit(self._nickname)

    @Slot(str, str, str)
    def change_password(self, old_password: str, new_password: str, confirm: str) -> None:
        try:
            old_password, new_password = validate_password_change(old_password, new_password, confirm)
        except ValidationError as exc:
            self.set_password_result(str(exc), False)
            return
        self.password_requested.emit(old_password, new_password)

    @Slot()
    def logout(self) -> None:
        self.logout_requested.emit()

    @Slot()
    def back(self) -> None:
        self.back_requested.emit()
