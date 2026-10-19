#!/usr/bin/env python3
"""Delta Client 入口：配置解析 -> 启动 PySide6 桌面客户端。

用法::

    python main.py                 # 按环境变量/配置文件启动
    python main.py --mock          # 使用内置 Mock 后端演示（不联网）
    python main.py --server http://127.0.0.1:8000
    python main.py --print-config  # 只打印生效配置（无需 GUI 依赖）
    python main.py --check         # 检查依赖是否安装
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys

from config import AppConfig, ConfigError, load_config
from state.session import Session, default_session_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delta-client",
        description="Delta Client - 三角洲行动队友房间桌面客户端（PySide6）",
    )
    parser.add_argument(
        "--server",
        help="HTTP 服务器地址，例如 http://127.0.0.1:8000（优先级高于 DELTA_SERVER 与配置文件）",
    )
    parser.add_argument(
        "--ws",
        dest="ws_url",
        help="WebSocket 地址，例如 ws://127.0.0.1:8765；留空则由服务器地址推导 ws(s)://host/ws",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="强制使用内置 Mock 后端（不联网）")
    mode.add_argument("--no-mock", action="store_true", help="强制关闭 Mock 后端（连接真实服务器）")
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="打印生效配置后退出（不导入 PySide6，适合排障）",
    )
    parser.add_argument("--check", action="store_true", help="检查 Python 依赖与生效配置后退出")
    return parser


def _effective_config_dict(config: AppConfig) -> dict[str, object]:
    payload = config.public_dict()
    payload["effective_ws_url"] = config.effective_ws_url
    payload["source"] = config.source
    return payload


def _check_dependencies(config: AppConfig) -> int:
    required = ("PySide6", "aiohttp", "websockets")
    missing: list[str] = []
    for name in required:
        try:
            module = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            print(f"[缺少] {name}")
        else:
            version = getattr(module, "__version__", "unknown")
            print(f"[ OK ] {name} {version}")
    print("生效配置：")
    print(json.dumps(_effective_config_dict(config), ensure_ascii=False, indent=2))
    if missing:
        print(f"\n缺少依赖：{', '.join(missing)}")
        print("请执行：python -m pip install -r requirements.txt")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mock_override = True if args.mock else (False if args.no_mock else None)
    try:
        config = load_config(
            server_override=args.server,
            ws_override=args.ws_url,
            mock_override=mock_override,
        )
    except ConfigError as exc:
        print(f"[配置错误] {exc}", file=sys.stderr)
        print("可用 DELTA_SERVER 环境变量、~/.delta_client.json 或 --server 指定服务器地址", file=sys.stderr)
        return 2

    if args.print_config:
        print(json.dumps(_effective_config_dict(config), ensure_ascii=False, indent=2))
        return 0
    if args.check:
        return _check_dependencies(config)

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("缺少 PySide6，无法启动图形界面。", file=sys.stderr)
        print("请执行：python -m pip install -r requirements.txt", file=sys.stderr)
        print("若只想查看配置，可运行：python main.py --print-config", file=sys.stderr)
        return 1

    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    session = None
    if config.persist_token:
        session = Session.from_file(default_session_path(), persist_token=True)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Delta Client")
    app.setOrganizationName("Delta")
    apply_theme(app)
    window = MainWindow(config, session)
    window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
