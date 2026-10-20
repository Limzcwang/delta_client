"""编号数字对固定 ROI / 自动扫描匹配的鲁棒性。"""

from __future__ import annotations

import unittest
from pathlib import Path

from core.hud_profile import Roi
from core.operator_match import recognize_operator, recognize_operator_auto
from core.operators import load_operator_catalog

try:  # pragma: no cover
    import cv2
    import numpy as np

    HAS_CV = True
except Exception:  # noqa: BLE001
    HAS_CV = False


def _green_digit(frame, x=0, y=0, text="1"):
    cv2.putText(
        frame,
        text,
        (x + 2, y + 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 0),
        1,
        cv2.LINE_AA,
    )
    return frame


@unittest.skipUnless(HAS_CV, "opencv/numpy 未安装，跳过头像数字鲁棒性测试")
class NumberRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_operator_catalog()
        cls.operator = cls.catalog.get("honglang")
        cls.avatar = cv2.imread(str(cls.operator.avatar_path()))
        cls.h, cls.w = cls.avatar.shape[:2]

    def _frame(self) -> tuple[object, Roi]:
        frame = np.zeros((1440, 2560, 3), dtype=np.uint8)
        frame[1284 : 1284 + self.h, 40 : 40 + self.w] = self.avatar
        return frame, Roi(40, 1284, self.w, self.h)

    def test_fixed_roi_digit_scores_within_003(self) -> None:
        frame, roi = self._frame()
        _, base = recognize_operator(frame, roi, self.catalog)
        self.assertGreaterEqual(base, 0.80)
        for digit in ("1", "2", "3"):
            target = frame.copy()
            _green_digit(target[roi.y : roi.bottom, roi.x : roi.right], 2, 1, digit)
            target[roi.y : roi.bottom, roi.x : roi.right] = target[roi.y : roi.bottom, roi.x : roi.right]
            _id, score = recognize_operator(target, roi, self.catalog)
            self.assertLessEqual(abs(base - score), 0.03, f"digit {digit}: {base} vs {score}")

    def test_auto_digit_scores_within_003(self) -> None:
        fixture = Path(r"C:\Users\1\Documents\deepseek-harness\default-workspace\.tmp\gh\frame_person.png")
        if not fixture.is_file():
            self.skipTest("缺少真实红狼 fixture")
        frame = cv2.imread(str(fixture))
        if frame is None:
            self.skipTest("fixture 读取失败")
        self.h, self.w = self.avatar.shape[:2]
        frame = frame.copy()
        _id, base, _box, _top = recognize_operator_auto(frame, self.catalog)
        self.assertGreaterEqual(base, 0.70)
        for digit in ("1", "2", "3"):
            target = frame.copy()
            _green_digit(target[1284 : 1284 + self.h, 40 : 40 + self.w], 2, 1, digit)
            target[1284 : 1284 + self.h, 40 : 40 + self.w] = target[1284 : 1284 + self.h, 40 : 40 + self.w]
            _id, score, _box, _top = recognize_operator_auto(target, self.catalog)
            self.assertLessEqual(abs(base - score), 0.03, f"digit {digit}: {base} vs {score}")


if __name__ == "__main__":
    unittest.main()
