"""E3a：干员配置（assets/operators.json）解析与查询（纯逻辑）。"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

OPERATORS_ENV = "DELTA_OPERATORS_JSON"
OPERATORS_RELATIVE = Path("assets") / "operators.json"
AVATAR_RELATIVE = Path("assets") / "operators"
SLOT_NAMES = {0: "大招", 1: "战术技能", 2: "投掷物"}


def operators_asset_path() -> Path:
    """配置路径：环境变量优先；PyInstaller 下取 ``_MEIPASS/assets``。"""
    override = str(os.environ.get(OPERATORS_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / OPERATORS_RELATIVE


def avatar_path_for(operator_id: str, avatar: str = "") -> Path:
    """头像路径：配置里的 avatar 优先，缺省 assets/operators/<id>.png。"""
    if avatar:
        path = Path(avatar)
        if path.is_absolute():
            return path
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / path
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / AVATAR_RELATIVE / f"{operator_id}.png"


@dataclass(frozen=True)
class OperatorSkill:
    slot: int = 0
    name: str = ""
    total_cd_ms: int | None = None
    max_charges: int = 0
    charge_cd_ms: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @property
    def slot_name(self) -> str:
        return SLOT_NAMES.get(self.slot, f"槽位{self.slot}")

    @property
    def effective_charge_cd_ms(self) -> int:
        if self.charge_cd_ms is not None and self.charge_cd_ms > 0:
            return int(self.charge_cd_ms)
        if self.total_cd_ms and self.max_charges > 0:
            return max(1, int(self.total_cd_ms / self.max_charges))
        return 0

    @property
    def cd_known(self) -> bool:
        return self.total_cd_ms is not None and self.total_cd_ms > 0

    @classmethod
    def from_api(cls, payload: Any, index: int = 0) -> "OperatorSkill":
        if not isinstance(payload, Mapping):
            return cls(slot=index, name="")
        slot = payload.get("slot", index)
        try:
            slot = int(slot)
        except (TypeError, ValueError):
            slot = index
        if slot not in SLOT_NAMES:
            slot = index
        total_cd = payload.get("total_cd_ms")
        try:
            total_cd = int(total_cd) if total_cd is not None else None
        except (TypeError, ValueError):
            total_cd = None
        if total_cd is not None and total_cd <= 0:
            total_cd = None
        try:
            max_charges = max(1, int(payload.get("max_charges") or 1))
        except (TypeError, ValueError):
            max_charges = 1
        charge_cd = payload.get("charge_cd_ms")
        try:
            charge_cd = int(charge_cd) if charge_cd is not None else None
        except (TypeError, ValueError):
            charge_cd = None
        if charge_cd is not None and charge_cd <= 0:
            charge_cd = None
        return cls(
            slot=slot,
            name=str(payload.get("name") or ""),
            total_cd_ms=total_cd,
            max_charges=max_charges,
            charge_cd_ms=charge_cd,
            raw=dict(payload),
        )


@dataclass(frozen=True)
class Operator:
    id: str = ""
    name: str = ""
    avatar: str = ""
    skills: Mapping[int, OperatorSkill] = field(default_factory=dict)

    def skill(self, slot: int) -> OperatorSkill | None:
        return self.skills.get(int(slot))

    def skill_name(self, slot: int) -> str:
        skill = self.skill(slot)
        return skill.name if skill else ""

    def cd_known(self, slot: int) -> bool:
        skill = self.skill(slot)
        return bool(skill and skill.cd_known)

    @property
    def display_name(self) -> str:
        return self.name or self.id or "未知干员"

    def avatar_path(self) -> Path:
        return avatar_path_for(self.id, self.avatar)

    def avatar_available(self) -> bool:
        try:
            return self.avatar_path().is_file()
        except OSError:
            return False

    @classmethod
    def from_api(cls, payload: Any) -> "Operator":
        if not isinstance(payload, Mapping):
            return cls()
        operator_id = str(payload.get("id") or payload.get("operator_id") or "").strip()
        name = str(payload.get("name") or payload.get("operator_name") or operator_id)
        skills: dict[int, OperatorSkill] = {}
        raw_skills = payload.get("skills")
        if isinstance(raw_skills, list):
            for index, item in enumerate(raw_skills):
                skill = OperatorSkill.from_api(item, index)
                skills[skill.slot] = skill
        elif isinstance(raw_skills, Mapping):
            for index, (key, item) in enumerate(raw_skills.items()):
                try:
                    slot = int(key)
                except (TypeError, ValueError):
                    slot = index
                skill = OperatorSkill.from_api(item, slot)
                skills[skill.slot] = skill
        return cls(
            id=operator_id,
            name=name,
            avatar=str(payload.get("avatar") or ""),
            skills=skills,
        )


@dataclass(frozen=True)
class OperatorCatalog:
    operators: tuple[Operator, ...] = ()

    def __len__(self) -> int:
        return len(self.operators)

    def __iter__(self):
        return iter(self.operators)

    def get(self, operator_id: str) -> Operator | None:
        key = str(operator_id or "").strip()
        if not key:
            return None
        for operator in self.operators:
            if operator.id == key:
                return operator
        return None

    def by_name(self, name: str) -> Operator | None:
        key = str(name or "").strip()
        if not key:
            return None
        for operator in self.operators:
            if operator.name == key:
                return operator
        return None

    def resolve(self, operator_id: str = "", operator_name: str = "") -> Operator | None:
        return self.get(operator_id) or self.by_name(operator_name)

    def ids(self) -> list[str]:
        return [operator.id for operator in self.operators]

    @classmethod
    def from_payload(cls, payload: Any) -> "OperatorCatalog":
        if not isinstance(payload, Mapping):
            return cls()
        items = payload.get("operators")
        if not isinstance(items, list):
            return cls()
        operators = tuple(
            Operator.from_api(item) for item in items if isinstance(item, Mapping)
        )
        return cls(tuple(operator for operator in operators if operator.id))

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> "OperatorCatalog":
        target = Path(path).expanduser() if path is not None else operators_asset_path()
        try:
            with target.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return cls()
        return cls.from_payload(payload)


def load_operator_catalog(path: str | os.PathLike[str] | None = None) -> OperatorCatalog:
    return OperatorCatalog.load(path)
