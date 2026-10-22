"""E2 技能面板渲染/开关/倒计时测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPixmap
    from PySide6.QtWidgets import QApplication

    from core.operators import OperatorCatalog, load_operator_catalog
    from core.skills import SKILL_UNKNOWN, SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState
    from ui.skill_panel import SkillPanel

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False

#: 固定服务器时间，禁止测试依赖真实 time.time()
CAPTURED_AT = 1_700_000_000_000


def state(user_id="2", operator_id="", operator="红狼", **skills):
    base = {
        "ultimate": {"state": "ready", "percent": 100},
        "ability": {
            "state": "charging",
            "charges": 1,
            "max_charges": 2,
            "remaining_ms": 30_000,
        },
        "throwable": {"state": "unknown"},
    }
    base.update(skills)
    return SkillState.from_ws(
        {
            "user_id": user_id,
            "nickname": f"队友{user_id}",
            "operator_id": operator_id,
            "operator": operator,
            "captured_at": CAPTURED_AT,
            "skills": base,
        }
    )


@unittest.skipUnless(HAS_QT, "PySide6 未安装，跳过 GUI 单测")
class SkillPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panels: list[SkillPanel] = []

    def tearDown(self) -> None:
        for panel in self.panels:
            panel.close()
            panel.deleteLater()
        self.app.processEvents()

    def _panel(self, clock=CAPTURED_AT, catalog=None) -> SkillPanel:
        clock_fn = clock if callable(clock) else (lambda: clock)
        panel = SkillPanel(clock=clock_fn, catalog=catalog)
        self.panels.append(panel)
        return panel

    def test_three_slots_states_and_countdown(self) -> None:
        panel = self._panel()
        panel.set_states([state()])
        self.assertEqual(1, len(panel._rows))
        row = panel._rows["2"]
        self.assertEqual("队友2", row.name_label.text())
        self.assertEqual("红狼", row.operator_label.text())
        self.assertEqual("fallback", row._avatar_source)
        self.assertEqual("", row.avatar.text())
        self.assertFalse(row.avatar.pixmap().isNull())
        ultimate = row.slot_widgets[SLOT_ULTIMATE]
        ability = row.slot_widgets[SLOT_ABILITY]
        throwable = row.slot_widgets[SLOT_THROWABLE]
        self.assertEqual(("大招", "100%", "就绪"), ultimate.text_lines())
        self.assertEqual(("技能", "1/2", "0:30"), ability.text_lines())
        self.assertEqual(("投掷物", "—", "未共享"), throwable.text_lines())

        row.update_state(state(), state().captured_at + 10_000, pulse=False)
        self.assertEqual(("技能", "1/2", "0:20"), ability.text_lines())

    def test_tick_uses_injected_clock_for_each_second(self) -> None:
        clock = [CAPTURED_AT]
        panel = self._panel(clock=lambda: clock[0])
        panel.set_states([state()])
        ability = panel._rows["2"].slot_widgets[SLOT_ABILITY]
        self.assertEqual("0:30", ability.text_lines()[2])
        clock[0] += 1_000
        panel._tick()
        self.assertEqual("0:29", ability.text_lines()[2])
        clock[0] += 5_000
        panel._tick()
        self.assertEqual("0:24", ability.text_lines()[2])

    def test_ready_at_absolute_countdown_and_past_ready(self) -> None:
        panel = self._panel()
        st = SkillState.from_ws(
            {
                "user_id": "2",
                "nickname": "队友2",
                "operator": "红狼",
                "captured_at": CAPTURED_AT - 10_000,
                "server_received_at": CAPTURED_AT,
                "skills": [
                    {"slot": 0, "state": "charging", "pct": 16, "ready_at": CAPTURED_AT + 5_000},
                    {"slot": 1, "state": "ready", "ready_at": CAPTURED_AT - 1},
                    {"slot": 2, "state": "unknown"},
                ],
            }
        )
        panel.set_states([st])
        row = panel._rows["2"]
        self.assertEqual("0:05", row.slot_widgets[SLOT_ULTIMATE].text_lines()[2])
        self.assertEqual("就绪", row.slot_widgets[SLOT_ABILITY].text_lines()[2])
        row.update_state(st, CAPTURED_AT + 6_000)
        self.assertEqual("就绪", row.slot_widgets[SLOT_ULTIMATE].text_lines()[2])

    def test_ready_vs_unshared_row_status(self) -> None:
        panel = self._panel()
        old = state()
        panel.set_states([old])
        row = panel._rows["2"]
        self.assertEqual("● 已共享", row.status_label.text())
        row.update_state(old, old.captured_at + 30 * 60 * 1000 + 1)
        self.assertEqual("未共享", row.status_label.text())

    def test_upsert_and_remove(self) -> None:
        panel = self._panel()
        panel.set_states([])
        self.assertEqual(0, len(panel.states()))
        self.assertTrue(panel.empty_label.isVisibleTo(panel))
        panel.upsert(state("2"))
        panel.upsert(state("3"))
        self.assertEqual(2, len(panel.states()))
        panel.upsert(state("2", ultimate={"state": "unknown"}))
        self.assertEqual(2, len(panel.states()))
        panel.remove("2")
        self.assertEqual(["3"], [item.user_id for item in panel.states()])
        panel.clear()
        self.assertEqual([], panel.states())

    def test_sharing_toggle_and_simulate_signal(self) -> None:
        panel = self._panel()
        events: list[bool] = []
        panel.sharing_toggled.connect(events.append)
        self.assertFalse(panel.sharing_enabled)
        panel.share_toggle_button.click()
        self.assertEqual([True], events)
        panel.set_sharing(False)
        self.assertFalse(panel.sharing_enabled)
        # 程序化 set_sharing 不应再次发信号
        self.assertEqual([True], events)

        simulated: list[bool] = []
        panel.simulate_requested.connect(lambda: simulated.append(True))
        panel.simulate_button.click()
        self.assertEqual([True], simulated)

    def test_operator_config_names_and_placeholder(self) -> None:
        # 自定义一个没有头像文件的干员，验证首字母占位与配置技能名
        catalog = OperatorCatalog.from_payload(
            {
                "operators": [
                    {
                        "id": "noavatar",
                        "name": "无头像干员",
                        "skills": [
                            {"slot": 0, "name": "配置大招", "total_cd_ms": 1000},
                            {"slot": 1, "name": "配置技能", "total_cd_ms": 1000},
                        ],
                    }
                ]
            }
        )
        panel = self._panel(catalog=catalog)
        panel.set_states([state(operator_id="noavatar", operator="无头像干员")])
        row = panel._rows["2"]
        self.assertEqual("无头像干员", row.operator_label.text())
        self.assertEqual("", row.avatar.text())
        self.assertEqual("fallback", row._avatar_source)
        self.assertFalse(row.avatar.pixmap().isNull())
        ultimate = row.slot_widgets[SLOT_ULTIMATE]
        ability = row.slot_widgets[SLOT_ABILITY]
        self.assertEqual("配置大招", ultimate.text_lines()[0])
        self.assertEqual("配置技能", ability.text_lines()[0])

    def test_unknown_cd_slot_has_no_ring_or_countdown(self) -> None:
        catalog = load_operator_catalog()
        panel = self._panel(catalog=catalog)
        panel.set_states(
            [
                state(
                    operator_id="wuming",
                    operator="无名",
                    throwable={"state": "ready", "charges": 2, "max_charges": 2},
                )
            ]
        )
        row = panel._rows["2"]
        throwable = row.slot_widgets[SLOT_THROWABLE]
        self.assertEqual(("闪光弹", "CD未知", "CD未知"), throwable.text_lines())
        self.assertFalse(throwable.cd_known)
        self.assertFalse(throwable.slot.percent)
        self.assertNotIn("0:", throwable.text_lines()[2])

    def test_operator_avatar_resolved_from_name(self) -> None:
        catalog = load_operator_catalog()
        panel = self._panel(catalog=catalog)
        panel.set_states([state(operator_id="", operator="红狼")])
        row = panel._rows["2"]
        self.assertEqual("operator", row._avatar_source)
        self.assertEqual("红狼", row.operator_label.text())

    def test_existing_avatar_file_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            avatar_path = Path(tmp) / "avatar.png"
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor("#FF00FF"))
            self.assertTrue(pixmap.save(str(avatar_path)))
            catalog = OperatorCatalog.from_payload(
                {
                    "operators": [
                        {
                            "id": "x",
                            "name": "测试干员",
                            "avatar": str(avatar_path),
                            "skills": [{"slot": 0, "name": "大招", "total_cd_ms": 1000}],
                        }
                    ]
                }
            )
            panel = self._panel(catalog=catalog)
            panel.set_states([state(operator_id="x", operator="测试干员")])
            row = panel._rows["2"]
            self.assertFalse(row.avatar.pixmap().isNull())
            self.assertEqual("测试干员", row.operator_label.text())

    def test_operator_avatar_path_and_cache(self) -> None:
        from core.operators import avatar_path_for, load_operator_catalog
        from ui.skill_panel import _AVATAR_CACHE, SkillRow

        self.assertTrue(avatar_path_for("honglang").is_file())
        _AVATAR_CACHE.clear()
        catalog = load_operator_catalog()
        panel = SkillPanel(catalog=catalog, clock=lambda: CAPTURED_AT)
        panel.set_states([state("2", operator_id="honglang", operator="红狼")])
        try:
            row = panel._rows["2"]
            self.assertEqual("operator", row._avatar_source)
            self.assertFalse(row.avatar.pixmap().isNull())
            self.assertIn("honglang", _AVATAR_CACHE)
            cached = _AVATAR_CACHE["honglang"]
            # 同一干员第二个成员直接命中缓存
            panel.upsert(state("3", operator_id="honglang", operator="红狼"))
            row3 = panel._rows["3"]
            self.assertEqual("operator", row3._avatar_source)
            self.assertIs(cached, _AVATAR_CACHE["honglang"])
            self.assertIsNotNone(row.avatar.pixmap())
        finally:
            panel.close()
            panel.deleteLater()

    def test_operator_avatar_fallback_and_refresh(self) -> None:
        from core.operators import load_operator_catalog
        from ui.skill_panel import _AVATAR_CACHE, _fallback_avatar

        _AVATAR_CACHE.clear()
        panel = SkillPanel(catalog=load_operator_catalog(), clock=lambda: CAPTURED_AT)
        panel.set_states([state("2", operator_id="", operator="不存在干员")])
        try:
            row = panel._rows["2"]
            self.assertEqual("fallback", row._avatar_source)
            self.assertFalse(row.avatar.pixmap().isNull())
            # 重新识别为蜂医后刷新头像
            panel.upsert(state("2", operator_id="fengyi", operator="蜂医"))
            self.assertEqual("operator", row._avatar_source)
            self.assertIn("fengyi", _AVATAR_CACHE)
            self.assertEqual("fengyi", row.operator_def.id)
            self.assertFalse(_fallback_avatar("队").isNull())
        finally:
            panel.close()
            panel.deleteLater()

    def test_slot_three_sections_do_not_overlap(self) -> None:
        panel = self._panel()
        panel.set_states([state()])
        slot = panel._rows["2"].slot_widgets[SLOT_ULTIMATE]
        slot.resize(120, 104)
        name, middle, bottom = slot.name_rect(), slot.middle_rect(), slot.bottom_rect()
        self.assertEqual(110, slot.height())
        self.assertFalse(name.intersects(middle))
        self.assertFalse(middle.intersects(bottom))
        self.assertLessEqual(name.bottom(), middle.top())
        self.assertGreaterEqual(bottom.top() - middle.bottom(), 8)
        self.assertLessEqual(bottom.bottom(), 108)

    def test_charge_uses_count_instead_of_ring(self) -> None:
        panel = self._panel()
        panel.set_states([state()])
        ability = panel._rows["2"].slot_widgets[SLOT_ABILITY]
        self.assertFalse(ability.kind == SLOT_ULTIMATE)
        self.assertEqual(("技能", "1/2", "0:30"), ability.text_lines())

    def test_long_skill_name_elides_with_full_tooltip(self) -> None:
        panel = self._panel()
        panel.set_states([state(ultimate={"state": "ready", "percent": 100})])
        slot = panel._rows["2"].slot_widgets[SLOT_ULTIMATE]
        slot.resize(80, 104)
        slot.set_data(slot.slot, slot.captured_at, slot.server_now, skill_name="非常非常非常长的大招名称")
        self.assertIn("非常非常非常长的大招名称", slot.toolTip())

    def test_squad_number_badge_show_hide_and_duplicates(self) -> None:
        from dataclasses import replace

        panel = self._panel()
        panel.set_states([
            replace(state("2"), squad_number=1),
            replace(state("3"), squad_number=1),
        ])
        try:
            rows = list(panel._rows.values())
            self.assertEqual("1", rows[0].squad_badge.text())
            self.assertTrue(rows[0].squad_badge.isVisibleTo(rows[0]))
            self.assertEqual("1", rows[1].squad_badge.text())
            self.assertTrue(rows[1].squad_badge.isVisibleTo(rows[1]))
            # 编号允许重复，不做去重/合并
            self.assertEqual(2, len(rows))
            panel.upsert(replace(state("2"), squad_number=None))
            self.assertFalse(rows[0].squad_badge.isVisibleTo(rows[0]))
        finally:
            panel.close()
            panel.deleteLater()

    def test_header_top_same_empty_and_with_cards(self) -> None:
        panel = self._panel()
        panel.resize(520, 520)
        panel.show()
        self.app.processEvents()
        empty_top = panel.header_widget.geometry().top()
        panel.set_states([state("2")])
        self.app.processEvents()
        self.assertEqual(empty_top, panel.header_widget.geometry().top())
        self.assertEqual(30, panel.header_widget.height())

    def test_multi_member_scroll_and_card_height(self) -> None:
        panel = self._panel()
        panel.resize(520, 520)
        panel.set_states([state("2"), state("3"), state("4")])
        panel.show()
        self.app.processEvents()
        self.assertEqual(Qt.ScrollBarPolicy.ScrollBarAsNeeded, panel.scroll.verticalScrollBarPolicy())
        self.assertEqual(10, panel.list_layout.spacing())
        for row in panel._rows.values():
            self.assertEqual(166, row.height())
        bar = panel.scroll.verticalScrollBar()
        self.assertTrue(bar.isVisible())
        self.assertEqual(8, bar.width())


if __name__ == "__main__":
    unittest.main()


