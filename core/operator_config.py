"""干员配置中心客户端：内置 bootstrap / 本地缓存 / 服务端版本热更新。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from core.operators import OperatorCatalog, load_operator_catalog
from state.paths import app_data_dir


@dataclass(frozen=True)
class OperatorConfigResponse:
    status: int
    payload: Any = None
    etag: str = ""


@dataclass
class OperatorConfigState:
    catalog: OperatorCatalog = field(default_factory=lambda: load_operator_catalog())
    version: str = "builtin"
    etag: str = ""
    updated_at: str = ""
    source: str = "builtin"

    @property
    def source_label(self) -> str:
        return {"builtin": "内置", "cache": "本地缓存", "server": "服务器"}.get(self.source, self.source)


def default_cache_path() -> Path:
    return app_data_dir() / "operators.json"


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, Mapping) and "operators" not in payload:
        data = payload.get("data")
        if isinstance(data, Mapping):
            return data
    return payload


def validate_payload(payload: Any) -> tuple[bool, str]:
    """校验服务端/缓存结构；缺 version/operators 或 operator 缺 id 均拒绝。"""
    payload = _unwrap(payload)
    if not isinstance(payload, Mapping):
        return False, "配置必须是 JSON 对象"
    version = payload.get("version")
    if version is None or str(version).strip() == "":
        return False, "缺少 version"
    operators = payload.get("operators")
    if not isinstance(operators, list) or not operators:
        return False, "operators 必须是非空数组"
    for index, item in enumerate(operators):
        if not isinstance(item, Mapping):
            return False, f"operators[{index}] 必须是对象"
        if not str(item.get("id") or "").strip():
            return False, f"operators[{index}] 缺少 id"
        if not str(item.get("name") or "").strip():
            return False, f"operators[{index}] 缺少 name"
    catalog = OperatorCatalog.from_payload(payload)
    if len(catalog) == 0:
        return False, "operators 结构无效"
    return True, ""


def _write_cache(path: Path, payload: Mapping[str, Any], etag: str) -> bool:
    data = {
        "version": payload.get("version"),
        "etag": etag or payload.get("etag") or "",
        "updated_at": payload.get("updated_at") or "",
        "operators": payload.get("operators") or [],
        "meta": payload.get("meta") or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        import os

        os.replace(temp, path)
        return True
    except OSError:
        return False


class OperatorConfigManager:
    """内存中的唯一干员配置来源；所有面板/识别/上报都引用它的 catalog。"""

    def __init__(
        self,
        cache_path: str | Path | None = None,
        builtin_path: str | Path | None = None,
    ) -> None:
        self.cache_path = Path(cache_path).expanduser() if cache_path else default_cache_path()
        self.builtin_path = Path(builtin_path) if builtin_path else None
        self.state = OperatorConfigState()
        self.load_initial()

    def load_initial(self) -> None:
        if self._load_cache():
            return
        builtin = load_operator_catalog(self.builtin_path) if self.builtin_path else load_operator_catalog()
        self.state = OperatorConfigState(catalog=builtin, version="builtin", source="builtin")

    def _load_cache(self) -> bool:
        try:
            with self.cache_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return False
        valid, _ = validate_payload(payload)
        if not valid:
            return False
        catalog = OperatorCatalog.from_payload(payload)
        self.state = OperatorConfigState(
            catalog=catalog,
            version=str(payload.get("version")),
            etag=str(payload.get("etag") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            source="cache",
        )
        return True

    @property
    def catalog(self) -> OperatorCatalog:
        return self.state.catalog

    def apply_server_payload(self, payload: Any, etag: str = "") -> bool:
        payload = _unwrap(payload)
        valid, _ = validate_payload(payload)
        if not valid:
            return False
        catalog = OperatorCatalog.from_payload(payload)
        version = str(payload.get("version"))
        effective_etag = etag or str(payload.get("etag") or "")
        _write_cache(self.cache_path, payload, effective_etag)
        self.state = OperatorConfigState(
            catalog=catalog,
            version=version,
            etag=effective_etag,
            updated_at=str(payload.get("updated_at") or ""),
            source="server",
        )
        return True

    async def check_update(self, api: Any) -> tuple[str, str]:
        """返回 (kind, message)，kind=not_modified/updated/error。"""
        try:
            response = await api.get_operator_config(self.state.etag)
        except Exception as exc:  # noqa: BLE001 - 网络失败静默
            return "error", f"网络失败，请稍后（{exc}）"
        if response.status == 304:
            return "not_modified", "已是最新"
        if response.status == 200:
            valid, reason = validate_payload(response.payload)
            if not valid:
                return "error", f"服务器配置结构非法：{reason}"
            if self.apply_server_payload(response.payload, response.etag):
                return "updated", f"已更新到版本 {self.state.version}"
            return "error", "缓存写入失败，仍使用内存配置"
        return "error", f"服务器返回异常状态 {response.status}"
