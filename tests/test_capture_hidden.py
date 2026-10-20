"""隐藏客户端窗口后抓帧 helper：顺序与异常恢复。"""

from __future__ import annotations

import unittest

from PySide6.QtCore import QRect

from ui.capture_utils import grab_frame_hidden, select_windows_to_hide


class _Window:
    def __init__(self, visible=True, active=True, geometry=(0, 0, 100, 100)):
        self.visible = visible
        self.active = active
        self.events = []
        self._geometry = QRect(*geometry)

    def isVisible(self):
        return self.visible

    def isActiveWindow(self):
        return self.active

    def frameGeometry(self):
        return self._geometry

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

    def test_only_intersecting_windows_hidden(self) -> None:
        intersecting = _Window(geometry=(10, 10, 100, 100))
        secondary = _Window(geometry=(2000, 0, 800, 600))
        source = _Source()
        grab_frame_hidden(
            _Widget(intersecting),
            source,
            game_rect=QRect(0, 0, 1920, 1080),
            windows=[intersecting, secondary],
            delay=0,
            sleep=lambda _d: None,
            process_events=lambda: None,
        )
        self.assertEqual(["hide", "show", "raise"], intersecting.events)
        self.assertEqual([], secondary.events)
        self.assertTrue(secondary.visible)

    def test_no_intersection_does_not_hide(self) -> None:
        secondary = _Window(geometry=(2000, 0, 800, 600))
        source = _Source()
        grab_frame_hidden(
            _Widget(secondary),
            source,
            game_rect=QRect(0, 0, 1920, 1080),
            windows=[secondary],
            delay=0,
            sleep=lambda _d: None,
            process_events=lambda: None,
        )
        self.assertEqual([], secondary.events)
        self.assertEqual(["grab"], source.events)
        self.assertTrue(secondary.visible)

    def test_select_windows_to_hide(self) -> None:
        a = _Window(geometry=(0, 0, 10, 10))
        b = _Window(geometry=(500, 500, 10, 10))
        c = _Window(visible=False, geometry=(0, 0, 10, 10))
        self.assertEqual([a], select_windows_to_hide([a, b, c], QRect(0, 0, 100, 100)))

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

    def test_excludes_overlay_and_pauses_resumes(self) -> None:
        window = _Window(geometry=(0, 0, 100, 100))
        overlay = _Window(geometry=(0, 0, 100, 100))
        self.assertEqual(
            [window], select_windows_to_hide([window, overlay], QRect(0, 0, 100, 100), exclude=[overlay])
        )
        pauses: list[str] = []
        resumes: list[str] = []
        source = _Source()
        grab_frame_hidden(
            _Widget(window),
            source,
            windows=[window, overlay],
            game_rect=QRect(0, 0, 100, 100),
            exclude=[overlay],
            pause_overlay=lambda: pauses.append("pause"),
            resume_overlay=lambda: resumes.append("resume"),
            resume_delay_ms=0,
            delay=0,
            sleep=lambda _d: None,
            process_events=lambda: None,
        )
        self.assertEqual(["pause"], pauses)
        self.assertEqual(["resume"], resumes)
        self.assertEqual(["hide", "show", "raise"], window.events)
        self.assertEqual([], overlay.events)  # overlay 不被 hide/show

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
