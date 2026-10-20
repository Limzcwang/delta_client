"""客户端配置：服务器地址、WebSocket 地址与运行模式。

配置优先级（高 -> 低）：
1. 命令行参数（``main.py`` 的 ``--server`` / ``--mock`` / ``--no-mock``）
2. 环境变量：``DELTA_SERVER`` / ``DELTA_WS`` / ``DELTA_MOCK`` / ``DELTA_SAVE_TOKEN``
3. 配置文件：``~/.delta_client.json``（可用 ``DELTA_CLIENT_CONFIG`` 指定其它路径）
4. 内置默认值：``http://127.0.0.1:8000``

配置文件示例::

    {
      "server_url": "http://127.0.0.1:8000",
      "ws_url": null,
      "mock": false,
      "save_token": false,
      "operator_id": "honglang",
      "request_timeout": 15.0
    }

安全约定：配置文件只保存连接参数，**不保存密码、不保存 token**；
token 的可选落盘由 :class:`state.session.Session` 单独处理。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.protocol import ws_url_for
from state.paths import APP_NAME

DEFAULT_SERVER_URL = "https://deltachat.icu"
FALLBACK_SERVER_URL = "https://deltachat.icu:8443"
LEGACY_DEFAULT_SERVER_URL = "http://114.132.161.169:8000"
LEGACY_WS_URL = "ws://114.132.161.169:8000/ws"
LEGACY_HTTPS_SERVER_URL = "https://deltachat.icu:8443"
LEGACY_HTTPS_WS_URL = "wss://deltachat.icu:8443/ws"
DEFAULT_TIMEOUT = 15.0
CONFIG_FILENAME = ".delta_client.json"
APP_VERSION = "0.2.5"
__version__ = APP_VERSION
CONFIG_ENV = "DELTA_CLIENT_CONFIG"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", "n", "f"})


class ConfigError(ValueError):
    """配置错误（供 UI 提示用户修正配置）。"""


def parse_bool(value: Any, default: bool = False) -> bool:
    """宽松解析布尔值（环境变量/JSON 都可能出现字符串）。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def _normalize_url(raw: Any, schemes: tuple[str, ...], label: str) -> str:
    """校验并规范化 URL：补协议、去尾部斜杠、丢弃 query/fragment。"""
    text = str(raw or "").strip()
    if not text:
        raise ConfigError(f"{label}不能为空")
    if "://" not in text:
        text = f"{schemes[0]}://{text}"
    try:
        parts = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(text)
    except ValueError as exc:  # 例如端口非法
        raise ConfigError(f"{label}不合法：{text}") from exc
    scheme = parts.scheme.lower()
    if scheme not in schemes:
        raise ConfigError(f"{label}协议不支持：{scheme}（仅支持 {'/'.join(schemes)}）")
    if not parts.hostname:
        raise ConfigError(f"{label}缺少主机名：{text}")
    try:
        port = parts.port
    except ValueError as exc:
        raise ConfigError(f"{label}端口不合法：{text}") from exc
    if port is not None and not (0 < port < 65536):
        raise ConfigError(f"{label}端口不合法：{port}")
    path = parts.path.rstrip("/")
    return f"{scheme}://{parts.netloc}{path}"


def normalize_server_url(raw: Any) -> str:
    """规范化 HTTP(S) 服务器地址，例如 ``127.0.0.1:8000`` -> ``http://127.0.0.1:8000``。"""
    return _normalize_url(raw, ("http", "https"), "服务器地址")


def normalize_ws_url(raw: Any) -> str:
    """规范化 WebSocket 地址；也接受 http(s) 写法并自动换成 ws(s)。"""
    text = str(raw or "").strip()
    if text.lower().startswith("https://"):
        text = "wss://" + text[len("https://") :]
    elif text.lower().startswith("http://"):
        text = "ws://" + text[len("http://") :]
    return _normalize_url(text, ("ws", "wss"), "WebSocket 地址")


def connection_candidates(server_url: Any) -> list[str]:
    """连接候选：用户/当前地址优先，其次 443 默认与 8443 兼容；去重且保持顺序。"""
    candidates: list[str] = []
    for raw in (server_url, FALLBACK_SERVER_URL):
        if not raw:
            continue
        try:
            value = normalize_server_url(raw)
        except ConfigError:
            continue
        if value not in candidates:
            candidates.append(value)
    return candidates


def config_path_from_env(env: Mapping[str, str] | None = None) -> Path:
    """配置文件路径：``DELTA_CLIENT_CONFIG`` 优先，否则 ``%APPDATA%\\DeltaClient\\config.json``。"""
    source = os.environ if env is None else env
    override = str(source.get(CONFIG_ENV, "") or "").strip()
    if override:
        return Path(override).expanduser()
    data_override = str(source.get("DELTA_DATA_DIR", "") or "").strip()
    if data_override:
        return Path(data_override).expanduser() / "config.json"
    appdata = str(source.get("APPDATA", "") or "").strip()
    if appdata:
        return Path(appdata) / APP_NAME / "config.json"
    return Path.home() / ".delta_client" / "config.json"


@dataclass(frozen=True)
class AppConfig:
    """客户端生效配置（不可变，改配置请用 dataclasses.replace）。"""

    server_url: str = DEFAULT_SERVER_URL
    ws_url: str | None = None
    use_mock: bool = False
    persist_token: bool = False
    operator_id: str = ""
    hud_profile: dict[str, Any] | None = None
    server_migrated: bool = False
    overlay_enabled: bool = False
    overlay_opacity: int = 30
    overlay_scale: float = 1.0
    overlay_x: int | None = None
    overlay_y: int | None = None
    shortcut_toggle: str = "Ctrl+Shift+D"
    shortcut_edit: str = "Ctrl+Shift+E"
    auto_capture_enabled: bool = False
    auto_loop_enabled: bool = False
    auto_sample_ms: int = 2000
    capture_window_process: str = "DeltaForceClient-Win64-Shipping"
    capture_window_title: str = ""
    title_match_strict: bool = True
    auto_operator_enabled: bool = True
    operator_recognition_threshold: float = 0.65
    hud_debug_export: bool = False
    request_timeout: float = DEFAULT_TIMEOUT
    source: str = "default"

    @property
    def effective_ws_url(self) -> str:
        """显式配置的 WS 地址优先，否则由 HTTP 地址推导（``ws(s)://host/ws``）。"""
        return self.ws_url or ws_url_for(self.server_url)

    @property
    def mode_label(self) -> str:
        return "MOCK" if self.use_mock else "LIVE"

    def public_dict(self) -> dict[str, Any]:
        """可安全落盘/打印的配置（不含任何凭据）。"""
        return {
            "server_url": self.server_url,
            "ws_url": self.ws_url,
            "mock": self.use_mock,
            "save_token": self.persist_token,
            "operator_id": self.operator_id,
            "hud_profile": self.hud_profile,
            "overlay_enabled": self.overlay_enabled,
            "overlay_opacity": self.overlay_opacity,
            "overlay_scale": self.overlay_scale,
            "overlay_x": self.overlay_x,
            "overlay_y": self.overlay_y,
            "shortcut_toggle": self.shortcut_toggle,
            "shortcut_edit": self.shortcut_edit,
            "auto_capture_enabled": self.auto_capture_enabled,
            "auto_loop_enabled": self.auto_loop_enabled,
            "auto_sample_ms": self.auto_sample_ms,
            "capture_window_process": self.capture_window_process,
            "capture_window_title": self.capture_window_title,
            "title_match_strict": self.title_match_strict,
            "auto_operator_enabled": self.auto_operator_enabled,
            "operator_recognition_threshold": self.operator_recognition_threshold,
            "hud_debug_export": self.hud_debug_export,
            "request_timeout": self.request_timeout,
        }


def _read_config_file(path: Path) -> dict[str, Any]:
    """读取 JSON 配置；文件不存在/损坏时返回空字典（不阻塞启动）。"""
    try:
        if not path.is_file():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_config_data(path: Path, data: Mapping[str, Any]) -> bool:
    """保留字段原子写回配置；失败不阻塞启动。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, path)
        return True
    except OSError:
        return False


def _migrate_legacy_server(path: Path, file_data: dict[str, Any]) -> bool:
    """旧 HTTP 默认地址 -> HTTPS 默认；仅迁移该精确旧值，保留其它字段。"""
    raw = file_data.get("server_url")
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        normalized = normalize_server_url(raw)
    except ConfigError:
        return False
    if normalized not in (LEGACY_DEFAULT_SERVER_URL, LEGACY_HTTPS_SERVER_URL):
        return False
    updated = dict(file_data)
    updated["server_url"] = DEFAULT_SERVER_URL
    old_ws = str(updated.get("ws_url") or "").strip()
    if old_ws:
        try:
            if normalize_ws_url(old_ws) in (LEGACY_WS_URL, LEGACY_HTTPS_WS_URL):
                updated.pop("ws_url", None)
        except ConfigError:
            pass
    _write_config_data(path, updated)
    file_data.clear()
    file_data.update(updated)
    return True


def load_config(
    path: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    server_override: str | None = None,
    ws_override: str | None = None,
    mock_override: bool | None = None,
) -> AppConfig:
    """按优先级合并 CLI / 环境变量 / 配置文件，返回生效配置。"""
    env_map: Mapping[str, str] = os.environ if env is None else env
    config_path = Path(path).expanduser() if path is not None else config_path_from_env(env_map)
    file_data = _read_config_file(config_path)
    server_migrated = _migrate_legacy_server(config_path, file_data)

    server = DEFAULT_SERVER_URL
    source = "file-migrated" if server_migrated else "default"

    file_server = file_data.get("server_url")
    if isinstance(file_server, str) and file_server.strip():
        server = normalize_server_url(file_server)
        source = "file"

    env_server = str(env_map.get("DELTA_SERVER", "") or "").strip()
    if env_server:
        server = normalize_server_url(env_server)
        source = "env"

    if server_override:
        server = normalize_server_url(server_override)
        source = "cli"

    ws_url: str | None = None
    file_ws = file_data.get("ws_url")
    if isinstance(file_ws, str) and file_ws.strip():
        ws_url = normalize_ws_url(file_ws)
    env_ws = str(env_map.get("DELTA_WS", "") or "").strip()
    if env_ws:
        ws_url = normalize_ws_url(env_ws)
    if ws_override:
        ws_url = normalize_ws_url(ws_override)

    use_mock = parse_bool(file_data.get("mock"), False)
    if "DELTA_MOCK" in env_map:
        use_mock = parse_bool(env_map.get("DELTA_MOCK"), use_mock)
    if mock_override is not None:
        use_mock = bool(mock_override)

    persist_token = parse_bool(file_data.get("save_token"), False)
    if "DELTA_SAVE_TOKEN" in env_map:
        persist_token = parse_bool(env_map.get("DELTA_SAVE_TOKEN"), persist_token)

    operator_id = str(file_data.get("operator_id") or "").strip()
    hud_profile = file_data.get("hud_profile")
    if not isinstance(hud_profile, dict):
        hud_profile = None
    overlay_enabled = parse_bool(file_data.get("overlay_enabled"), False)
    try:
        overlay_opacity = min(100, max(10, int(file_data.get("overlay_opacity", 30))))
    except (TypeError, ValueError):
        overlay_opacity = 30
    try:
        overlay_scale = min(2.0, max(0.6, float(file_data.get("overlay_scale", 1.0))))
    except (TypeError, ValueError):
        overlay_scale = 1.0
    overlay_x = file_data.get("overlay_x")
    overlay_y = file_data.get("overlay_y")
    overlay_x = int(overlay_x) if isinstance(overlay_x, (int, float)) else None
    overlay_y = int(overlay_y) if isinstance(overlay_y, (int, float)) else None
    shortcut_toggle = str(file_data.get("shortcut_toggle") or "Ctrl+Shift+D")
    shortcut_edit = str(file_data.get("shortcut_edit") or "Ctrl+Shift+E")
    auto_capture_enabled = parse_bool(file_data.get("auto_capture_enabled"), False)
    auto_loop_enabled = parse_bool(file_data.get("auto_loop_enabled"), False)
    try:
        auto_sample_ms = int(file_data.get("auto_sample_ms", 2000))
    except (TypeError, ValueError):
        auto_sample_ms = 2000
    if auto_sample_ms not in (1000, 2000, 3000):
        auto_sample_ms = 2000
    capture_window_process = str(
        file_data.get("capture_window_process") or "DeltaForceClient-Win64-Shipping"
    ).strip()
    capture_window_title = str(file_data.get("capture_window_title") or "").strip()
    title_match_strict = parse_bool(file_data.get("title_match_strict"), True)
    auto_operator_enabled = parse_bool(file_data.get("auto_operator_enabled"), True)
    hud_debug_export = parse_bool(file_data.get("hud_debug_export"), False)
    try:
        operator_recognition_threshold = min(
            0.95, max(0.5, float(file_data.get("operator_recognition_threshold", 0.65)))
        )
    except (TypeError, ValueError):
        operator_recognition_threshold = 0.65

    timeout = DEFAULT_TIMEOUT
    raw_timeout = file_data.get("request_timeout")
    if isinstance(raw_timeout, (int, float)) and raw_timeout > 0:
        timeout = float(raw_timeout)

    return AppConfig(
        server_url=server,
        ws_url=ws_url,
        use_mock=use_mock,
        persist_token=persist_token,
        operator_id=operator_id,
        hud_profile=hud_profile,
        server_migrated=server_migrated,
        overlay_enabled=overlay_enabled,
        overlay_opacity=overlay_opacity,
        overlay_scale=overlay_scale,
        overlay_x=overlay_x,
        overlay_y=overlay_y,
        shortcut_toggle=shortcut_toggle,
        shortcut_edit=shortcut_edit,
        auto_capture_enabled=auto_capture_enabled,
        auto_loop_enabled=auto_loop_enabled,
        auto_sample_ms=auto_sample_ms,
        capture_window_process=capture_window_process,
        capture_window_title=capture_window_title,
        title_match_strict=title_match_strict,
        auto_operator_enabled=auto_operator_enabled,
        operator_recognition_threshold=operator_recognition_threshold,
        hud_debug_export=hud_debug_export,
        request_timeout=timeout,
        source=source,
    )


def save_config(config: AppConfig, path: str | os.PathLike[str] | None = None) -> Path:
    """原子写入配置文件，返回实际写入路径。"""
    target = Path(path).expanduser() if path is not None else config_path_from_env()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = config.public_dict()
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".delta_client.", suffix=".json.tmp", dir=str(target.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


