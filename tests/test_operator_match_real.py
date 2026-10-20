"""真实头像模板匹配：17 个内置模板自匹配。"""

from __future__ import annotations

import unittest

from core.hud_profile import DEFAULT_AVATAR_ROI, Roi
from core.operator_match import recognize_operator
from core.operators import load_operator_catalog

try:  # pragma: no cover
    import cv2
    import numpy as np

    HAS_CV = True
except Exception:  # noqa: BLE001
    HAS_CV = False


@unittest.skipUnless(HAS_CV, "opencv/numpy 未安装，跳过真实头像模板测试")
class RealAvatarMatchTests(unittest.TestCase):
    def test_all_17_builtin_avatars_self_match(self) -> None:
        catalog = load_operator_catalog()
        self.assertEqual(17, len(catalog))
        roi = Roi(*DEFAULT_AVATAR_ROI)
        matched = []
        for operator in catalog:
            path = operator.avatar_path()
            if not path.is_file():
                continue
            avatar = cv2.imread(str(path))
            if avatar is None:
                continue
            height, width = avatar.shape[:2]
            frame = np.zeros((max(1440, height + 10), max(2560, width + 10), 3), dtype=np.uint8)
            frame[5 : 5 + height, 5 : 5 + width] = avatar
            target_roi = Roi(5, 5, width, height)
            operator_id, score = recognize_operator(frame, target_roi, catalog, threshold=0.90)
            self.assertGreaterEqual(score, 0.90, operator.display_name)
            self.assertEqual(operator.id, operator_id, operator.display_name)
            matched.append(operator.id)
        self.assertEqual(17, len(matched))


if __name__ == "__main__":
    unittest.main()
