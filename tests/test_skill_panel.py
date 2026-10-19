"""E2 技能面板渲染/开关/倒计时测试（PySide6，离屏；无 PySide6 跳过）。"""

from __future__ import annotations

import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # pragma: no cover - 环境相关
    from PySide6.QtWidgets import QApplication

    from core.skills import SKILL_UNKNOWN, SLOT_ABILITY, SLOT_THROWABLE, SLOT_ULTIMATE, SkillState
    from ui.skill_panel import SkillPanel

    HAS_QT = True
except Exception:  # noqa: BLE001
    HAS_QT = False


def state(user_id="2", **skills):
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
            "operator": "红狼",
            "captured_at": int(time.time() * 1000),
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

    def _panel(self) -> SkillPanel:
        panel = SkillPanel()
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


if __name__ == "__main__":
    unittest.main()

