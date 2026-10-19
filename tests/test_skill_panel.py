"""E2 技能面板渲染/开关/倒计时测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
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
        self.assertEqual("队", row.avatar.text())
        ultimate = row.slot_widgets[SLOT_ULTIMATE]
        ability = row.slot_widgets[SLOT_ABILITY]
        throwable = row.slot_widgets[SLOT_THROWABLE]
        self.assertEqual(("大招", "100%", "就绪"), ultimate.text_lines())
        self.assertEqual(("技能", "1/2", "0:30"), ability.text_lines())
        self.assertEqual(("投掷物", "?", "未共享"), throwable.text_lines())

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

    def test_ready_vs_unshared_row_status(self) -> None:
        panel = self._panel()
        old = state()
        panel.set_states([old])
        row = panel._rows["2"]
        self.assertEqual("已共享", row.status_label.text())
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
        panel.share_check.setChecked(True)
        self.assertEqual([True], events)
        panel.set_sharing(False)
        self.assertFalse(panel.sharing_enabled)
        # 程序化 set_sharing 不应再次发信号
        self.assertEqual([True], events)

        simulated: list[bool] = []
        panel.simulate_requested.connect(lambda: simulated.append(True))
        panel.simulate_button.click()
        self.assertEqual([True], simulated)

    def test_operator_config_names_and_missing_avatar_placeholder(self) -> None:
        catalog = load_operator_catalog()
        panel = self._panel(catalog=catalog)
        panel.set_states([state(operator_id="honglang", operator="红狼")])
        row = panel._rows["2"]
        self.assertEqual("红狼", row.operator_label.text())
        self.assertEqual("队", row.avatar.text())
        self.assertTrue(row.avatar.pixmap().isNull())
        ultimate = row.slot_widgets[SLOT_ULTIMATE]
        ability = row.slot_widgets[SLOT_ABILITY]
        self.assertEqual("动力外骨骼", ultimate.text_lines()[0])
        self.assertEqual("三联装手炮", ability.text_lines()[0])

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


if __name__ == "__main__":
    unittest.main()

