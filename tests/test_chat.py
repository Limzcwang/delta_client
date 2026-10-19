"""聊天时间线测试：乐观更新、广播认领、去重、失败重试、历史分页合并（离线）。"""

from __future__ import annotations

import unittest

from core.chat import (
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    ChatEntry,
    ChatTimeline,
)
from core.models import ChatMessage, ChatPage


def make_message(
    message_id: str = "m-1",
    client_msg_id: str = "",
    sender: str = "bob",
    content: str = "hello",
    created_at: int = 1750000000000,
    room_id: str = "room-1",
) -> ChatMessage:
    return ChatMessage(
        message_id=message_id,
        room_id=room_id,
        sender_name=sender,
        content=content,
        client_msg_id=client_msg_id,
        created_at=created_at,
    )


class PendingConfirmTests(unittest.TestCase):
    def test_pending_entry(self) -> None:
        timeline = ChatTimeline()
        entry = timeline.add_pending("c-1", "alice", "hi", 1750000000000)
        self.assertEqual(entry.status, STATUS_PENDING)
        self.assertTrue(entry.outgoing)
        self.assertIn("发送中", entry.display_text())
        self.assertIs(timeline.get("c-1"), entry)

    def test_confirm_replaces_pending_without_duplicate(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi", 1750000000000)
        result = timeline.merge_remote(make_message("m-9", client_msg_id="c-1", content="hi"))
        self.assertEqual(result, "confirmed")
        self.assertEqual(1, len(timeline.entries))
        entry = timeline.entries[0]
        self.assertEqual(entry.status, STATUS_SENT)
        self.assertEqual(entry.message_id, "m-9")
        self.assertIn("发送中", timeline.add_pending("c-2", "a", "x").display_text())  # 其他条目不受影响

    def test_confirm_keeps_local_content_if_broadcast_missing_content(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi", 1750000000000)
        timeline.merge_remote(ChatMessage(client_msg_id="c-1", content=""))
        self.assertEqual("hi", timeline.entries[0].content)

    def test_duplicate_broadcast_ignored(self) -> None:
        timeline = ChatTimeline()
        message = make_message("m-1", "c-1")
        self.assertEqual("appended", timeline.merge_remote(message))
        self.assertEqual("duplicate", timeline.merge_remote(message))
        self.assertEqual(1, len(timeline.entries))

    def test_remote_message_without_client_msg_id_appended(self) -> None:
        timeline = ChatTimeline()
        self.assertEqual("appended", timeline.merge_remote(make_message("m-1", "", "bob")))
        self.assertEqual(1, len(timeline.entries))
        self.assertFalse(timeline.entries[0].outgoing)


class FailureRetryTests(unittest.TestCase):
    def test_fail_and_retry_same_client_msg_id(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi", 1750000000000)
        self.assertTrue(timeline.fail("c-1", "发送过快"))
        self.assertEqual(1, len(timeline.failed_entries()))
        self.assertEqual(STATUS_FAILED, timeline.get("c-1").status)
        self.assertIn("发送失败", timeline.get("c-1").display_text())

        retried = timeline.retry("c-1")
        self.assertIsNotNone(retried)
        assert retried is not None
        self.assertEqual(STATUS_PENDING, retried.status)
        self.assertEqual("c-1", retried.client_msg_id)
        self.assertEqual("", retried.error)

    def test_retry_only_failed(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi")
        timeline.merge_remote(make_message("m-1", "c-1"))
        self.assertIsNone(timeline.retry("c-1"))

    def test_fail_all_pending_returns_failed_entries(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "a", "one")
        timeline.add_pending("c-2", "a", "two")
        timeline.merge_remote(make_message("m-0", "c-0"))
        failed = timeline.fail_all_pending("RATE_LIMITED")
        self.assertEqual(["c-1", "c-2"], [entry.client_msg_id for entry in failed])
        self.assertEqual([], timeline.pending_entries())

    def test_timeout_fail_after_copy(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi")
        self.assertTrue(timeline.fail("c-1", "发送超时"))
        self.assertTrue(timeline.fail_all_pending("不会重复标记") == [])


class HistoryTests(unittest.TestCase):
    def test_initial_page_rendered_oldest_first(self) -> None:
        timeline = ChatTimeline()
        page = ChatPage(
            messages=(make_message("m-3", content="3"), make_message("m-2", content="2"), make_message("m-1", content="1")),
            has_more=True,
            next_before="m-1",
        )
        added = timeline.add_page(page)
        self.assertEqual(3, added)
        self.assertEqual(["1", "2", "3"], [entry.content for entry in timeline.entries])

    def test_older_page_prepended_and_deduped(self) -> None:
        timeline = ChatTimeline()
        timeline.add_page(ChatPage(messages=(make_message("m-3", content="3"), make_message("m-2", content="2"))))
        added = timeline.add_page(
            ChatPage(messages=(make_message("m-2"), make_message("m-1", content="1"), make_message("m-0", content="0")))
        )
        self.assertEqual(2, added)
        self.assertEqual(["0", "1", "2", "3"], [entry.content for entry in timeline.entries])

    def test_history_dedupes_against_confirmed_broadcast(self) -> None:
        timeline = ChatTimeline()
        timeline.add_pending("c-1", "alice", "hi")
        timeline.merge_remote(make_message("m-1", "c-1", content="hi"))
        added = timeline.add_page(ChatPage(messages=(make_message("m-1", "c-1", content="hi"),)))
        self.assertEqual(0, added)
        self.assertEqual(1, len(timeline.entries))

    def test_system_entries(self) -> None:
        timeline = ChatTimeline()
        timeline.add_system("已进入房间")
        self.assertTrue(timeline.entries[0].system)
        self.assertEqual("— 已进入房间 —", timeline.entries[0].display_text())


class EntryTests(unittest.TestCase):
    def test_from_message(self) -> None:
        entry = ChatEntry.from_message(make_message("m-1", "c-1", sender="bob", content="yo"))
        self.assertEqual("m-1", entry.key)
        self.assertEqual(STATUS_SENT, entry.status)
        self.assertIn("bob", entry.display_text())


if __name__ == "__main__":
    unittest.main()
