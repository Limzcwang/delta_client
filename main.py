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
import logging
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
import uuid

from config import APP_VERSION, AppConfig, ConfigError, load_config, save_config
from state.logging_setup import setup_logging
from state.paths import app_data_dir, migrate_legacy_data
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
        "--version",
        action="store_true",
        help="打印版本号后退出",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="打印生效配置后退出（不导入 PySide6，适合排障）",
    )
    parser.add_argument("--check", action="store_true", help="检查 Python 依赖与生效配置后退出")
    parser.add_argument(
        "--ui",
        choices=("widgets", "qml", "qml-lobby"),
        default="widgets",
        help="UI 承载方式：widgets（默认）或 qml-lobby（H0 QQuickWidget 大厅 spike）",
    )
    return parser


def _write_cli(text: str) -> None:
    """CLI 输出：source 模式 stdout；windowed PyInstaller 回退临时文件。"""
    if sys.stdout is not None:
        try:
            print(text)
            return
        except Exception:  # noqa: BLE001
            pass
    try:
        target = Path(tempfile.gettempdir()) / "DeltaClient-cli.txt"
        target.write_text(text + "\n", encoding="utf-8")
    except OSError:
        pass


def _effective_config_dict(config: AppConfig) -> dict[str, object]:
    payload = config.public_dict()
    payload["version"] = APP_VERSION
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
    if args.version:
        _write_cli(f"delta-client {APP_VERSION}")
        return 0
    migrated = migrate_legacy_data()
    setup_logging()
    logging.getLogger(__name__).info(
        "Delta Client %s starting (data_dir=%s)", APP_VERSION, app_data_dir()
    )
    if migrated:
        logging.getLogger(__name__).info("已迁移旧版数据文件 %s 个", len(migrated))
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
        _write_cli(json.dumps(_effective_config_dict(config), ensure_ascii=False, indent=2))
        return 0
    if args.check:
        return _check_dependencies(config)
    if not config.client_diag_id:
        config = replace(config, client_diag_id=uuid.uuid4().hex)
        try:
            save_config(config)
        except OSError:
            pass

    from state.crash_logging import (
        clear_current_step,
        crash_log_path,
        heartbeat,
        install_crash_logging,
        install_qt_message_handler,
        read_previous_step,
        set_current_step,
        shutdown_crash_logging,
        start_stall_watchdog,
    )

    previous_crash = read_previous_step()
    install_crash_logging(APP_VERSION)
    install_qt_message_handler()

    if sys.platform == "win32":
        try:
            from capture.window import ensure_dpi_aware

            ensure_dpi_aware()
        except Exception:  # noqa: BLE001
            pass

    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        shutdown_crash_logging()
        print("缺少 PySide6，无法启动图形界面。", file=sys.stderr)
        print("请执行：python -m pip install -r requirements.txt", file=sys.stderr)
        print("若只想查看配置，可运行：python main.py --print-config", file=sys.stderr)
        return 1

    from ui.single_instance import SingleInstance
    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    session = None
    if config.persist_token:
        session = Session.from_file(default_session_path(), persist_token=True)

    app = QApplication(sys.argv[:1])
    lock = SingleInstance("DeltaClient")
    if not lock.acquire():
        lock.activate_existing()
        shutdown_crash_logging()
        QMessageBox.information(None, "Delta Client", "Delta Client 已在运行")
        return 1
    app.setApplicationName("Delta Client")
    app.setOrganizationName("Delta")
    icon_base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    icon_file = icon_base / "assets" / "app.ico"
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))
    apply_theme(app)
    window = MainWindow(config, session, ui_mode=args.ui)
    window.show()
    if previous_crash:
        try:
            from ui.crash_notice import show_previous_crash_notice

            show_previous_crash_notice(window, previous_crash, crash_log_path())
        except Exception:  # noqa: BLE001
            pass
    clear_current_step()
    set_current_step("running")
    from PySide6.QtCore import QTimer

    heartbeat_timer = QTimer()
    heartbeat_timer.setInterval(1000)
    heartbeat_timer.timeout.connect(heartbeat)
    heartbeat_timer.start()
    start_stall_watchdog(2.0)
    exit_code = int(app.exec())
    heartbeat_timer.stop()
    shutdown_crash_logging()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
