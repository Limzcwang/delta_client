"""HUD 调试导出：三槽 ROI + 整帧缩略图 + result.json，保留最近 N 次。"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from core.hud_pipeline import RecognitionFrame
from core.hud_profile import HudProfile, Roi

logger = logging.getLogger(__name__)


class HudDebugExporter:
    def __init__(self, base_dir: str | Path | None = None, keep: int = 10) -> None:
        from state.paths import app_data_dir

        self.base_dir = Path(base_dir) if base_dir else app_data_dir() / "hud_debug"
        self.keep = max(1, int(keep))

    def export(
        self,
        frame: Any,
        profile: HudProfile,
        recognized: RecognitionFrame,
        *,
        operator_id: str = "",
        operator_name: str = "",
        extra: dict[str, Any] | None = None,
    ) -> Path | None:
        try:
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns()}"
            target = self.base_dir / stamp
            target.mkdir(parents=True, exist_ok=True)
            cv2 = None
            try:
                import cv2  # type: ignore[import-not-found]
            except Exception:  # noqa: BLE001
                cv2 = None
            if cv2 is not None and frame is not None:
                try:
                    cv2.imwrite(str(target / "frame.png"), frame)
                    for index, roi in enumerate(profile.slot_rois()):
                        crop = frame[int(roi.y) : int(roi.bottom), int(roi.x) : int(roi.right)]
                        cv2.imwrite(str(target / f"slot{index}.png"), crop)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("HUD 调试图片写入失败：%s", exc)
            payload = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "operator_id": operator_id or recognized.operator_id,
                "operator_name": operator_name or recognized.operator_name,
                "profile": profile.to_dict(),
                "diagnostics": [item.to_dict() for item in recognized.diagnostics],
                "payload": recognized.payload(),
                "extra": dict(extra or {}),
            }
            (target / "result.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._prune()
            return target
        except Exception as exc:  # noqa: BLE001
            logger.warning("HUD 调试导出失败：%s", exc)
            return None

    def _prune(self) -> None:
        dirs = sorted([path for path in self.base_dir.iterdir() if path.is_dir()])
        for old in dirs[: max(0, len(dirs) - self.keep)]:
            try:
                shutil.rmtree(old)
            except OSError:
                pass
