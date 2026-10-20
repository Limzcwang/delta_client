"""P1：入口版本参数测试。"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

import main as entry


class VersionTests(unittest.TestCase):
    def test_version_flag_prints_app_version(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = entry.main(["--version"])
        self.assertEqual(0, code)
        self.assertIn("0.2.2", output.getvalue())


if __name__ == "__main__":
    unittest.main()


