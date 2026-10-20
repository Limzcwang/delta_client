"""E3b1 HUD profile/ROI 缩放/JSON 测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.hud_profile import (
    DEFAULT_AVATAR_ROI,
    DEFAULT_SELF_AVATAR_ROI,
    DEFAULT_SKILL_BAR,
    HudProfile,
    Roi,
)


class RoiTests(unittest.TestCase):
    def test_from_quad_and_clamp(self) -> None:
        roi = Roi.from_quad((100, 80), (20, 30))
        self.assertEqual((20, 30, 80, 50), roi.as_tuple())
        self.assertEqual((0, 0, 10, 10), Roi(-5, -5, 10, 10).clamp(100, 100).as_tuple())
        self.assertEqual((95, 95, 5, 5), Roi(95, 95, 20, 20).clamp(100, 100).as_tuple())


class HudProfileTests(unittest.TestCase):
    def test_default_profile_and_slots(self) -> None:
        profile = HudProfile()
        self.assertEqual(3, len(profile.slot_rois()))
        self.assertEqual(DEFAULT_SKILL_BAR, profile.skill_bar.as_tuple())
        self.assertEqual(DEFAULT_AVATAR_ROI, profile.avatar_roi.as_tuple())
        self.assertEqual(DEFAULT_SELF_AVATAR_ROI, profile.self_avatar_roi.as_tuple())
        self.assertEqual("charged", profile.ult_pct_meaning)
        slots = profile.slot_rois()
        self.assertEqual(slots[0].x, profile.skill_bar.x)
        self.assertAlmostEqual(slots[0].width, slots[1].width, delta=1)
        self.assertEqual(slots[-1].right, profile.skill_bar.right)

    def test_scale_to_720p(self) -> None:
        profile = HudProfile()
        scaled = profile.scaled(1280, 720)
        self.assertEqual((1280, 720), (scaled.client_width, scaled.client_height))
        self.assertEqual((961, 631), (scaled.skill_bar.x, scaled.skill_bar.y))
        self.assertEqual((126, 42), (scaled.skill_bar.width, scaled.skill_bar.height))
        self.assertEqual((20, 642), (scaled.avatar_roi.x, scaled.avatar_roi.y))
        self.assertEqual((18, 640), (scaled.self_avatar_roi.x, scaled.self_avatar_roi.y))
        self.assertEqual(3, len(scaled.slot_rois()))

    def test_split_skill_bar_with_gap(self) -> None:
        rois = HudProfile.split_skill_bar(Roi(100, 200, 302, 100), gap=1)
        self.assertEqual([100, 201, 302], [roi.x for roi in rois])
        self.assertEqual([100, 100, 100], [roi.width for roi in rois])

    def test_json_roundtrip_and_export_import(self) -> None:
        profile = HudProfile(name="test", slots=[Roi(1, 2, 3, 4), Roi(5, 6, 7, 8), Roi(9, 10, 11, 12)])
        profile.ult_pct_meaning = "remaining"
        profile.mask_dark_threshold = 90
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            profile.save(path)
            loaded = HudProfile.load(path)
            self.assertEqual("test", loaded.name)
            self.assertEqual("remaining", loaded.ult_pct_meaning)
            self.assertEqual(90, loaded.mask_dark_threshold)
            self.assertEqual(profile.slot_rois(), loaded.slot_rois())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(3, len(data["slots"]))
            self.assertIn("self_avatar_roi", data)

    def test_bad_json_and_invalid_meaning(self) -> None:
        profile = HudProfile.from_dict({"ult_pct_meaning": "wat", "skill_bar": None})
        self.assertEqual("charged", profile.ult_pct_meaning)
        self.assertEqual(DEFAULT_SKILL_BAR, profile.skill_bar.as_tuple())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{no", encoding="utf-8")
            self.assertEqual(HudProfile(), HudProfile.load(path))


if __name__ == "__main__":
    unittest.main()


