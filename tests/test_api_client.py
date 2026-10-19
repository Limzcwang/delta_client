"""个人资料接口契约测试（不联网）：改昵称走 PATCH /me，改密走 POST /me/password。

用 fake ``_request`` 捕获实际方法/路径/body，避免依赖 aiohttp。
"""

from __future__ import annotations

import asyncio
import unittest

from core import protocol
from core.errors import ApiError, api_error_from_response
from net.api_client import ApiClient


class ProfileApiContractTests(unittest.TestCase):
    def _client_with_fake(self, calls: list[tuple[str, str, object]], response=None, error=None):
        client = ApiClient("http://unit-test")

        async def fake_request(method: str, path: str, **kwargs):
            calls.append((method, path, kwargs.get("json_body")))
            if error is not None:
                raise error
            return response

        client._request = fake_request  # type: ignore[method-assign]
        return client

    def test_update_nickname_uses_patch_me(self) -> None:
        async def scenario() -> None:
            calls: list[tuple[str, str, object]] = []
            client = self._client_with_fake(
                calls,
                # 真实后端响应形态：{"user": {...}}（无 data 包装）
                response={"user": {"id": "1", "username": "demo", "nickname": "新昵称"}},
            )
            result = await client.update_nickname("新昵称")
            self.assertEqual(
                [("PATCH", protocol.API_V1_ME, {"nickname": "新昵称"})], calls
            )
            self.assertEqual("新昵称", result["nickname"])
            self.assertEqual("demo", result["username"])

        asyncio.run(scenario())

    def test_change_password_uses_post_password_endpoint(self) -> None:
        async def scenario() -> None:
            calls: list[tuple[str, str, object]] = []
            client = self._client_with_fake(calls, response={"code": 200, "message": "OK", "data": None})
            await client.change_password("old-pass", "new-pass-123")
            # F 契约：只允许 POST /users/me/password，不做 PATCH/422 猜测回退
            self.assertEqual(
                [
                    (
                        "POST",
                        protocol.API_V1_ME_PASSWORD,
                        {"old_password": "old-pass", "new_password": "new-pass-123"},
                    )
                ],
                calls,
            )

        asyncio.run(scenario())

    def test_wrong_old_password_error_message(self) -> None:
        async def scenario() -> None:
            error = api_error_from_response(
                400,
                {
                    "code": 40000,
                    "message": "",
                    "data": {"error_code": "WRONG_OLD_PASSWORD"},
                    "request_id": "req_1",
                },
            )
            calls: list[tuple[str, str, object]] = []
            client = self._client_with_fake(calls, error=error)
            with self.assertRaises(ApiError) as ctx:
                await client.change_password("wrong", "new-pass-123")
            self.assertEqual("WRONG_OLD_PASSWORD", ctx.exception.code)
            self.assertEqual("旧密码错误", ctx.exception.user_message)

        asyncio.run(scenario())

    def test_invalid_new_password_error_message(self) -> None:
        error = api_error_from_response(
            400,
            {"code": 40000, "message": "", "data": {"error_code": "INVALID_NEW_PASSWORD"}},
        )
        self.assertEqual("新密码不合法（8–32 位）", error.user_message)


class MyRoomsApiTests(unittest.TestCase):
    def test_list_my_rooms_uses_get_mine_with_pagination(self) -> None:
        async def scenario() -> None:
            calls: list[tuple[str, str, object]] = []
            client = ApiClient("http://unit-test")

            async def fake_request(method: str, path: str, **kwargs):
                calls.append((method, path, kwargs.get("params")))
                return {
                    "code": 200,
                    "data": {
                        "items": [
                            {"id": "a", "code": "AAAAA", "name": "A", "role": "owner"},
                            {"id": "b", "code": "BBBBB", "name": "B", "role": "member"},
                        ],
                        "has_more": False,
                        "next_before": None,
                    },
                }

            client._request = fake_request  # type: ignore[method-assign]
            page = await client.list_my_rooms(page=2, page_size=10)
            self.assertEqual(
                [("GET", protocol.API_V1_MY_ROOMS, {"page": 2, "page_size": 10})], calls
            )
            self.assertEqual(["a", "b"], [item.id for item in page.items])
            self.assertTrue(page.items[0].is_owner)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
