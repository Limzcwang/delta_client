"""E3b：HUD ROI 标定 profile、坐标缩放与 JSON 导入导出（纯逻辑）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CLIENT_SIZE = (2560, 1440)
DEFAULT_SKILL_BAR = (1922, 1262, 252, 84)
DEFAULT_AVATAR_ROI = (40, 1284, 78, 80)
DEFAULT_ULT_TOTAL_CD_MS = 90_000
SLOT_COUNT = 3
SLOT_MEANING = {0: "大招", 1: "战术技能", 2: "投掷物"}


@dataclass(frozen=True)
class Roi:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def scaled(self, source_size: tuple[int, int], target_size: tuple[int, int]) -> "Roi":
        sx = target_size[0] / max(1, source_size[0])
        sy = target_size[1] / max(1, source_size[1])
        return Roi(
            int(round(self.x * sx)),
            int(round(self.y * sy)),
            max(1, int(round(self.width * sx))),
            max(1, int(round(self.height * sy))),
        )

    def clamp(self, width: int, height: int) -> "Roi":
        x = max(0, min(int(self.x), max(0, width - 1)))
        y = max(0, min(int(self.y), max(0, height - 1)))
        w = max(1, min(int(self.width), width - x))
        h = max(1, min(int(self.height), height - y))
        return Roi(x, y, w, h)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Any) -> "Roi":
        if isinstance(data, (list, tuple)) and len(data) == 4:
            return cls(*(int(value) for value in data))  # type: ignore[arg-type]
        if isinstance(data, Mapping):
            return cls(
                int(data.get("x", 0)),
                int(data.get("y", 0)),
                int(data.get("width", 1)),
                int(data.get("height", 1)),
            )
        return cls(0, 0, 1, 1)

    @classmethod
    def from_quad(cls, start: tuple[int, int], end: tuple[int, int]) -> "Roi":
        x1, y1 = start
        x2, y2 = end
        return cls(min(x1, x2), min(y1, y2), max(1, abs(x2 - x1)), max(1, abs(y2 - y1)))


@dataclass
class HudProfile:
    """一套窗口客户区标定（默认 2560×1440，可随分辨率缩放）。"""

    name: str = "default-2560x1440"
    client_width: int = DEFAULT_CLIENT_SIZE[0]
    client_height: int = DEFAULT_CLIENT_SIZE[1]
    skill_bar: Roi = field(default_factory=lambda: Roi(*DEFAULT_SKILL_BAR))
    slots: list[Roi] | None = None
    avatar_roi: Roi = field(default_factory=lambda: Roi(*DEFAULT_AVATAR_ROI))
    ult_pct_meaning: str = "charged"
    ocr_threshold: float = 0.5
    template_threshold: float = 0.70
    skill_icon_threshold: float = 0.70
    brightness_threshold: int = 140
    mask_dark_threshold: int = 70
    #: 技能栏整体左右内缩比例（图标之间有缝隙时用于单槽微调）
    slot_gap: int = 0
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.slots is not None:
            self.slots = [Roi.from_dict(item) for item in self.slots]
        if self.ult_pct_meaning not in ("charged", "remaining"):
            self.ult_pct_meaning = "charged"

    def slot_rois(self) -> list[Roi]:
        if self.slots:
            return list(self.slots)
        return self.split_skill_bar(self.skill_bar, self.slot_gap)

    @staticmethod
    def split_skill_bar(bar: Roi, gap: int = 0) -> list[Roi]:
        total_gap = gap * (SLOT_COUNT - 1)
        width = max(1, (bar.width - total_gap) // SLOT_COUNT)
        rois = []
        for index in range(SLOT_COUNT):
            x = bar.x + index * (width + gap)
            rois.append(Roi(x, bar.y, width, bar.height))
        return rois

    def scaled(self, width: int, height: int) -> "HudProfile":
        source = (self.client_width, self.client_height)
        target = (max(1, int(width)), max(1, int(height)))
        return HudProfile(
            name=f"{self.name}@{target[0]}x{target[1]}",
            client_width=target[0],
            client_height=target[1],
            skill_bar=self.skill_bar.scaled(source, target).clamp(*target),
            slots=[roi.scaled(source, target).clamp(*target) for roi in self.slots] if self.slots else None,
            avatar_roi=self.avatar_roi.scaled(source, target).clamp(*target),
            ult_pct_meaning=self.ult_pct_meaning,
            ocr_threshold=self.ocr_threshold,
            template_threshold=self.template_threshold,
            skill_icon_threshold=self.skill_icon_threshold,
            brightness_threshold=self.brightness_threshold,
            mask_dark_threshold=self.mask_dark_threshold,
            slot_gap=self.slot_gap,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "client_width": self.client_width,
            "client_height": self.client_height,
            "skill_bar": self.skill_bar.to_dict(),
            "slots": [roi.to_dict() for roi in self.slots] if self.slots else None,
            "avatar_roi": self.avatar_roi.to_dict(),
            "ult_pct_meaning": self.ult_pct_meaning,
            "ocr_threshold": self.ocr_threshold,
            "template_threshold": self.template_threshold,
            "skill_icon_threshold": self.skill_icon_threshold,
            "brightness_threshold": self.brightness_threshold,
            "mask_dark_threshold": self.mask_dark_threshold,
            "slot_gap": self.slot_gap,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "HudProfile":
        if not isinstance(data, Mapping):
            return cls()
        slots = data.get("slots")
        return cls(
            name=str(data.get("name") or "default"),
            client_width=max(1, int(data.get("client_width", DEFAULT_CLIENT_SIZE[0]))),
            client_height=max(1, int(data.get("client_height", DEFAULT_CLIENT_SIZE[1]))),
            skill_bar=Roi.from_dict(data.get("skill_bar") or DEFAULT_SKILL_BAR),
            slots=[Roi.from_dict(item) for item in slots] if isinstance(slots, list) and slots else None,
            avatar_roi=Roi.from_dict(data.get("avatar_roi") or DEFAULT_AVATAR_ROI),
            ult_pct_meaning=str(data.get("ult_pct_meaning") or "charged"),
            ocr_threshold=float(data.get("ocr_threshold", 0.5)),
            template_threshold=float(data.get("template_threshold", 0.70)),
            skill_icon_threshold=float(data.get("skill_icon_threshold", 0.70)),
            brightness_threshold=int(data.get("brightness_threshold", 140)),
            mask_dark_threshold=int(data.get("mask_dark_threshold", 70)),
            slot_gap=int(data.get("slot_gap", 0) or 0),
            raw=dict(data),
        )

    @classmethod
    def load(cls, path: str | Path) -> "HudProfile":
        try:
            with Path(path).open("r", encoding="utf-8") as handle:
                return cls.from_dict(json.load(handle))
        except (OSError, ValueError):
            return cls()

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return target
