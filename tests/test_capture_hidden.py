"""隐藏客户端窗口后抓帧 helper：顺序与异常恢复。"""

from __future__ import annotations

import unittest

from ui.capture_utils import grab_frame_hidden


class _Window:
    def __init__(self, visible=True, active=True):
        self.visible = visible
        self.active = active
        self.events = []

    def isVisible(self):
        return self.visible

    def isActiveWindow(self):
        return self.active

    def hide(self):
        self.events.append("hide")
        self.visible = False

    def show(self):
        self.events.append("show")
        self.visible = True

    def raise_(self):
        self.events.append("raise")


class _Widget:
    def __init__(self, window):
        self._window = window

    def window(self):
        return self._window


class _Source:
    def __init__(self, error=None):
        self.events = []
        self.error = error

    def grab(self):
        self.events.append("grab")
        if self.error:
            raise self.error
        return "frame"


class HiddenGrabTests(unittest.TestCase):
    def test_hide_grab_show_order(self) -> None:
        def process():
            calls.append("process")

        calls: list[str] = []
        source = _Source()
        window = _Window()
        original_grab = source.grab

        def grab():
            calls.append("grab")
            return original_grab()

        source.grab = grab
        frame = grab_frame_hidden(
            _Widget(window),
            source,
            delay=0.2,
            sleep=lambda delay: calls.append(f"sleep:{delay}"),
            process_events=process,
        )
        self.assertEqual("frame", frame)
        self.assertEqual(
            ["process", "sleep:0.2", "process", "grab", "process"],
            calls,
        )
        self.assertEqual(["hide", "show", "raise"], window.events)
        self.assertTrue(window.visible)

    def test_exception_restores_visibility(self) -> None:
        window = _Window()
        source = _Source(error=RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            grab_frame_hidden(_Widget(window), source, delay=0, sleep=lambda _d: None, process_events=lambda: None)
        self.assertTrue(window.visible)
        self.assertIn("show", window.events)

    def test_hidden_widget_not_shown(self) -> None:
        window = _Window(visible=False)
        source = _Source()
        grab_frame_hidden(_Widget(window), source, delay=0, sleep=lambda _d: None, process_events=lambda: None)
        self.assertNotIn("hide", window.events)
        self.assertNotIn("show", window.events)

    def test_only_if_active_skips_inactive(self) -> None:
        window = _Window(active=False)
        source = _Source()
        grab_frame_hidden(
            _Widget(window),
            source,
            delay=0,
            only_if_active=True,
            sleep=lambda _d: None,
            process_events=lambda: None,
        )
        self.assertNotIn("hide", window.events)
        self.assertIn("grab", source.events)


if __name__ == "__main__":
    unittest.main()
