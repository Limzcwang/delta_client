"""E3b1 采集层测试（fake source；不依赖真实游戏窗口）。"""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import dataclass

from capture.sources import CaptureWorker, Frame, open_source
from capture.window import find_window_by_process


@dataclass
class _FakeWindow:
    is_minimized: bool = False


class _FakeSource:
    def __init__(self) -> None:
        self.window = _FakeWindow()
        self.closed = False
        self.count = 0

    def grab(self):
        self.count += 1
        return Frame(image=[[[0, 0, 0]]], timestamp=time.time(), source="fake")

    def close(self) -> None:
        self.closed = True


class CaptureTests(unittest.TestCase):
    def test_find_missing_window_returns_none(self) -> None:
        self.assertIsNone(find_window_by_process("definitely-not-running.exe"))

    def test_open_source_no_window(self) -> None:
        source, message = open_source(process_name="definitely-not-running.exe")
        self.assertIsNone(source)
        self.assertIn("未找到", message)

    def test_worker_captures_and_stops(self) -> None:
        source = _FakeSource()
        frames: list[Frame] = []
        event = threading.Event()

        def on_frame(frame: Frame) -> None:
            frames.append(frame)
            event.set()

        worker = CaptureWorker(source, on_frame, fps=20)
        worker.start()
        self.assertTrue(event.wait(2.0))
        worker.stop()
        self.assertGreaterEqual(len(frames), 1)
        self.assertGreaterEqual(source.count, 1)
        self.assertFalse(worker._thread is not None and worker._thread.is_alive())

    def test_worker_pauses_when_minimized(self) -> None:
        source = _FakeSource()
        source.window.is_minimized = True
        frames: list[Frame] = []
        worker = CaptureWorker(source, frames.append, fps=20)
        worker.start()
        time.sleep(0.15)
        worker.stop()
        self.assertEqual([], frames)


if __name__ == "__main__":
    unittest.main()
