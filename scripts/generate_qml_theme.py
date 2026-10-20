"""从 ui.theme.TOKENS / UI_METRICS 生成 QML Theme 单例，避免双份色值。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.theme import TOKENS, UI_METRICS  # noqa: E402


def qml_source() -> str:
    lines = ["pragma Singleton", "import QtQuick", "", "QtObject {"]
    lines.append(f'    readonly property string fontFamily: "{UI_METRICS["fontFamily"]}"')
    lines.append("")
    for key, value in TOKENS.items():
        lines.append(f'    readonly property color {key}: "{value}"')
    color_key = {"amber": "amberHover", "green": "greenHover"}
    lines.append(f'    readonly property color amberHover: "{TOKENS["amber_hover"]}"')
    lines.append(f'    readonly property color greenHover: "{TOKENS["green_hover"]}"')
    lines.append(f'    readonly property color header: "{TOKENS["input"]}"')
    lines.append("")
    for key, value in UI_METRICS.items():
        if key == "fontFamily":
            continue
        lines.append(f"    readonly property int {key}: {int(value)}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    target = ROOT / "ui_qml" / "Theme.qml"
    target.write_text(qml_source(), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
