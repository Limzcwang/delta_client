"""E3a：干员配置解析/未知 CD/头像缺失容错测试。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.operators import (
    Operator,
    OperatorCatalog,
    OperatorSkill,
    load_operator_catalog,
    operators_asset_path,
)


class OperatorConfigTests(unittest.TestCase):
    def test_real_config_has_16_operators(self) -> None:
        catalog = load_operator_catalog()
        self.assertEqual(17, len(catalog))
        self.assertEqual(17, len(catalog.ids()))
        self.assertIsNotNone(catalog.get("honglang"))
        self.assertIsNotNone(catalog.by_name("红狼"))

    def test_slot_names_cd_and_charges(self) -> None:
        catalog = load_operator_catalog()
        honglang = catalog.get("honglang")
        self.assertEqual("红狼", honglang.name)
        self.assertEqual("动力外骨骼", honglang.skill_name(0))
        self.assertEqual(90_000, honglang.skill(0).total_cd_ms)
        self.assertEqual(1, honglang.skill(0).max_charges)
        self.assertEqual("三联装手炮", honglang.skill_name(1))
        self.assertEqual(70_000, honglang.skill(1).total_cd_ms)
        self.assertEqual(2, honglang.skill(1).max_charges)
        self.assertTrue(honglang.cd_known(1))

    def test_unknown_cd_slots(self) -> None:
        catalog = load_operator_catalog()
        expected = {
            "wuming": 2,
            "muyangren": 2,
            "wululu": 2,
            "bite": 0,
            "yinyi": 0,
        }
        for operator_id, slot in expected.items():
            with self.subTest(operator_id=operator_id):
                operator = catalog.get(operator_id)
                skill = operator.skill(slot)
                self.assertIsNotNone(skill)
                self.assertIsNone(skill.total_cd_ms)
                self.assertFalse(skill.cd_known)
        # 同干员的其它槽位仍正常
        self.assertTrue(catalog.get("wuming").cd_known(0))

    def test_all_operator_avatars_present(self) -> None:
        catalog = load_operator_catalog()
        self.assertEqual(17, len(catalog))
        for operator in catalog:
            with self.subTest(operator=operator.id):
                self.assertTrue(operator.avatar_available(), f"{operator.id} 头像缺失")
        # 不存在的干员仍应安全返回不可用
        missing = Operator(id="no-such-operator", name="无")
        self.assertFalse(missing.avatar_available())

    def test_missing_fields_tolerated(self) -> None:
        catalog = OperatorCatalog.from_payload(
            {
                "operators": [
                    {"id": "x", "name": "测试", "skills": [{"slot": 1, "name": "技能"}]},
                    {"id": "y"},
                    {"name": "无id"},
                    "bad",
                ]
            }
        )
        self.assertEqual(2, len(catalog))
        operator = catalog.get("x")
        self.assertIsNone(catalog.get("y").skill(0))
        self.assertEqual("技能", operator.skill_name(1))
        self.assertIsNone(operator.skill(1).total_cd_ms)
        self.assertFalse(operator.skill(1).cd_known)
        self.assertEqual("测试", operator.display_name)

    def test_load_missing_or_bad_json_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            self.assertEqual(0, len(OperatorCatalog.load(missing)))
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not-json", encoding="utf-8")
            self.assertEqual(0, len(OperatorCatalog.load(bad)))
            empty = Path(tmp) / "empty.json"
            empty.write_text(json.dumps({"operators": []}), encoding="utf-8")
            self.assertEqual(0, len(OperatorCatalog.load(empty)))

    def test_temp_config_parses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "operators.json"
            path.write_text(
                json.dumps(
                    {
                        "operators": [
                            {
                                "id": "abc",
                                "name": "甲",
                                "avatar": "avatars/abc.png",
                                "skills": [
                                    {"slot": 0, "name": "大", "total_cd_ms": 1000, "max_charges": 1},
                                    {"slot": 2, "name": "投", "total_cd_ms": 0, "max_charges": 2},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            catalog = load_operator_catalog(path)
            operator = catalog.get("abc")
            self.assertEqual("甲", operator.name)
            self.assertTrue(operator.avatar_path().name == "abc.png")
            self.assertTrue(operator.skill(0).cd_known)
            self.assertFalse(operator.skill(2).cd_known)
            self.assertEqual(2, operator.skill(2).max_charges)

    def test_asset_path_is_repo_assets(self) -> None:
        self.assertEqual("operators.json", operators_asset_path().name)


if __name__ == "__main__":
    unittest.main()

