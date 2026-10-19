"""聊天时间线：本地乐观更新 + 服务端广播认领 + 历史分页合并（纯逻辑）。

设计目标（对应 PROTOCOL C 定稿行为）：

- 发送后先插入 ``pending`` 条目（本地回显），不等待 ack；
- 服务端把 ``chat_message`` 广播给所有人（含发送者），客户端用
  ``client_msg_id`` 认领并**原地更新**为 ``sent``，绝不重复插入；
- 没有 ``client_msg_id`` / 非本机的消息按 ``id`` 去重后追加；
- 失败/超时保留条目并标红，重试时**复用同一个 client_msg_id**；
- 历史分页（``items`` 新→旧）合并到列表头部，并跳过已存在的消息。

本模块不依赖 Qt / 网络，便于离线单测。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from core.models import ChatMessage, ChatPage, format_timestamp

STATUS_SENT = "sent"
STATUS_PENDING = "pending"
STATUS_FAILED = "failed"


@dataclass(frozen=True)
class ChatEntry:
    """聊天列表中的一条（本地发送/服务端广播/系统提示）。"""

    key: str
    sender_name: str = ""
    content: str = ""
    created_at: int | None = None
    message_id: str = ""
    client_msg_id: str = ""
    status: str = STATUS_SENT
    error: str = ""
    system: bool = False
    outgoing: bool = False

    @property
    def time_text(self) -> str:
        return format_timestamp(self.created_at)

    @property
    def is_failed(self) -> bool:
        return self.status == STATUS_FAILED

    @property
    def is_pending(self) -> bool:
        return self.status == STATUS_PENDING

    def display_text(self) -> str:
        if self.system:
            return f"— {self.content} —"
        stamp = f"[{self.time_text}] " if self.time_text else ""
        base = f"{stamp}{self.sender_name}：{self.content}"
        if self.status == STATUS_PENDING:
            return f"{base}  · 发送中…"
        if self.status == STATUS_FAILED:
            reason = self.error or "发送失败"
            return f"⚠ {base} 发送失败：{reason}（双击重试）"
        return base

    @classmethod
    def from_message(cls, message: ChatMessage, *, outgoing: bool = False) -> "ChatEntry":
        key = message.message_id or message.client_msg_id or f"anon-{id(message)}"
        return cls(
            key=key,
            sender_name=message.sender_name,
            content=message.content,
            created_at=message.created_at,
            message_id=message.message_id,
            client_msg_id=message.client_msg_id,
            status=STATUS_SENT,
            outgoing=outgoing,
        )


class ChatTimeline:
    """按时间顺序维护聊天条目；所有变更方法返回是否发生变化。"""

    def __init__(self) -> None:
        self.entries: list[ChatEntry] = []

    # ---------- 查询 ----------
    @property
    def is_empty(self) -> bool:
        return not self.entries

    def get(self, client_msg_id: str) -> ChatEntry | None:
        if not client_msg_id:
            return None
        for entry in self.entries:
            if entry.client_msg_id == client_msg_id:
                return entry
        return None

    def pending_entries(self) -> list[ChatEntry]:
        return [entry for entry in self.entries if entry.status == STATUS_PENDING]

    def failed_entries(self) -> list[ChatEntry]:
        return [entry for entry in self.entries if entry.status == STATUS_FAILED]

    def last_pending_content(self) -> str | None:
        pending = self.pending_entries()
        return pending[-1].content if pending else None

    # ---------- 变更 ----------
    def clear(self) -> None:
        self.entries.clear()

    def add_system(self, text: str) -> ChatEntry:
        entry = ChatEntry(key=f"sys-{len(self.entries)}-{len(text)}", content=str(text), system=True)
        self.entries.append(entry)
        return entry

    def add_pending(
        self,
        client_msg_id: str,
        sender_name: str,
        content: str,
        created_at: int | None = None,
    ) -> ChatEntry:
        """发送前插入本地乐观条目（status=pending）。"""
        entry = ChatEntry(
            key=client_msg_id,
            sender_name=sender_name,
            content=content,
            created_at=created_at,
            client_msg_id=client_msg_id,
            status=STATUS_PENDING,
            outgoing=True,
        )
        self.entries.append(entry)
        return entry

    def merge_remote(self, message: ChatMessage) -> str:
        """合并一条服务端广播/历史消息。

        返回 ``"confirmed"``（认领本地 pending 并原地更新）、``"appended"``
        （新消息追加）或 ``"duplicate"``（已存在，忽略）。
        """
        if not isinstance(message, ChatMessage):
            raise TypeError("merge_remote 需要 ChatMessage")
        # 1) 按 message_id 去重（同一条广播可能重复到达）
        if message.message_id and any(entry.message_id == message.message_id for entry in self.entries):
            return "duplicate"
        # 2) 用 client_msg_id 认领本机 pending 条目；已发送过的同 cid 广播不重复渲染
        if message.client_msg_id:
            for index, entry in enumerate(self.entries):
                if entry.client_msg_id != message.client_msg_id:
                    continue
                if (
                    entry.status == STATUS_SENT
                    and entry.message_id
                    and message.message_id
                    and entry.message_id != message.message_id
                ):
                    return "duplicate"
                self.entries[index] = replace(
                    entry,
                    message_id=message.message_id or entry.message_id,
                    sender_name=message.sender_name or entry.sender_name,
                    content=message.content or entry.content,
                    created_at=message.created_at or entry.created_at,
                    status=STATUS_SENT,
                    error="",
                )
                return "confirmed"
        # 3) 无 id 的消息按 client_msg_id 去重
        if message.client_msg_id and any(entry.client_msg_id == message.client_msg_id for entry in self.entries):
            return "duplicate"
        self.entries.append(ChatEntry.from_message(message))
        return "appended"

    def add_page(self, page: ChatPage) -> int:
        """合并历史页（``items`` 新→旧），插入到当前列表头部，返回新增条数。

        历史一定早于实时消息；首次加载与向上翻页都插入到头部，并跳过已存在
        的 ``message_id`` / ``client_msg_id``（避免重连后重复加载）。
        """
        existing_ids = {entry.message_id for entry in self.entries if entry.message_id}
        existing_client_ids = {entry.client_msg_id for entry in self.entries if entry.client_msg_id}
        ordered = list(page.messages)[::-1]  # 新→旧 转成 旧→新
        inserted = 0
        for message in ordered:
            if message.message_id and message.message_id in existing_ids:
                continue
            if message.client_msg_id and message.client_msg_id in existing_client_ids:
                continue
            entry = ChatEntry.from_message(message)
            self.entries.insert(inserted, entry)
            inserted += 1
            if entry.message_id:
                existing_ids.add(entry.message_id)
            if entry.client_msg_id:
                existing_client_ids.add(entry.client_msg_id)
        return inserted

    def fail(self, client_msg_id: str, reason: str) -> bool:
        for index, entry in enumerate(self.entries):
            if entry.client_msg_id == client_msg_id and entry.status != STATUS_FAILED:
                self.entries[index] = replace(entry, status=STATUS_FAILED, error=str(reason))
                return True
        return False

    def mark_sent(self, client_msg_id: str) -> bool:
        for index, entry in enumerate(self.entries):
            if entry.client_msg_id == client_msg_id and entry.status == STATUS_PENDING:
                self.entries[index] = replace(entry, status=STATUS_SENT, error="")
                return True
        return False

    def retry(self, client_msg_id: str) -> ChatEntry | None:
        """把失败条目重置为 pending，并返回它（重试复用同一个 client_msg_id）。"""
        for index, entry in enumerate(self.entries):
            if entry.client_msg_id == client_msg_id and entry.status == STATUS_FAILED:
                updated = replace(entry, status=STATUS_PENDING, error="")
                self.entries[index] = updated
                return updated
        return None

    def fail_all_pending(self, reason: str) -> list[ChatEntry]:
        """服务端 error 无 client_msg_id 时，把所有 pending 标记失败。

        返回被标记失败的条目；RATE_LIMITED 等场景 UI 可据此恢复输入框内容。
        """
        failed: list[ChatEntry] = []
        for index, entry in enumerate(self.entries):
            if entry.status != STATUS_PENDING:
                continue
            updated = replace(entry, status=STATUS_FAILED, error=str(reason))
            self.entries[index] = updated
            failed.append(updated)
        return failed


def entries_from_messages(messages: Iterable[ChatMessage]) -> list[ChatEntry]:
    """把一批消息转成条目（测试/工具用）。"""
    return [ChatEntry.from_message(message) for message in messages]
