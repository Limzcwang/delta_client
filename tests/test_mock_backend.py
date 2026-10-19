"""Mock 后端测试：不联网验证登录/注册/房间流程与 WS 消息（离线）。"""

from __future__ import annotations

import asyncio
import unittest

from core.errors import ApiError, ErrorKind
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
            self.assertEqual({m.username for m in detail.members}, {"player", "队友-Bravo"})

            await api.join_room("AB12C")
            after_join = await api.get_room_detail("AB12C")
            self.assertIn("demo", {m.username for m in after_join.members})

            await api.leave_room("AB12C")
            after_leave = await api.get_room_detail("AB12C")
            self.assertNotIn("demo", {m.username for m in after_leave.members})

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


class MockWsTests(unittest.TestCase):
    def test_ws_auth_join_and_chat_echo(self) -> None:
        async def scenario() -> None:
            messages: list[dict] = []
            states: list[str] = []
            ws = MockWsClient(
                on_message=messages.append,
                on_state=lambda state, info: states.append(state),
                user={"id": "1", "username": "demo"},
                latency=0,
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

            client_msg_id = await ws.send_chat("大家好")
            self.assertTrue(client_msg_id)
            await asyncio.sleep(0.35)
            chat = next(message for message in messages if message["type"] == "chat_message")
            self.assertEqual(chat["content"], "大家好")
            self.assertEqual(chat["client_msg_id"], client_msg_id)

            await ws.close()
            await asyncio.sleep(0.02)
            self.assertFalse(ws.connected)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
