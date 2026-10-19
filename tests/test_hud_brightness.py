"""亮度判定/状态跳变 ready_at/无图标路径。"""

from __future__ import annotations

import unittest
from pathlib import Path

from core.hud_brightness import SkillTransitionTracker, p90_brightness, recognize_frame_brightness
from core.hud_pipeline import recognize_frame, to_skill_state
from core.hud_profile import HudProfile, Roi
from core.operators import Operator, OperatorSkill
from core.skill_payload import serialize_skill_state, validate_payload

try:
    import numpy as np

    HAS_NUMPY = True
except Exception:  # noqa: BLE001
    HAS_NUMPY = False


try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None


class _Ocr:
    def __init__(self, texts):
        self.texts = texts

    def read_lines(self, _image):
        from types import SimpleNamespace

        return [SimpleNamespace(text=text, score=0.95) for text in self.texts.pop(0)]


def _operator():
    return Operator(
        id="honglang",
        name="红狼",
        skills={
            0: OperatorSkill(0, "大", 90_000, 1),
            1: OperatorSkill(1, "技", 30_000, 2),
            2: OperatorSkill(2, "投", 20_000, 1),
        },
    )


class BrightnessTests(unittest.TestCase):
    def test_p90_ready_vs_cooldown(self) -> None:
        if not HAS_NUMPY:
            self.skipTest("numpy 未安装")
        ready = np.full((50, 50, 3), 180, dtype=np.uint8)
        cooldown = np.full((50, 50, 3), 60, dtype=np.uint8)
        self.assertGreaterEqual(p90_brightness(ready)[0], 140)
        self.assertLess(p90_brightness(cooldown)[0], 140)
        self.assertEqual(0.0, p90_brightness(cooldown)[1])

    def test_transition_ready_at(self) -> None:
        tracker = SkillTransitionTracker()
        ready_at, remaining, transition = tracker.update(1, "ready", 30_000, 1_000)
        self.assertEqual(0, ready_at)
        self.assertEqual("", transition)
        ready_at, remaining, transition = tracker.update(1, "charging", 30_000, 2_000)
        self.assertEqual(32_000, ready_at)
        self.assertEqual(30_000, remaining)
        self.assertEqual("ready->charging", transition)
        ready_at, remaining, transition = tracker.update(1, "ready", 30_000, 32_100)
        self.assertEqual(0, ready_at)
        self.assertEqual(0, remaining)
        self.assertEqual("charging->ready", transition)

    def test_brightness_path_without_icons_and_ready_at_payload(self) -> None:
        if not HAS_NUMPY:
            self.skipTest("numpy 未安装")
        profile = HudProfile(
            client_width=2560,
            client_height=1440,
            slots=[Roi(0, 0, 84, 84).to_dict(), Roi(100, 0, 84, 84).to_dict(), Roi(200, 0, 84, 84).to_dict()],
        )
        frame = np.zeros((200, 400, 3), dtype=np.uint8)
        frame[0:84, 0:84] = 200
        frame[0:84, 100:184] = 60
        frame[0:84, 200:284] = 60
        ocr = _Ocr([["50%"], ["2"], []])
        tracker = SkillTransitionTracker()
        result = recognize_frame(
            frame, profile, operator=_operator(), ocr=ocr, tracker=tracker, server_now=1000
        )
        self.assertEqual("charging", result.slots["ultimate"].state)
        self.assertEqual(46_000, result.slots["ultimate"].ready_at)
        self.assertEqual("charging", result.slots["ability"].state)
        self.assertEqual(31_000, result.slots["ability"].ready_at)
        state = to_skill_state(result, user_id="1", nickname="我", captured_at=1000)
        self.assertEqual(46_000, state.slot("ultimate").ready_at)
        payload = serialize_skill_state(state)
        valid, reason = validate_payload(payload)
        self.assertTrue(valid, reason)
        self.assertEqual(46_000, payload[0]["ready_at"])
        self.assertNotIn("icon_score", result.diagnostics[0].reason)

    def test_real_frame_p90_brightness(self) -> None:
        if not HAS_NUMPY or cv2 is None:
            self.skipTest("opencv/numpy 未安装")
        path = Path(__file__).parent / "fixtures" / "hud" / "frame_person.png"
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        profile = HudProfile()
        slots = [(roi, p90_brightness(image[roi.y:roi.bottom, roi.x:roi.right])) for roi in profile.slot_rois()]
        self.assertEqual(3, len(slots))
        for _roi, (p90, ratio) in slots:
            self.assertGreaterEqual(p90, 140)
            self.assertGreaterEqual(ratio, 0.0)
        result = recognize_frame(
            image, profile, operator=_operator(), ocr=_Ocr([[], [], []]),
            tracker=SkillTransitionTracker(), server_now=1000,
        )
        self.assertEqual("ready", result.slots["ultimate"].state)
        self.assertEqual("ready", result.slots["ability"].state)
        self.assertEqual("ready", result.slots["throwable"].state)

    def test_ultimate_ready_when_bright(self) -> None:
        if not HAS_NUMPY:
            self.skipTest("numpy 未安装")
        profile = HudProfile(
            client_width=100,
            client_height=100,
            slots=[Roi(0, 0, 30, 30).to_dict(), Roi(35, 0, 30, 30).to_dict(), Roi(70, 0, 30, 30).to_dict()],
        )
        frame = np.full((100, 100, 3), 60, dtype=np.uint8)
        frame[0:30, 0:30] = 200
        result = recognize_frame(
            frame, profile, operator=_operator(), ocr=_Ocr([[], [], []]), tracker=SkillTransitionTracker(), server_now=1000
        )
        self.assertEqual("ready", result.slots["ultimate"].state)
        self.assertEqual(0, result.slots["ultimate"].ready_at)


if __name__ == "__main__":
    unittest.main()



