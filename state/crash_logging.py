"""崩溃可观测性：faulthandler / 未捕获异常 / Qt 消息 / 最后操作标记。"""

from __future__ import annotations

import atexit
import faulthandler
import json
import logging
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from types import TracebackType
from typing import Any

from state.paths import app_data_dir

logger = logging.getLogger(__name__)

_crash_file = None
_step_path: Path | None = None
_installed = False
_original_excepthook = sys.excepthook
_original_thread_hook = threading.excepthook
_qt_handler_installed = False


def crash_log_path() -> Path:
    override = str(os.environ.get("DELTA_CRASH_LOG", "") or "").strip()
    return Path(override).expanduser() if override else app_data_dir() / "logs" / "crash.log"


def last_step_path() -> Path:
    override = str(os.environ.get("DELTA_LAST_STEP", "") or "").strip()
    return Path(override).expanduser() if override else app_data_dir() / "logs" / "last_step.json"


def _write(text: str) -> None:
    global _crash_file
    if not _installed and _crash_file is None:
        return
    if _crash_file is None:
        try:
            path = crash_log_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _crash_file = path.open("a", encoding="utf-8", buffering=1)
        except OSError:
            _crash_file = None
    if _crash_file is not None:
        try:
            _crash_file.write(text)
            _crash_file.flush()
        except OSError:
            pass
    if sys.stderr is not None:
        try:
            sys.stderr.write(text)
            sys.stderr.flush()
        except Exception:  # noqa: BLE001
            pass


def set_current_step(step: str) -> None:
    """记录最后操作；硬崩溃后由下次启动读取提示。"""
    global _step_path
    if not _installed:
        return
    try:
        path = _step_path or last_step_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "step": str(step),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": _version,
        }
        temp = path.with_name(path.name + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, path)
        _write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} STEP {step}\n")
    except OSError:
        pass


def clear_current_step() -> None:
    path = _step_path or last_step_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def read_previous_step() -> dict[str, Any] | None:
    path = _step_path or last_step_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("step") else None


def _exception_hook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _write(
        f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] UNCAUGHT {exc_type.__name__} "
        f"version={_version} thread={threading.current_thread().name}\n{text}\n"
    )
    _original_excepthook(exc_type, exc, tb)


def _thread_hook(args: threading.ExceptHookArgs) -> None:
    _write(
        f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] THREAD UNCAUGHT "
        f"version={_version} thread={args.thread.name if args.thread else '?'}\n"
    )
    _write("".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    _original_thread_hook(args)


def _qt_message_handler(mode: Any, context: Any, message: str) -> None:
    try:
        level = getattr(mode, "name", str(mode))
        _write(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} QT {level} "
            f"version={_version} step={_current_step()} {message}\n"
        )
    except Exception:  # noqa: BLE001
        pass


def _current_step() -> str:
    data = read_previous_step() or {}
    return str(data.get("step") or "-")


def install_qt_message_handler() -> bool:
    global _qt_handler_installed
    if _qt_handler_installed:
        return True
    try:
        from PySide6.QtCore import qInstallMessageHandler

        qInstallMessageHandler(_qt_message_handler)
        _qt_handler_installed = True
        return True
    except Exception:  # noqa: BLE001
        return False


def install_crash_logging(version: str = "", path: str | Path | None = None, step_path: str | Path | None = None) -> None:
    global _crash_file, _step_path, _installed, _version, _original_excepthook, _original_thread_hook
    if _installed:
        return
    _version = version
    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _crash_file = target.open("a", encoding="utf-8", buffering=1)
        try:
            faulthandler.enable(file=_crash_file, all_threads=True)
        except Exception:  # noqa: BLE001
            pass
    else:
        try:
            target = crash_log_path()
            target.parent.mkdir(parents=True, exist_ok=True)
            _crash_file = target.open("a", encoding="utf-8", buffering=1)
            faulthandler.enable(file=_crash_file, all_threads=True)
        except OSError:
            _crash_file = None
    _step_path = Path(step_path) if step_path is not None else last_step_path()
    _original_excepthook = sys.excepthook
    _original_thread_hook = threading.excepthook
    sys.excepthook = _exception_hook
    threading.excepthook = _thread_hook
    _installed = True
    atexit.register(clear_current_step)
    _write(
        f"\n===== Delta Client {version} started {time.strftime('%Y-%m-%d %H:%M:%S')} "
        f"pid={os.getpid()} =====\n"
    )
    set_current_step("startup")


def shutdown_crash_logging() -> None:
    global _crash_file, _installed, _stall_thread
    _stall_stop.set()
    if _stall_thread is not None:
        _stall_thread.join(timeout=1.0)
        _stall_thread = None
    clear_current_step()
    if _crash_file is not None:
        try:
            faulthandler.disable()
            _crash_file.flush()
            _crash_file.close()
        except (OSError, ValueError):
            pass
        _crash_file = None
    if _installed:
        sys.excepthook = _original_excepthook
        threading.excepthook = _original_thread_hook
        _installed = False


_version = ""
_stall_thread: threading.Thread | None = None
_stall_stop = threading.Event()
_last_heartbeat = 0.0


def heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = time.monotonic()


def start_stall_watchdog(threshold: float = 2.0) -> None:
    """主线程心跳超过 threshold 未更新时把全部线程栈写入 crash.log。"""
    global _stall_thread, _last_heartbeat
    if not _installed or _stall_thread is not None:
        return
    heartbeat()
    _stall_stop.clear()

    def loop() -> None:
        last_dump = 0.0
        while not _stall_stop.wait(0.5):
            now = time.monotonic()
            if now - _last_heartbeat >= threshold and now - last_dump >= threshold:
                _write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] STALL >{threshold:.0f}s step={_current_step()}\n")
                try:
                    if _crash_file is not None:
                        faulthandler.dump_traceback(file=_crash_file, all_threads=True)
                except Exception:  # noqa: BLE001
                    pass
                last_dump = now

    _stall_thread = threading.Thread(target=loop, name="delta-stall-watchdog", daemon=True)
    _stall_thread.start()
