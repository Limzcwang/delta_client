"""HUD 诊断：每槽原因、调试导出、保留最近 10 次。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.hud_debug import HudDebugExporter
from core.hud_pipeline import RecognitionFrame, recognize_frame
from core.hud_profile import HudProfile, Roi
from core.hud_recognition import SlotRecognition
from core.operators import Operator, OperatorSkill


class _FakeOcr:
    def __init__(self, texts_by_call):
        self.texts_by_call = list(texts_by_call)
        self.calls = 0

    def read_lines(self, _image):
        texts = self.texts_by_call[self.calls] if self.calls < len(self.texts_by_call) else []
        self.calls += 1
        return [SimpleNamespace(text=text, score=0.95) for text in texts]


class DiagnosticsTests(unittest.TestCase):
    def _profile(self):
        return HudProfile(
            client_width=100,
            client_height=100,
            skill_bar=Roi(0, 0, 90, 20),
            avatar_roi=Roi(0, 80, 20, 20),
        )

    def _frame(self):
        return [[(200, 200, 200), (200, 200, 200)] * 20 for _ in range(100)]

    def _operator(self):
        skills = {
            0: OperatorSkill(slot=0, name="大", total_cd_ms=90_000, max_charges=1),
            1: OperatorSkill(slot=1, name="技", total_cd_ms=30_000, max_charges=2),
            2: OperatorSkill(slot=2, name="投", total_cd_ms=20_000, max_charges=2),
        }
        return Operator(id="op", name="干员", skills=skills)

    def test_per_slot_diagnostics_reasons(self) -> None:
        ocr = _FakeOcr([["50%"], [], ["1"]])
        result = recognize_frame(
            self._frame(), self._profile(), operator=self._operator(), ocr=ocr
        )
        self.assertEqual(3, len(result.diagnostics))
        ultimate = result.diagnostics[0]
        self.assertEqual(50, ultimate.parsed["percent"])
        self.assertEqual("charging", ultimate.state)
        self.assertEqual("ultimate", result.slots["ultimate"].slot)
        ability = result.diagnostics[1]
        self.assertEqual("unknown", ability.state)
        self.assertIn("未读到文本", ability.reason)
        throwable = result.diagnostics[2]
        self.assertEqual("unknown", throwable.state)
        self.assertIn("充能数", throwable.reason)
        self.assertIsInstance(throwable.roi, tuple)

    def test_ultimate_expanded_roi_recovers_percent(self) -> None:
        # 基础 3 槽无百分比；扩展 ROI 的后续 OCR 给出 50%
        ocr = _FakeOcr([[], [], [], ["50%"]])
        result = recognize_frame(
            self._frame(), self._profile(), operator=self._operator(), ocr=ocr
        )
        ultimate = result.diagnostics[0]
        self.assertEqual(50, ultimate.parsed["percent"])
        self.assertEqual("charging", ultimate.state)
        self.assertIsNotNone(ultimate.expanded_roi)

    def test_export_json_and_retention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exporter = HudDebugExporter(tmp, keep=10)
            frame = self._frame()
            recognized = RecognitionFrame(
                slots={0: SlotRecognition(0, "ready", percent=100.0)},
                diagnostics=[],
            )
            paths = []
            for _ in range(12):
                path = exporter.export(frame, self._profile(), recognized)
                self.assertIsNotNone(path)
                paths.append(path)
            dirs = [path for path in Path(tmp).iterdir() if path.is_dir()]
            self.assertEqual(10, len(dirs))
            result = json.loads((sorted(dirs)[-1] / "result.json").read_text(encoding="utf-8"))
            self.assertIn("profile", result)
            self.assertIn("diagnostics", result)
            self.assertIn("payload", result)


if __name__ == "__main__":
    unittest.main()




