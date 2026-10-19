"""画板纯逻辑（D）：归一化坐标、op 校验/分段、文档状态、撤销重做、限频、快照上限。

对应 PROTOCOL §5 / §6.7 / §6.5：

- 坐标一律 **0–1 归一化**（显示基准 1920×1080，客户端按窗口缩放换算）；
- `stroke`：`points` ≤ 512 个，`color` `#RRGGBB`，`width` 1–32，`tool` pen/eraser；
- `clear`：清空整块画板；
- 快照：`{strokes:[CanvasOp], rev}`，≤ 5000 笔 / ≤ 512KB；
- `rev` 每连接每房间从 0 单调递增，只用于丢弃旧包，不做状态合并；
- undo/redo 纯客户端（服务端无 undo）。

本模块只依赖标准库，便于离线单测。
"""

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from core.protocol import unwrap_payload

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
MAX_POINTS_PER_OP = 512
MAX_STROKES = 5000
MAX_SNAPSHOT_BYTES = 512 * 1024
CANVAS_OPS_PER_SECOND = 30
DEFAULT_COLOR = "#FF3B30"
DEFAULT_WIDTH = 4
TOOLS = ("pen", "eraser")

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CanvasError(ValueError):
    """画板输入/快照不合法（UI 直接展示 message）。"""


def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CanvasError("坐标必须是 0–1 的数字") from exc
    if number < 0.0:
        return 0.0
    if number > 1.0:
        return 1.0
    return round(number, 4)


def normalize_points(points: Iterable[Any]) -> list[dict[str, float]]:
    """把 ``[{x,y}]`` / ``[(x,y)]`` 规范成 0–1 归一化点（超界收敛到边界）。"""
    normalized: list[dict[str, float]] = []
    for point in points:
        if isinstance(point, Mapping):
            if "x" not in point or "y" not in point:
                raise CanvasError("点必须包含 x/y")
            x, y = point.get("x"), point.get("y")
        elif isinstance(point, (list, tuple)) and len(point) == 2:
            x, y = point
        else:
            raise CanvasError("点必须是 {x,y} 或 [x,y]")
        if isinstance(x, bool) or isinstance(y, bool):
            raise CanvasError("坐标必须是数字")
        normalized.append({"x": _clamp01(x), "y": _clamp01(y)})
    if not normalized:
        raise CanvasError("笔画至少需要 1 个点")
    return normalized


def split_points(
    points: Sequence[Any], limit: int = MAX_POINTS_PER_OP
) -> list[list[dict[str, float]]]:
    """按服务端上限切分长笔画：相邻分段共享一个端点，保证视觉连续。"""
    if limit < 2:
        raise CanvasError("分段上限必须 >= 2")
    normalized = normalize_points(points)
    if len(normalized) <= limit:
        return [normalized]
    chunks: list[list[dict[str, float]]] = []
    start = 0
    total = len(normalized)
    while start < total:
        chunk = normalized[start : start + limit]
        chunks.append(chunk)
        if start + limit >= total:
            break
        start += limit - 1  # 重叠最后一个点，续接下一段
    return chunks


def validate_op(op: Any) -> dict[str, Any]:
    """校验并规范化一个 CanvasOp；非法抛 :class:`CanvasError`。"""
    if not isinstance(op, Mapping):
        raise CanvasError("画板操作必须是 JSON 对象")
    kind = op.get("kind")
    if kind == "clear":
        return {"kind": "clear"}
    if kind != "stroke":
        raise CanvasError("kind 必须是 stroke 或 clear")

    raw_points = op.get("points")
    if not isinstance(raw_points, (list, tuple)):
        raise CanvasError("stroke.points 必须是数组")
    if not raw_points:
        raise CanvasError("stroke.points 不能为空")
    if len(raw_points) > MAX_POINTS_PER_OP:
        raise CanvasError(f"单笔最多 {MAX_POINTS_PER_OP} 个点，请分段发送")
    points = normalize_points(raw_points)

    color = op.get("color", DEFAULT_COLOR)
    if not isinstance(color, str) or not _COLOR_RE.fullmatch(color):
        raise CanvasError("color 必须是 #RRGGBB")
    width = op.get("width", DEFAULT_WIDTH)
    if isinstance(width, bool) or not isinstance(width, (int, float)):
        raise CanvasError("width 必须是数字")
    width_int = int(width)
    if width_int != float(width) or not 1 <= width_int <= 32:
        raise CanvasError("width 必须是 1–32 的整数")
    tool = op.get("tool", "pen")
    if tool not in TOOLS:
        raise CanvasError("tool 必须是 pen 或 eraser")

    return {
        "kind": "stroke",
        "points": points,
        "color": color.upper(),
        "width": width_int,
        "tool": tool,
    }


def make_stroke_op(
    points: Sequence[Any],
    color: str = DEFAULT_COLOR,
    width: int = DEFAULT_WIDTH,
    tool: str = "pen",
) -> dict[str, Any]:
    return validate_op(
        {"kind": "stroke", "points": list(points), "color": color, "width": width, "tool": tool}
    )


def make_clear_op() -> dict[str, Any]:
    return {"kind": "clear"}


def snapshot_size_bytes(strokes: Sequence[Mapping[str, Any]]) -> int:
    return len(
        json.dumps(list(strokes), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def check_snapshot_limits(strokes: Sequence[Mapping[str, Any]]) -> str | None:
    """返回超限提示；未超限返回 None。"""
    if len(strokes) > MAX_STROKES:
        return f"画布已满（超过 {MAX_STROKES} 笔），请清空后再保存"
    if snapshot_size_bytes(strokes) > MAX_SNAPSHOT_BYTES:
        return "画布已满（快照超过 512KB），请清空后再保存"
    return None


@dataclass(frozen=True)
class CanvasSnapshot:
    """画板快照（``room_joined.canvas_snapshot`` 或 HTTP GET canvas）。"""

    strokes: tuple[dict[str, Any], ...] = ()
    rev: int = 0
    updated_at: int | None = None


def parse_canvas_snapshot(payload: Any) -> CanvasSnapshot:
    """解析快照；非法 op 跳过（服务端可能存有旧版本/未知字段，客户端容错）。"""
    data = unwrap_payload(payload)
    if not isinstance(data, Mapping):
        return CanvasSnapshot()
    raw_strokes = data.get("strokes")
    strokes: list[dict[str, Any]] = []
    if isinstance(raw_strokes, list):
        for raw_op in raw_strokes:
            try:
                op = validate_op(raw_op)
            except CanvasError:
                continue
            if op.get("kind") == "clear":
                strokes.clear()
            else:
                strokes.append(op)
    raw_rev = data.get("rev", 0)
    try:
        rev = int(raw_rev)
    except (TypeError, ValueError):
        rev = 0
    raw_updated = data.get("updated_at")
    try:
        updated_at = int(raw_updated) if raw_updated is not None else None
    except (TypeError, ValueError):
        updated_at = None
    return CanvasSnapshot(strokes=tuple(strokes), rev=max(0, rev), updated_at=updated_at)


class CanvasDocument:
    """客户端画板文档：当前笔画 + 本地 undo/redo（服务端无 undo）。

    - 本地绘制/清空会记录 undo 快照；
    - 远端 op 应用后清空 undo/redo 历史，避免 undo 误删队友笔画；
    - 快照保存时用 :meth:`snapshot_strokes` 生成全量笔画。
    """

    def __init__(self, undo_limit: int = 50) -> None:
        self.ops: list[dict[str, Any]] = []
        self._undo: list[list[dict[str, Any]]] = []
        self._redo: list[list[dict[str, Any]]] = []
        self._undo_limit = max(1, int(undo_limit))

    @property
    def is_empty(self) -> bool:
        return not self.ops

    @property
    def count(self) -> int:
        return len(self.ops)

    def reset(self) -> None:
        self.ops = []
        self._undo.clear()
        self._redo.clear()

    def apply_snapshot(self, strokes: Iterable[Mapping[str, Any]]) -> None:
        """用快照覆盖当前画面（重连/进房以服务端快照为准，不保留旧增量）。"""
        ops: list[dict[str, Any]] = []
        for raw_op in strokes:
            try:
                op = validate_op(raw_op)
            except CanvasError:
                continue
            if op.get("kind") == "clear":
                ops = []
            else:
                ops.append(op)
        self.ops = ops
        self._undo.clear()
        self._redo.clear()

    def apply_remote_op(self, op: Mapping[str, Any]) -> None:
        op = validate_op(op)
        if op.get("kind") == "clear":
            self.ops = []
        else:
            self.ops.append(op)
        self._undo.clear()
        self._redo.clear()

    def _push_undo(self) -> None:
        self._undo.append(list(self.ops))
        if len(self._undo) > self._undo_limit:
            self._undo.pop(0)

    def add_stroke(
        self,
        points: Sequence[Any],
        color: str = DEFAULT_COLOR,
        width: int = DEFAULT_WIDTH,
        tool: str = "pen",
    ) -> list[dict[str, Any]]:
        """本地落笔：自动按 ≤512 点分段，返回实际追加的 op 列表。"""
        segments = split_points(points)
        ops = [make_stroke_op(segment, color, width, tool) for segment in segments]
        self._push_undo()
        self.ops.extend(ops)
        self._redo.clear()
        return ops

    def clear(self) -> None:
        if not self.ops:
            return
        self._push_undo()
        self.ops = []
        self._redo.clear()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(list(self.ops))
        self.ops = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(list(self.ops))
        self.ops = self._redo.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def snapshot_strokes(self) -> list[dict[str, Any]]:
        return list(self.ops)


class CanvasRateLimiter:
    """滑动窗口限频（默认 30 次/秒），用于本地节流避免触发服务端 RATE_LIMITED。"""

    def __init__(
        self,
        max_events: int = CANVAS_OPS_PER_SECOND,
        window: float = 1.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_events < 1 or window <= 0:
            raise ValueError("限频参数非法")
        self.max_events = int(max_events)
        self.window = float(window)
        self._clock = clock or time.monotonic
        self._events: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self._events and now - self._events[0] >= self.window:
            self._events.popleft()

    def allow(self, now: float | None = None) -> bool:
        moment = self._clock() if now is None else float(now)
        self._prune(moment)
        if len(self._events) >= self.max_events:
            return False
        self._events.append(moment)
        return True

    def wait_seconds(self, now: float | None = None) -> float:
        """还需要等待多久才允许下一次发送（窗口满时）。"""
        moment = self._clock() if now is None else float(now)
        self._prune(moment)
        if len(self._events) < self.max_events:
            return 0.0
        return max(0.0, self.window - (moment - self._events[0]))
