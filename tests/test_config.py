"""配置加载/规范化/落盘测试（离线，不依赖 GUI/网络）。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config import (
    DEFAULT_SERVER_URL,
    DEFAULT_TIMEOUT,
    AppConfig,
    ConfigError,
    config_path_from_env,
    load_config,
    normalize_server_url,
    normalize_ws_url,
    save_config,
)


class NormalizeUrlTests(unittest.TestCase):
    def test_server_url_gets_default_scheme(self) -> None:
        self.assertEqual(normalize_server_url("127.0.0.1:8000"), "http://127.0.0.1:8000")

    def test_server_url_strips_trailing_slash(self) -> None:
        self.assertEqual(normalize_server_url("http://example.com:8000/"), "http://example.com:8000")
        self.assertEqual(normalize_server_url("https://host/delta/"), "https://host/delta")

    def test_server_url_requires_http_scheme(self) -> None:
        with self.assertRaises(ConfigError):
            normalize_server_url("ftp://host")
        with self.assertRaises(ConfigError):
            normalize_server_url("")

    def test_server_url_rejects_missing_host(self) -> None:
        with self.assertRaises(ConfigError):
            normalize_server_url("http://")

    def test_ws_url_normalization(self) -> None:
        self.assertEqual(normalize_ws_url("localhost:8765"), "ws://localhost:8765")
        self.assertEqual(normalize_ws_url("https://host/ws"), "wss://host/ws")
        self.assertEqual(normalize_ws_url("wss://host/ws/"), "wss://host/ws")
        with self.assertRaises(ConfigError):
            normalize_ws_url("ftp://host")


class LoadConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_path = Path(self._tmp.name) / ".delta_client.json"

    def _write(self, payload: object) -> None:
        self.config_path.write_text(json.dumps(payload), encoding="utf-8")

    def test_defaults_when_no_file(self) -> None:
        cfg = load_config(path=self.config_path, env={})
        self.assertEqual(cfg.server_url, DEFAULT_SERVER_URL)
        self.assertEqual(cfg.request_timeout, DEFAULT_TIMEOUT)
        self.assertFalse(cfg.use_mock)
        self.assertFalse(cfg.persist_token)
        self.assertEqual(cfg.source, "default")
        self.assertEqual(cfg.effective_ws_url, "ws://127.0.0.1:8000/ws")

    def test_file_values_are_loaded(self) -> None:
        self._write(
            {
                "server_url": "http://file-host:9000",
                "ws_url": "ws://file-host:8766/ws",
                "mock": True,
                "save_token": True,
                "request_timeout": 20,
            }
        )
        cfg = load_config(path=self.config_path, env={})
        self.assertEqual(cfg.server_url, "http://file-host:9000")
        self.assertEqual(cfg.ws_url, "ws://file-host:8766/ws")
        self.assertTrue(cfg.use_mock)
        self.assertTrue(cfg.persist_token)
        self.assertEqual(cfg.request_timeout, 20.0)
        self.assertEqual(cfg.source, "file")

    def test_env_overrides_file(self) -> None:
        self._write({"server_url": "http://file-host:9000", "mock": True, "save_token": True})
        cfg = load_config(
            path=self.config_path,
            env={
                "DELTA_SERVER": "http://env-host:7000",
                "DELTA_WS": "ws://env-host:8766/ws",
                "DELTA_MOCK": "0",
                "DELTA_SAVE_TOKEN": "yes",
            },
        )
        self.assertEqual(cfg.server_url, "http://env-host:7000")
        self.assertEqual(cfg.ws_url, "ws://env-host:8766/ws")
        self.assertFalse(cfg.use_mock)
        self.assertTrue(cfg.persist_token)
        self.assertEqual(cfg.source, "env")

    def test_cli_overrides_env(self) -> None:
        cfg = load_config(
            path=self.config_path,
            env={"DELTA_SERVER": "http://env-host:7000", "DELTA_MOCK": "1"},
            server_override="https://cli-host",
            mock_override=False,
        )
        self.assertEqual(cfg.server_url, "https://cli-host")
        self.assertFalse(cfg.use_mock)
        self.assertEqual(cfg.source, "cli")

    def test_malformed_file_falls_back_to_defaults(self) -> None:
        self.config_path.write_text("{not json", encoding="utf-8")
        cfg = load_config(path=self.config_path, env={})
        self.assertEqual(cfg.server_url, DEFAULT_SERVER_URL)

    def test_invalid_file_server_raises_config_error(self) -> None:
        self._write({"server_url": "ftp://bad"})
        with self.assertRaises(ConfigError):
            load_config(path=self.config_path, env={})

    def test_invalid_timeout_ignored(self) -> None:
        self._write({"request_timeout": "oops"})
        cfg = load_config(path=self.config_path, env={})
        self.assertEqual(cfg.request_timeout, DEFAULT_TIMEOUT)

    def test_https_derives_wss(self) -> None:
        cfg = load_config(path=self.config_path, env={"DELTA_SERVER": "https://host/delta"})
        self.assertEqual(cfg.effective_ws_url, "wss://host/delta/ws")


class SaveConfigTests(unittest.TestCase):
    def test_roundtrip_and_no_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "config.json"
            cfg = AppConfig(
                server_url="http://host:1234",
                use_mock=True,
                persist_token=True,
                operator_id="honglang",
                request_timeout=9.0,
                source="cli",
            )
            saved = save_config(cfg, target)
            self.assertEqual(saved, target)
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["server_url"], "http://host:1234")
            self.assertTrue(data["mock"])
            self.assertTrue(data["save_token"])
            self.assertEqual("honglang", data["operator_id"])
            self.assertNotIn("token", data)
            self.assertNotIn("password", data)
            reloaded = load_config(path=target, env={})
            self.assertEqual(reloaded.server_url, "http://host:1234")
            self.assertTrue(reloaded.use_mock)
            self.assertTrue(reloaded.persist_token)
            self.assertEqual("honglang", reloaded.operator_id)
            self.assertEqual(reloaded.effective_ws_url, "ws://host:1234/ws")

    def test_config_path_env_override(self) -> None:
        path = config_path_from_env({"DELTA_CLIENT_CONFIG": "~/custom.json"})
        self.assertEqual(path, Path.home() / "custom.json")
        default = config_path_from_env({"APPDATA": str(Path.home() / "AppData/Roaming")})
        self.assertEqual(default.name, "config.json")
        self.assertEqual(default.parent.name, "DeltaClient")


if __name__ == "__main__":
    unittest.main()
