"""大厅房间列表 diff（F-c3：自动刷新时按 id 增量更新，不整页重建）。"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Member, Room


def room_key(room: Room) -> str:
    """房间稳定标识：优先服务端 id，其次 5 位房间号。"""
    return room.id or room.code


def _members_signature(members: tuple[Member, ...]) -> tuple[tuple[str, str, str, bool], ...]:
    return tuple(
        (member.id, member.nickname, member.username, member.online) for member in members
    )


def room_signature(room: Room) -> tuple:
    """用于判断同一房间是否需要更新单元格（忽略 raw 字段）。"""
    return (
        room.id,
        room.code,
        room.name,
        room.owner_id,
        room.member_count,
        room.has_password,
        room.background_id,
        room.created_at,
        _members_signature(room.members),
    )


@dataclass(frozen=True)
class RoomDiff:
    """一次列表更新的增量结果；``order`` 为服务端返回的最新顺序。"""

    added: tuple[Room, ...] = ()
    removed: tuple[Room, ...] = ()
    updated: tuple[Room, ...] = ()
    order: tuple[Room, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.updated)


def diff_rooms(old: list[Room], new: list[Room]) -> RoomDiff:
    """按 ``room_key`` 对比新旧列表。

    - ``added``：新列表新增（保持新列表顺序）；
    - ``removed``：旧列表已不存在；
    - ``updated``：key 相同但展示字段变化（保持新列表顺序）；
    - ``order``：新列表顺序，供 UI 原地重排/更新。
    """
    old_by_key = {room_key(room): room for room in old}
    new_by_key = {room_key(room): room for room in new}

    added = tuple(room for room in new if room_key(room) not in old_by_key)
    removed = tuple(room for room in old if room_key(room) not in new_by_key)
    updated = tuple(
        room
        for room in new
        if room_key(room) in old_by_key
        and room_signature(room) != room_signature(old_by_key[room_key(room)])
    )
    return RoomDiff(added=added, removed=removed, updated=updated, order=tuple(new))
