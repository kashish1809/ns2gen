"""Canvas geometry helpers. No GUI imports, so they can be unit tested."""
from __future__ import annotations

import math
from typing import Tuple

Seg = Tuple[float, float, float, float]


class Viewport:
    """Maps world coordinates (y up, like ns2/nam) to canvas pixels (y down)."""

    def __init__(self, world_w: float, world_h: float, canvas_w: float, canvas_h: float, pad: float = 30):
        self.ww, self.wh, self.pad = world_w, world_h, pad
        sx = (canvas_w - 2 * pad) / world_w if world_w > 0 else 1.0
        sy = (canvas_h - 2 * pad) / world_h if world_h > 0 else 1.0
        self.scale = max(min(sx, sy), 0.01)

    def to_canvas(self, x: float, y: float) -> Tuple[float, float]:
        return self.pad + x * self.scale, self.pad + (self.wh - y) * self.scale

    def to_world(self, cx: float, cy: float) -> Tuple[float, float]:
        return (cx - self.pad) / self.scale, self.wh - (cy - self.pad) / self.scale

    def clamp(self, x: float, y: float) -> Tuple[float, float]:
        return min(max(x, 0.0), self.ww), min(max(y, 0.0), self.wh)


def dist_point_segment(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def offset_segment(ax, ay, bx, by, d: float) -> Seg:
    """Shift a segment sideways by d pixels (positive = left of travel direction on screen)."""
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L == 0 or d == 0:
        return ax, ay, bx, by
    nx, ny = -dy / L * d, dx / L * d
    return ax + nx, ay + ny, bx + nx, by + ny


def trim_segment(ax, ay, bx, by, t: float) -> Seg:
    """Shorten a segment by t pixels at both ends (so arrows clear node circles)."""
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy)
    if L <= 2 * t or L == 0:
        return ax, ay, bx, by
    ux, uy = dx / L, dy / L
    return ax + ux * t, ay + uy * t, bx - ux * t, by - uy * t


def nice_step(scale: float, min_px: float = 40.0) -> float:
    """Smallest 'round' world step that is at least min_px pixels wide."""
    for step in (1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000):
        if step * scale >= min_px:
            return float(step)
    return 10000.0
