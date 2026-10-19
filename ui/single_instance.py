"""单实例锁：同一台机器只允许一个 Delta Client 进程（文件锁）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class SingleInstance:
    def __init__(self, name: str = "DeltaClient") -> None:
        safe = "".join(ch for ch in name if ch.isalnum() or ch in "-_.") or "DeltaClient"
        self.path = Path(tempfile.gettempdir()) / f".{safe}.instance.lock"
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        try:
            handle = self.path.open("a+b")
            handle.seek(0)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._handle = handle
            return True
        except (OSError, IOError):
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
            return False

    def activate_existing(self) -> bool:
        """文件锁模式无法跨进程激活窗口；由调用方提示用户。"""
        return False

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError):
            pass
        finally:
            try:
                handle.close()
            except Exception:  # noqa: BLE001
                pass
