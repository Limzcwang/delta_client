"""H1：QML 列表模型（房间/历史账号），复用 Python 数据结构。"""

from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt, Property, Signal


class RoomListModel(QAbstractListModel):
    countChanged = Signal()

    CodeRole = Qt.ItemDataRole.UserRole + 1
    NameRole = Qt.ItemDataRole.UserRole + 2
    MembersRole = Qt.ItemDataRole.UserRole + 3
    KindRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[dict[str, str]] = []

    def roleNames(self):  # noqa: N802
        return {
            self.CodeRole: b"code",
            self.NameRole: b"name",
            self.MembersRole: b"members",
            self.KindRole: b"kind",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        return {
            self.CodeRole: row["code"],
            self.NameRole: row["name"],
            self.MembersRole: row["members"],
            self.KindRole: row["kind"],
        }.get(role)

    def set_rooms(self, rooms: Iterable[Any]) -> None:
        rows = []
        for room in rooms:
            code = str(getattr(room, "code", "") or "")
            name = str(getattr(room, "display_name", "") or getattr(room, "name", "") or "")
            members = str(getattr(room, "member_count", 0) or 0)
            private = bool(getattr(room, "has_password", False) or getattr(room, "is_private", False))
            rows.append({"code": code, "name": name, "members": members, "kind": "私有" if private else "公开"})
        if rows == self._rows:
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
        self.countChanged.emit()
        self.countChanged.emit()

    @Property(int, notify=countChanged)
    def count(self) -> int:  # pragma: no cover - QML 绑定
        return len(self._rows)


class LoginHistoryModel(QAbstractListModel):
    countChanged = Signal()

    UsernameRole = Qt.ItemDataRole.UserRole + 1
    TimeRole = Qt.ItemDataRole.UserRole + 2
    LockRole = Qt.ItemDataRole.UserRole + 3

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[dict[str, Any]] = []

    def roleNames(self):  # noqa: N802
        return {
            self.UsernameRole: b"username",
            self.TimeRole: b"timeText",
            self.LockRole: b"hasPassword",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        return {
            self.UsernameRole: row["username"],
            self.TimeRole: row["timeText"],
            self.LockRole: row["hasPassword"],
        }.get(role)

    @Property(int, notify=countChanged)
    def count(self) -> int:  # pragma: no cover - QML 绑定
        return len(self._rows)

    def set_entries(self, entries: Iterable[Any]) -> None:
        rows = [
            {
                "username": str(getattr(entry, "username", "") or ""),
                "timeText": str(getattr(entry, "last_used_text", "") or ""),
                "hasPassword": bool(getattr(entry, "has_password", False)),
            }
            for entry in entries
        ]
        if rows == self._rows:
            return
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()
