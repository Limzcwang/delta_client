"""E3b1 采集层测试（fake source；不依赖真实游戏窗口）。"""

from __future__ import annotations

import threading
import time
import unittest
from dataclasses import dataclass

from capture.sources import CaptureWorker, Frame, open_source
from capture.window import (
    WindowCandidate,
    find_game_window,
    find_window_by_process,
    normalize_process_name,
)


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
        self.assertIsNone(find_game_window(candidates=[]).window)

    def test_open_source_no_window(self) -> None:
        source, message = open_source(
            process_name="definitely-not-running.exe",
            title_keyword="__no_such_window_title__",
        )
        self.assertIsNone(source)
        self.assertIn("未找到", message)


class WindowMatchingTests(unittest.TestCase):
    def test_normalize_process_ignores_exe_case_and_path(self) -> None:
        self.assertEqual(
            "deltaforceclient-win64-shipping",
            normalize_process_name(r"C:\Game\DeltaForceClient-Win64-Shipping.exe"),
        )
        self.assertEqual(
            normalize_process_name("DeltaForceClient-Win64-Shipping"),
            normalize_process_name("deltaforceclient-win64-shipping.EXE"),
        )

    def _candidate(self, **kwargs):
        values = {
            "hwnd": 1,
            "pid": 33220,
            "title": "三角洲行动",
            "process_name": "DeltaForceClient-Win64-Shipping.exe",
            "client_left": 0,
            "client_top": 0,
            "client_width": 2560,
            "client_height": 1440,
            "minimized": False,
        }
        values.update(kwargs)
        return WindowCandidate(**values)

    def test_process_match_with_exe(self) -> None:
        result = find_game_window(candidates=[self._candidate()])
        self.assertIsNotNone(result.window)
        self.assertEqual("process", result.match_method)
        self.assertEqual(33220, result.window.pid)

    def test_title_fallback_when_process_unavailable(self) -> None:
        result = find_game_window(
            candidates=[self._candidate(pid=9, title="Delta Force Client", process_name="")]
        )
        self.assertIsNotNone(result.window)
        self.assertEqual("title", result.match_method)

    def test_title_keyword_and_size_filter(self) -> None:
        small = self._candidate(title="三角洲行动", client_width=640, client_height=480)
        self.assertIsNone(find_game_window(candidates=[small]).window)
        tiny = self._candidate(client_width=100, client_height=100)
        self.assertIsNone(find_game_window(candidates=[tiny]).window)

    def test_own_client_window_not_matched_by_title(self) -> None:
        own = self._candidate(
            pid=44204,
            title="Delta Client - 三角洲行动队友房间",
            process_name="python.exe",
        )
        self.assertIsNone(find_game_window(candidates=[own]).window)
        # 真正的游戏窗口排在后面也必须优先按进程名命中，而不是先命中客户端标题
        game = self._candidate(pid=33220, hwnd=2)
        result = find_game_window(candidates=[own, game])
        self.assertEqual(33220, result.window.pid)
        self.assertEqual("process", result.match_method)

    def test_minimized_reason(self) -> None:
        result = find_game_window(candidates=[self._candidate(minimized=True)])
        self.assertIsNotNone(result.window)
        self.assertIn("最小化", result.reason)

    def test_no_candidate_reason(self) -> None:
        result = find_game_window(candidates=[])
        self.assertIsNone(result.window)
        self.assertIn("未找到", result.reason)

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

