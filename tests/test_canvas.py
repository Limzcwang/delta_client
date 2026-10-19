"""画板纯逻辑测试（离线）：归一化/校验/分段/文档/撤销重做/快照上限/限频。"""

from __future__ import annotations

import unittest

from core.canvas import (
    MAX_POINTS_PER_OP,
    MAX_STROKES,
    CanvasDocument,
    CanvasError,
    CanvasRateLimiter,
    check_snapshot_limits,
    make_clear_op,
    make_stroke_op,
    normalize_points,
    parse_canvas_snapshot,
    snapshot_size_bytes,
    split_points,
    validate_op,
)


class NormalizeTests(unittest.TestCase):
    def test_clamp_and_round(self) -> None:
        points = normalize_points([{"x": -0.5, "y": 1.5}, (0.123456, 0.5)])
        self.assertEqual(points[0], {"x": 0.0, "y": 1.0})
        self.assertEqual(points[1], {"x": 0.1235, "y": 0.5})

    def test_reject_invalid(self) -> None:
        for points in ([], [{"x": 0.1}], ["bad"], [(True, 0.2)], [("a", "b")]):
            with self.subTest(points=points):
                with self.assertRaises(CanvasError):
                    normalize_points(points)


class SplitTests(unittest.TestCase):
    def test_no_split_needed(self) -> None:
        points = [{"x": i / 100, "y": 0.5} for i in range(MAX_POINTS_PER_OP)]
        chunks = split_points(points)
        self.assertEqual(1, len(chunks))
        self.assertEqual(MAX_POINTS_PER_OP, len(chunks[0]))

    def test_long_stroke_split_with_overlap(self) -> None:
        points = [{"x": (i % 500) / 500, "y": 0.5} for i in range(1000)]
        chunks = split_points(points)
        self.assertEqual(2, len(chunks))
        self.assertTrue(all(len(chunk) <= MAX_POINTS_PER_OP for chunk in chunks))
        # 相邻分段共享端点，保证续接
        self.assertEqual(chunks[0][-1], chunks[1][0])
        self.assertEqual(1000, len(chunks[0]) + len(chunks[1]) - 1)


class ValidateOpTests(unittest.TestCase):
    def test_clear(self) -> None:
        self.assertEqual({"kind": "clear"}, validate_op({"kind": "clear"}))

    def test_valid_stroke_normalized(self) -> None:
        op = validate_op(
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "color": "#ff3b30", "width": 4, "tool": "pen"}
        )
        self.assertEqual("#FF3B30", op["color"])
        self.assertEqual(4, op["width"])
        self.assertEqual("pen", op["tool"])

    def test_invalid_strokes(self) -> None:
        cases = [
            {"kind": "line"},
            {"kind": "stroke", "points": []},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}] * (MAX_POINTS_PER_OP + 1)},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "color": "red"},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "color": "#GGGGGG"},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "width": 0},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "width": 33},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "width": 2.5},
            {"kind": "stroke", "points": [{"x": 0.1, "y": 0.2}], "tool": "brush"},
        ]
        for op in cases:
            with self.subTest(op=op):
                with self.assertRaises(CanvasError):
                    validate_op(op)

    def test_helpers(self) -> None:
        op = make_stroke_op([{"x": 0.5, "y": 0.5}], "#00FF00", 8, "eraser")
        self.assertEqual("eraser", op["tool"])
        self.assertEqual({"kind": "clear"}, make_clear_op())


class SnapshotTests(unittest.TestCase):
    def test_parse_envelope_and_clear_semantics(self) -> None:
        snapshot = parse_canvas_snapshot(
            {
                "code": 200,
                "data": {
                    "strokes": [
                        {"kind": "stroke", "points": [{"x": 0.1, "y": 0.1}]},
                        {"kind": "clear"},
                        {"kind": "stroke", "points": [{"x": 0.2, "y": 0.2}], "color": "#00FF00"},
                        {"kind": "stroke", "points": []},  # 非法，跳过
                    ],
                    "rev": 12,
                    "updated_at": 1750000000000,
                },
            }
        )
        self.assertEqual(1, len(snapshot.strokes))
        self.assertEqual(12, snapshot.rev)
        self.assertEqual(1750000000000, snapshot.updated_at)

    def test_parse_invalid_payload(self) -> None:
        self.assertEqual(0, len(parse_canvas_snapshot(None).strokes))
        self.assertEqual(0, parse_canvas_snapshot("junk").rev)

    def test_size_and_limits(self) -> None:
        op = make_stroke_op([{"x": 0.1, "y": 0.1}])
        self.assertGreater(snapshot_size_bytes([op]), 0)
        self.assertIsNone(check_snapshot_limits([op]))
        too_many = [op] * (MAX_STROKES + 1)
        self.assertIsNotNone(check_snapshot_limits(too_many))
        self.assertIn("画布已满", check_snapshot_limits(too_many) or "")
        # 构造超过 512KB 的快照
        big_op = make_stroke_op(
            [{"x": (i % 100) / 100, "y": (i % 50) / 50} for i in range(MAX_POINTS_PER_OP)]
        )
        oversized = [big_op] * 400
        self.assertGreater(snapshot_size_bytes(oversized), 512 * 1024)
        self.assertIsNotNone(check_snapshot_limits(oversized))


class DocumentTests(unittest.TestCase):
    def test_add_stroke_and_snapshot(self) -> None:
        document = CanvasDocument()
        ops = document.add_stroke([(0.1, 0.1), (0.2, 0.2)], "#FF0000", 4)
        self.assertEqual(1, len(ops))
        self.assertEqual(1, document.count)
        self.assertEqual(1, len(document.snapshot_strokes()))
        self.assertTrue(document.can_undo)

    def test_long_stroke_splits_into_ops(self) -> None:
        document = CanvasDocument()
        points = [{"x": (i % 500) / 500, "y": 0.5} for i in range(600)]
        ops = document.add_stroke(points)
        self.assertEqual(2, len(ops))
        self.assertEqual(2, document.count)

    def test_undo_redo(self) -> None:
        document = CanvasDocument()
        document.add_stroke([(0.1, 0.1)])
        document.add_stroke([(0.2, 0.2)])
        self.assertTrue(document.undo())
        self.assertEqual(1, document.count)
        self.assertTrue(document.can_redo)
        self.assertTrue(document.redo())
        self.assertEqual(2, document.count)
        self.assertFalse(document.redo())

    def test_clear_and_undo_clear(self) -> None:
        document = CanvasDocument()
        document.add_stroke([(0.1, 0.1)])
        document.clear()
        self.assertTrue(document.is_empty)
        self.assertTrue(document.undo())
        self.assertEqual(1, document.count)

    def test_apply_snapshot_replaces_and_resets_history(self) -> None:
        document = CanvasDocument()
        document.add_stroke([(0.1, 0.1)])
        document.apply_snapshot([make_clear_op(), make_stroke_op([(0.5, 0.5)])])
        self.assertEqual(1, document.count)
        self.assertFalse(document.can_undo)

    def test_apply_remote_op_clears_undo(self) -> None:
        document = CanvasDocument()
        document.add_stroke([(0.1, 0.1)])
        document.apply_remote_op(make_stroke_op([(0.2, 0.2)]))
        self.assertEqual(2, document.count)
        self.assertFalse(document.can_undo)

    def test_reset(self) -> None:
        document = CanvasDocument()
        document.add_stroke([(0.1, 0.1)])
        document.reset()
        self.assertTrue(document.is_empty)
        self.assertFalse(document.can_undo)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class RateLimiterTests(unittest.TestCase):
    def test_limit_30_per_second(self) -> None:
        clock = FakeClock()
        limiter = CanvasRateLimiter(30, 1.0, clock=clock)
        allowed = [limiter.allow() for _ in range(31)]
        self.assertEqual(30, sum(allowed))
        self.assertFalse(allowed[-1])
        self.assertGreater(limiter.wait_seconds(), 0)
        clock.now += 1.01
        self.assertTrue(limiter.allow())


if __name__ == "__main__":
    unittest.main()
