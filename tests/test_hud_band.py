"""充能技能灰带比例：面积/remaining/回退。"""

from __future__ import annotations

import unittest

from core.hud_band import charge_remaining_ms, measure_band_ratio
from core.hud_brightness import recognize_frame_brightness
from core.hud_profile import HudProfile, Roi
from core.operators import Operator, OperatorSkill

try:
    import numpy as np

    HAS_NUMPY = True
except Exception:  # noqa: BLE001
    HAS_NUMPY = False


class _Ocr:
    def __init__(self):
        self.calls = 0

    def read_lines(self, _image):
        from types import SimpleNamespace

        self.calls += 1
        if self.calls == 2:
            return [SimpleNamespace(text="1", score=0.95)]
        return []


@unittest.skipUnless(HAS_NUMPY, "numpy 未安装")
class BandTests(unittest.TestCase):
    def test_band_area_and_remaining(self) -> None:
        ready = np.full((84, 84, 3), 200, dtype=np.uint8)
        current = ready.copy()
        current[42:, :] = 50
        band = measure_band_ratio(current, ready)
        self.assertIsNotNone(band)
        self.assertGreater(band.area_ratio, 0.4)
        self.assertLess(band.area_ratio, 0.6)
        remaining = charge_remaining_ms(band, total_cd_ms=20_000, max_charges=2)
        self.assertGreater(remaining, 4_000)
        self.assertLess(remaining, 6_000)

    def test_charge_band_path_uses_template(self) -> None:
        profile = HudProfile(
            client_width=400,
            client_height=200,
            slots=[Roi(0, 0, 84, 84).to_dict(), Roi(100, 0, 84, 84).to_dict(), Roi(200, 0, 84, 84).to_dict()],
            text_row=Roi(0, 150, 300, 40),
        )
        frame = np.full((200, 400, 3), 200, dtype=np.uint8)
        frame[42:84, 100:184, :] = 50
        operator = Operator(
            id="honglang",
            name="红狼",
            skills={0: OperatorSkill(0, "大", 90_000, 1), 1: OperatorSkill(1, "三连手炮", 20_000, 2), 2: OperatorSkill(2, "投", 20_000, 1)},
        )
        ready_template = np.full((84, 84, 3), 200, dtype=np.uint8)
        result = recognize_frame_brightness(
            frame, profile, operator=operator, ocr=_Ocr(), server_now=1000,
            templates={1: ready_template},
        )
        self.assertEqual("charging", result.slots["ability"].state)
        self.assertGreater(result.slots["ability"].remaining_ms, 0)
        self.assertLessEqual(result.slots["ability"].remaining_ms, 10_000)
        self.assertGreater(result.diagnostics[1].band_ratio, 0.4)

    def test_no_template_falls_back(self) -> None:
        profile = HudProfile(
            client_width=400,
            client_height=200,
            slots=[Roi(0, 0, 84, 84).to_dict(), Roi(100, 0, 84, 84).to_dict(), Roi(200, 0, 84, 84).to_dict()],
            text_row=Roi(0, 150, 300, 40),
        )
        frame = np.full((200, 400, 3), 50, dtype=np.uint8)
        operator = Operator(id="x", name="x", skills={1: OperatorSkill(1, "技", 20_000, 2)})
        result = recognize_frame_brightness(
            frame, profile, operator=operator, ocr=_Ocr(), server_now=1000, templates={}
        )
        self.assertNotEqual("unknown", result.slots["ability"].state)


if __name__ == "__main__":
    unittest.main()

