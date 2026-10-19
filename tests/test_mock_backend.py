"""Mock 后端测试：不联网验证登录/注册/房间流程与 WS 消息（离线）。"""

from __future__ import annotations

import asyncio
import unittest

from core.canvas import make_stroke_op
from core.errors import ApiError, ErrorKind
from core.models import Room
from core.rooms import is_valid_room_code
from net.mock_backend import MockApiClient, MockWsClient


class MockApiTests(unittest.TestCase):
    def test_login_success_and_failure(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            result = await api.login("demo", "demo123")
            self.assertTrue(result.has_token)
            self.assertEqual(result.user["username"], "demo")
            self.assertIsInstance(result.token, str)

            with self.assertRaises(ApiError) as ctx:
                await api.login("demo", "wrong")
            self.assertEqual(ctx.exception.kind, ErrorKind.AUTH)
            self.assertEqual(ctx.exception.user_message, "用户名或密码错误")

            with self.assertRaises(ApiError) as missing:
                await api.login("nobody", "x")
            self.assertEqual(missing.exception.kind, ErrorKind.AUTH)

        asyncio.run(scenario())

    def test_register(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            created = await api.register("newbie", "abc123")
            self.assertEqual(created["username"], "newbie")
            # Mock 与 B2b v1 注册一致：返回 access_token + user，UI 可自动登录
            self.assertTrue(created.get("access_token"))
            self.assertEqual(created["user"]["username"], "newbie")

            with self.assertRaises(ApiError) as duplicate:
                await api.register("newbie", "abc123")
            self.assertEqual(duplicate.exception.kind, ErrorKind.CONFLICT)
            self.assertEqual(duplicate.exception.user_message, "用户名已存在")

            with self.assertRaises(ApiError) as short:
                await api.register("shorty", "123")
            self.assertEqual(short.exception.kind, ErrorKind.VALIDATION)

            # 新账号可以登录
            result = await api.login("newbie", "abc123")
            self.assertTrue(result.has_token)

        asyncio.run(scenario())

    def test_public_room_list_excludes_private(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            rooms = await api.list_rooms()
            codes = {room.code for room in rooms}
            self.assertIn("AB12C", codes)
            self.assertIn("K7M2P", codes)
            self.assertNotIn("Q4W8E", codes)  # 私有房间不出现在公共列表

        asyncio.run(scenario())

    def test_create_room_public_and_private(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")

            room = await api.create_room("我的房间", "public")
            self.assertTrue(is_valid_room_code(room.code))
            self.assertFalse(room.has_password)
            listed = {item.code for item in await api.list_rooms()}
            self.assertIn(room.code, listed)

            with self.assertRaises(ApiError) as no_password:
                await api.create_room("私密房", "private")
            self.assertEqual(no_password.exception.kind, ErrorKind.VALIDATION)

            private = await api.create_room("私密房", "private", "room-pass")
            self.assertTrue(private.has_password)
            self.assertNotIn(private.code, {item.code for item in await api.list_rooms()})

        asyncio.run(scenario())

    def test_join_and_leave_room(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")

            before = {room.code: room.member_count for room in await api.list_rooms()}
            joined = await api.join_room("ab12c")
            self.assertEqual(joined.code, "AB12C")
            self.assertEqual(joined.member_count, before["AB12C"] + 1)

            with self.assertRaises(ApiError) as not_found:
                await api.join_room("ZZZZZ")
            self.assertEqual(not_found.exception.kind, ErrorKind.ROOM_NOT_FOUND)

            with self.assertRaises(ApiError) as invalid:
                await api.join_room("ABC")
            self.assertEqual(invalid.exception.kind, ErrorKind.VALIDATION)

            await api.leave_room("AB12C")
            after = {room.code: room.member_count for room in await api.list_rooms()}
            self.assertEqual(after["AB12C"], before["AB12C"])

        asyncio.run(scenario())

    def test_join_private_room_password_flow(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")

            with self.assertRaises(ApiError) as required:
                await api.join_room("Q4W8E")
            self.assertEqual(required.exception.kind, ErrorKind.ROOM_PASSWORD_REQUIRED)
            self.assertTrue(required.exception.needs_room_password)

            with self.assertRaises(ApiError) as wrong:
                await api.join_room("Q4W8E", "0000")
            self.assertEqual(wrong.exception.kind, ErrorKind.ROOM_PASSWORD_INVALID)

            joined = await api.join_room("q4w8e", "1234")
            self.assertEqual(joined.code, "Q4W8E")
            self.assertTrue(joined.has_password)

        asyncio.run(scenario())

    def test_room_detail_members_and_connection_check(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")

            detail = await api.get_room_detail("ab12c")
            self.assertEqual(detail.room.code, "AB12C")
            self.assertEqual(
                {m.display_name for m in detail.members}, {"队友玩家", "队友-Bravo"}
            )
            self.assertTrue(all(m.nickname for m in detail.members))

            await api.join_room("AB12C")
            after_join = await api.get_room_detail("AB12C")
            self.assertIn("演示玩家", {m.display_name for m in after_join.members})

            await api.leave_room("AB12C")
            after_leave = await api.get_room_detail("AB12C")
            self.assertNotIn("演示玩家", {m.display_name for m in after_leave.members})

            by_id = await api.get_room_detail("mock-room-ab12c")
            self.assertEqual(by_id.room.code, "AB12C")

            with self.assertRaises(ApiError) as not_found:
                await api.get_room_detail("ZZZZZ")
            self.assertEqual(not_found.exception.kind, ErrorKind.ROOM_NOT_FOUND)

            check = await api.check_connection()
            self.assertTrue(check.ok)
            self.assertIn("HTTP 可达：✅", check.format_text())
            self.assertIn("房间接口：✅", check.format_text())
            self.assertGreaterEqual(check.rooms_count or 0, 2)

        asyncio.run(scenario())

    def test_message_history_pagination(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            page = await api.get_messages("AB12C", limit=2)
            self.assertEqual(["mock-msg-0003", "mock-msg-0002"], [m.message_id for m in page.messages])
            self.assertTrue(page.has_more)
            self.assertEqual("mock-msg-0002", page.next_before)
            self.assertEqual("先热身两把", page.messages[0].content)

            older = await api.get_messages("AB12C", before=page.next_before, limit=2)
            self.assertEqual(["mock-msg-0001"], [m.message_id for m in older.messages])
            self.assertFalse(older.has_more)
            self.assertIsNone(older.next_before)

            api.append_message("AB12C", {"id": "1", "username": "demo"}, "新消息", "c-new")
            latest = await api.get_messages("AB12C")
            self.assertEqual("新消息", latest.messages[0].content)
            self.assertEqual("c-new", latest.messages[0].client_msg_id)
            self.assertEqual(7, latest.window_days)  # F-c5 历史窗口字段

            with self.assertRaises(ApiError) as not_found:
                await api.get_messages("ZZZZZ")
            self.assertEqual(not_found.exception.kind, ErrorKind.ROOM_NOT_FOUND)

        asyncio.run(scenario())

    def test_profile_nickname_and_password(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            login = await api.login("demo", "demo123")
            self.assertEqual("演示玩家", login.user["nickname"])

            updated = await api.update_nickname("新昵称")
            self.assertEqual("新昵称", updated["nickname"])
            relogin = await api.login("demo", "demo123")
            self.assertEqual("新昵称", relogin.user["nickname"])

            with self.assertRaises(ApiError) as wrong_old:
                await api.change_password("wrong-pass", "newpass123")
            self.assertEqual(wrong_old.exception.kind, ErrorKind.VALIDATION)
            self.assertEqual("WRONG_OLD_PASSWORD", wrong_old.exception.code)
            self.assertEqual("旧密码错误", wrong_old.exception.user_message)

            with self.assertRaises(ApiError) as invalid_new:
                await api.change_password("demo123", "123")
            self.assertEqual("INVALID_NEW_PASSWORD", invalid_new.exception.code)
            self.assertIn("新密码", invalid_new.exception.user_message)

            await api.change_password("demo123", "newpass123")
            with self.assertRaises(ApiError):
                await api.login("demo", "demo123")
            result = await api.login("demo", "newpass123")
            self.assertTrue(result.has_token)

            with self.assertRaises(ApiError) as invalid_nickname:
                await api.update_nickname("")
            self.assertEqual(invalid_nickname.exception.code, "INVALID_NICKNAME")

        asyncio.run(scenario())

    def test_register_username_rules_flow(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            with self.assertRaises(ApiError) as invalid:
                await api.register("abc", "123456")
            self.assertEqual(invalid.exception.kind, ErrorKind.VALIDATION)
            self.assertEqual("INVALID_USERNAME", invalid.exception.code)

            created = await api.register("newbie1", "123456")
            self.assertEqual("newbie1", created["nickname"])
            result = await api.login("newbie1", "123456")
            self.assertEqual("newbie1", result.user["nickname"])

            with self.assertRaises(ApiError) as duplicate:
                await api.register("newbie1", "123456")
            self.assertEqual(duplicate.exception.kind, ErrorKind.CONFLICT)

        asyncio.run(scenario())

    def test_room_management_owner(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")
            room = await api.create_room("原名", "public")

            renamed = await api.update_room(room.code, name="新名字")
            self.assertEqual("新名字", renamed.name)
            secured = await api.update_room(room.code, password="roompass1")
            self.assertTrue(secured.has_password)
            self.assertEqual("roompass1", api._find_room(room.code).get("password"))

            # 非房主（同一 Mock 实例切换登录）不能改
            await api.login("player", "player123")
            with self.assertRaises(ApiError) as forbidden:
                await api.update_room(room.code, name="篡改")
            self.assertEqual(forbidden.exception.kind, ErrorKind.FORBIDDEN)
            self.assertEqual("NOT_ROOM_OWNER", forbidden.exception.code)

            await api.login("demo", "demo123")
            self.assertTrue(await api.delete_room(room.code))
            self.assertNotIn(room.code, {item.code for item in await api.list_rooms()})
            with self.assertRaises(ApiError) as deleted:
                await api.get_room_detail(room.code)
            self.assertEqual(deleted.exception.kind, ErrorKind.ROOM_NOT_FOUND)

        asyncio.run(scenario())


class MockCanvasTests(unittest.TestCase):
    def test_canvas_snapshot_flow(self) -> None:
        async def scenario() -> None:
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")
            room = await api.create_room("画板房", "public")

            initial = await api.get_canvas(room.code)
            self.assertEqual(0, len(initial.strokes))
            self.assertEqual(0, initial.rev)

            messages: list[dict] = []
            ws = MockWsClient(
                on_message=messages.append,
                user={"id": "1", "username": "demo"},
                room=room,
                latency=0,
                store=api,
            )
            task = asyncio.create_task(ws.run())
            await asyncio.sleep(0.02)
            await ws.join_room(room.code)
            await asyncio.sleep(0.02)
            joined = next(message for message in messages if message["type"] == "room_joined")
            self.assertEqual([], joined["canvas_snapshot"]["strokes"])

            op = make_stroke_op([(0.1, 0.1), (0.2, 0.2)], "#FF3B30", 4)
            self.assertTrue(await ws.send_canvas_op(op, 0, room.id))
            snapshot = await api.get_canvas(room.code)
            self.assertEqual(1, len(snapshot.strokes))
            self.assertEqual(0, snapshot.rev)

            ack = await ws.save_canvas_snapshot([op], 1, room.id)
            self.assertIsNotNone(ack)
            self.assertEqual(1, ack["rev"])
            saved = await api.get_canvas(room.code)
            self.assertEqual(1, len(saved.strokes))
            self.assertEqual(1, saved.rev)

            await ws.close()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())


class MockWsTests(unittest.TestCase):
    def test_ws_auth_join_and_chat_echo(self) -> None:
        async def scenario() -> None:
            messages: list[dict] = []
            states: list[str] = []
            api = MockApiClient(latency=0)
            await api.login("demo", "demo123")
            ws = MockWsClient(
                on_message=messages.append,
                on_state=lambda state, info: states.append(state),
                user={"id": "1", "username": "demo"},
                room=Room.from_api({"id": "mock-room-ab12c", "code": "AB12C", "name": "新手训练房"}),
                latency=0,
                store=api,
            )
            task = asyncio.create_task(ws.run())
            await asyncio.sleep(0.02)
            self.assertTrue(ws.connected)
            self.assertIn("connected", states)

            await ws.join_room("AB12C")
            await asyncio.sleep(0.02)
            types = [message.get("type") for message in messages]
            self.assertIn("auth_ok", types)
            self.assertIn("room_joined", types)
            room_joined = next(message for message in messages if message["type"] == "room_joined")
            self.assertTrue(room_joined["members"])
            self.assertEqual(room_joined["room"]["code"], "AB12C")

            client_msg_id = await ws.send_chat("大家好", "c-test", "mock-room-ab12c")
            self.assertEqual("c-test", client_msg_id)
            await asyncio.sleep(0.35)
            chat = next(message for message in messages if message["type"] == "chat_message")
            self.assertEqual(chat["content"], "大家好")
            self.assertEqual(chat["client_msg_id"], client_msg_id)
            self.assertTrue(chat["id"])
            self.assertEqual("demo", chat["user"]["username"])
            self.assertIsInstance(chat["created_at"], int)

            # Mock 回显也写入历史，供进房拉历史/分页测试
            page = await api.get_messages("AB12C")
            self.assertEqual("大家好", page.messages[0].content)
            self.assertEqual(client_msg_id, page.messages[0].client_msg_id)

            await ws.close()
            await asyncio.sleep(0.02)
            self.assertFalse(ws.connected)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
