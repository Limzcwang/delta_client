"""配置中心：304/200 写入+热更新/缓存损坏回退/网络失败静默/结构校验。"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from core.operator_config import (
    OperatorConfigManager,
    OperatorConfigResponse,
    validate_payload,
)


def payload(version="v2", count=2, **extra):
    operators = [
        {
            "id": f"op{index}",
            "name": f"干员{index}",
            "skills": [{"slot": 0, "name": "大", "total_cd_ms": 90000}],
        }
        for index in range(count)
    ]
    result = {"version": version, "updated_at": "2026-10-20T00:00:00Z", "operators": operators}
    result.update(extra)
    return result


class FakeApi:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.etags = []

    async def get_operator_config(self, etag=""):
        self.etags.append(etag)
        if self.error:
            raise self.error
        return self.response


class ManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / "operators.json"
        self.builtin = self.root / "builtin.json"
        self.builtin.write_text(json.dumps(payload("builtin-v1", count=1)), encoding="utf-8")

    def _manager(self) -> OperatorConfigManager:
        return OperatorConfigManager(self.cache, self.builtin)

    def test_bootstrap_builtin(self) -> None:
        manager = self._manager()
        self.assertEqual("builtin", manager.state.version)
        self.assertEqual("内置", manager.state.source_label)
        self.assertEqual(1, len(manager.catalog))

    def test_200_writes_cache_and_hot_updates(self) -> None:
        manager = self._manager()
        self.assertTrue(manager.apply_server_payload(payload("v2", count=2), '"etag-v2"'))
        self.assertEqual("v2", manager.state.version)
        self.assertEqual(2, len(manager.catalog))
        self.assertEqual("服务器", manager.state.source_label)
        saved = json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertEqual("v2", saved["version"])
        self.assertEqual('"etag-v2"', saved["etag"])
        # 重新构造从缓存加载
        reloaded = self._manager()
        self.assertEqual("v2", reloaded.state.version)
        self.assertEqual(2, len(reloaded.catalog))
        self.assertEqual("本地缓存", reloaded.state.source_label)

    def test_304_uses_cache(self) -> None:
        manager = self._manager()
        manager.apply_server_payload(payload("v2", count=2), '"etag-v2"')
        kind, message = asyncio.run(manager.check_update(FakeApi(OperatorConfigResponse(304, None, '"etag-v2"'))))
        self.assertEqual("not_modified", kind)
        self.assertEqual("已是最新", message)
        self.assertEqual("v2", manager.state.version)

    def test_200_update_message(self) -> None:
        manager = self._manager()
        kind, message = asyncio.run(manager.check_update(FakeApi(OperatorConfigResponse(200, payload("v3"), '"e3"'))))
        self.assertEqual("updated", kind)
        self.assertIn("v3", message)
        self.assertEqual("v3", manager.state.version)

    def test_corrupt_cache_falls_back_builtin(self) -> None:
        self.cache.write_text("{bad", encoding="utf-8")
        manager = self._manager()
        self.assertEqual("builtin", manager.state.version)
        self.assertEqual(1, len(manager.catalog))
        self.cache.write_text(json.dumps({"version": "x", "operators": []}), encoding="utf-8")
        self.assertEqual("builtin", self._manager().state.version)

    def test_network_failure_silent(self) -> None:
        manager = self._manager()
        kind, message = asyncio.run(manager.check_update(FakeApi(error=RuntimeError("offline"))))
        self.assertEqual("error", kind)
        self.assertIn("网络失败", message)
        self.assertEqual("builtin", manager.state.version)
        self.assertEqual(1, len(manager.catalog))

    def test_invalid_payload_rejected(self) -> None:
        manager = self._manager()
        for bad in (
            {},
            {"version": "v", "operators": []},
            {"version": "v", "operators": [{"name": "x"}]},
            {"operators": [{"id": "x", "name": "x"}]},
        ):
            with self.subTest(bad=bad):
                valid, reason = validate_payload(bad)
                self.assertFalse(valid)
                self.assertFalse(manager.apply_server_payload(bad, "e"))
                self.assertEqual("builtin", manager.state.version)

    def test_unwraps_data_envelope(self) -> None:
        manager = self._manager()
        self.assertTrue(
            manager.apply_server_payload({"data": payload("v4", count=3)}, '"e4"')
        )
        self.assertEqual("v4", manager.state.version)
        self.assertEqual(3, len(manager.catalog))


class MockConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_200_then_304_then_new_version(self) -> None:
        from net.mock_backend import MockApiClient

        api = MockApiClient(latency=0)
        first = await api.get_operator_config()
        self.assertEqual(200, first.status)
        self.assertTrue(first.etag)
        self.assertGreater(len(first.payload["operators"]), 0)
        second = await api.get_operator_config(first.etag)
        self.assertEqual(304, second.status)
        api.operator_config_version = "mock-v2"
        third = await api.get_operator_config(first.etag)
        self.assertEqual(200, third.status)
        self.assertEqual("mock-v2", third.payload["version"])


if __name__ == "__main__":
    unittest.main()
