"""坐标换算。

MAA 的卫戍协议任务资源（以及本工具内置的 ROI）都以 1280x720 为基准。
界面识别统一在缩放到 1280x720 的截图上进行，点击/滑动时再换算回真实分辨率。
这样同一份坐标可以同时适配 1280x720、1600x900、1920x1080 的模拟器。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

BASE_WIDTH = 1280
BASE_HEIGHT = 720


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def scaled(self, size: tuple[int, int]) -> "Point":
        sx, sy = _factors(size)
        return Point(round(self.x * sx), round(self.y * sy))

    def as_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)

    def distance_to(self, other: "Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> Point:
        return Point(self.x + self.w // 2, self.y + self.h // 2)

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def scaled(self, size: tuple[int, int]) -> "Rect":
        sx, sy = _factors(size)
        return Rect(
            round(self.x * sx),
            round(self.y * sy),
            max(1, round(self.w * sx)),
            max(1, round(self.h * sy)),
        )

    def offset(self, dx: int, dy: int) -> "Rect":
        """相对偏移（用于“卡牌中心 + 固定偏移”这类 ROI）。"""
        return Rect(self.x + dx, self.y + dy, self.w, self.h)

    def moved_to(self, x: int, y: int) -> "Rect":
        return Rect(x, y, self.w, self.h)

    def contains(self, point: Point) -> bool:
        return self.x <= point.x < self.right and self.y <= point.y < self.bottom

    def clamp(self, size: tuple[int, int]) -> "Rect":
        """裁到画面内，避免 OpenCV ROI 越界。"""
        x0 = max(0, min(self.x, size[0] - 1))
        y0 = max(0, min(self.y, size[1] - 1))
        x1 = max(x0 + 1, min(self.right, size[0]))
        y1 = max(y0 + 1, min(self.bottom, size[1]))
        return Rect(x0, y0, x1 - x0, y1 - y0)

    def to_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]

    @classmethod
    def from_list(cls, values: Sequence[int]) -> "Rect":
        if len(values) != 4:
            raise ValueError(f"rect needs 4 values, got {values!r}")
        return cls(*(int(v) for v in values))


def roi(x: int, y: int, w: int, h: int) -> Rect:
    return Rect(x, y, w, h)


def _factors(size: tuple[int, int]) -> tuple[float, float]:
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError(f"invalid screen size: {size!r}")
    return size[0] / BASE_WIDTH, size[1] / BASE_HEIGHT


def scale_point(point: Point, size: tuple[int, int]) -> Point:
    return point.scaled(size)


def scale_rect(rect: Rect, size: tuple[int, int]) -> Rect:
    return rect.scaled(size)
