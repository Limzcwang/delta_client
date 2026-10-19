"""P1：数据目录/旧版迁移/日志轮转与脱敏测试。"""

from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from state import paths
from state.logging_setup import (
    SensitiveFilter,
    redact_sensitive,
    setup_logging,
    shutdown_logging,
)


class DataPathTests(unittest.TestCase):
    def test_appdata_and_env_override(self) -> None:
        with patch.dict(os.environ, {"APPDATA": r"C:\Users\x\AppData\Roaming"}, clear=False):
            os.environ.pop(paths.DATA_DIR_ENV, None)
            self.assertEqual(
                Path(r"C:\Users\x\AppData\Roaming\DeltaClient"), paths.app_data_dir()
            )
            self.assertEqual("config.json", paths.config_path().name)
            self.assertEqual("session.json", paths.session_path().name)
            self.assertEqual("saved_logins.json", paths.saved_logins_path().name)
            self.assertEqual("client.log", paths.log_path().name)
            self.assertEqual("logs", paths.log_path().parent.name)
        with patch.dict(os.environ, {paths.DATA_DIR_ENV: r"C:\portable\data"}, clear=False):
            self.assertEqual(Path(r"C:\portable\data"), paths.app_data_dir())
        with patch.dict(os.environ, {paths.LOG_ENV: r"C:\tmp\x.log"}, clear=False):
            self.assertEqual(Path(r"C:\tmp\x.log"), paths.log_path())


class MigrationTests(unittest.TestCase):
    def test_migrates_legacy_config_and_session_with_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_config = root / ".delta_client.json"
            old_session = root / ".delta_client_session.json"
            old_config.write_text('{"server_url":"http://x"}', encoding="utf-8")
            old_session.write_text('{"token":"t"}', encoding="utf-8")
            new_dir = root / "data"
            with patch.object(paths, "legacy_config_path", return_value=old_config):
                with patch.object(paths, "legacy_session_path", return_value=old_session):
                    with patch.dict(os.environ, {paths.DATA_DIR_ENV: str(new_dir)}, clear=False):
                        migrated = paths.migrate_legacy_data()
            self.assertEqual(2, len(migrated))
            self.assertEqual('{"server_url":"http://x"}', (new_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual('{"token":"t"}', (new_dir / "session.json").read_text(encoding="utf-8"))
            self.assertFalse(old_config.exists())
            self.assertFalse(old_session.exists())
            self.assertTrue(old_config.with_name(".delta_client.json.bak").is_file())
            self.assertTrue(old_session.with_name(".delta_client_session.json.bak").is_file())

    def test_existing_new_config_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / ".delta_client.json"
            new_dir = root / "data"
            new_dir.mkdir()
            (new_dir / "config.json").write_text('{"keep":true}', encoding="utf-8")
            old.write_text('{"old":true}', encoding="utf-8")
            with patch.object(paths, "legacy_config_path", return_value=old):
                with patch.object(paths, "legacy_session_path", return_value=root / "none"):
                    with patch.dict(os.environ, {paths.DATA_DIR_ENV: str(new_dir)}, clear=False):
                        paths.migrate_legacy_data()
            self.assertEqual('{"keep":true}', (new_dir / "config.json").read_text(encoding="utf-8"))
            self.assertTrue(old.exists())


class LoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        shutdown_logging()

    def test_redaction_filter(self) -> None:
        self.assertNotIn("VALUE123", redact_sensitive("token=VALUE123"))
        self.assertNotIn("VALUE123", redact_sensitive("password: VALUE123"))
        self.assertNotIn("VALUE123", redact_sensitive('{"access_token": "VALUE123"}'))
        record = logging.LogRecord(
            "x", logging.INFO, __file__, 1, "token=%s", ("VALUE123",), None
        )
        SensitiveFilter().filter(record)
        self.assertNotIn("VALUE123", record.getMessage())

    def test_rotating_file_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "client.log"
            setup_logging(target, max_bytes=300, backup_count=2)
            logger = logging.getLogger("delta-test")
            for index in range(40):
                logger.warning("password=VALUE%d token=VALUE%d", index, index)
            logging.shutdown()
            text = "".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in sorted(Path(tmp).glob("client.log*"))
            )
            self.assertIn("***", text)
            self.assertNotIn("VALUE", text)
            self.assertTrue(any(path.name.startswith("client.log.") for path in Path(tmp).glob("*")))


if __name__ == "__main__":
    unittest.main()
