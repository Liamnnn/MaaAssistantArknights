"""截图、模板匹配与颜色判定。

设计要点：
- 所有识别都在 1280x720 基准图上做，模板只需要一份；
- 模板直接从本机 MAA 安装目录读取，不复制、不修改 MAA；
- cv2/numpy 延迟导入，`spa-farm check` 能在缺依赖时给出可读的错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .geometry import BASE_HEIGHT, BASE_WIDTH, Point, Rect
from .screens import TEMPLATES

try:  # pragma: no cover - 依赖缺失时在运行时提示
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:  # pragma: no cover
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

GREEN_LOWER = (35, 100, 100)
GREEN_UPPER = (85, 255, 255)
GOLD_LOWER = (8, 120, 150)
GOLD_UPPER = (35, 255, 255)
CYAN_LOWER = (70, 40, 150)
CYAN_UPPER = (140, 255, 255)


class VisionUnavailable(RuntimeError):
    pass


def require_cv() -> None:
    if cv2 is None or np is None:
        raise VisionUnavailable(
            "缺少 opencv/numpy：请先 `pip install -r requirements.txt`（opencv-python-headless、numpy）"
        )


@dataclass(frozen=True)
class Match:
    alias: str
    score: float
    rect: Rect  # 1280x720 基准坐标


class Screenshot:
    """一帧截图，同时保存原始分辨率与 720p 基准图。"""

    def __init__(self, bgr: "np.ndarray") -> None:
        if np is None:
            raise VisionUnavailable("缺少 numpy：请先 `pip install -r requirements.txt`")
        self.raw = bgr
        height, width = bgr.shape[:2]
        self.size = (width, height)
        self.scale = (width / BASE_WIDTH, height / BASE_HEIGHT)
        if (width, height) == (BASE_WIDTH, BASE_HEIGHT):
            self.base = bgr
        else:
            require_cv()
            self.base = cv2.resize(bgr, (BASE_WIDTH, BASE_HEIGHT), interpolation=cv2.INTER_AREA)

    @property
    def width(self) -> int:
        return self.size[0]

    @property
    def height(self) -> int:
        return self.size[1]

    def crop(self, rect: Rect) -> "np.ndarray":
        r = rect.clamp((BASE_WIDTH, BASE_HEIGHT))
        return self.base[r.y : r.bottom, r.x : r.right]

    def to_actual(self, point: Point) -> Point:
        return point.scaled(self.size)


class Matcher:
    def __init__(self, template_dirs: Sequence[Path], threshold: float = 0.80) -> None:
        require_cv()
        self.template_dirs = [Path(p) for p in template_dirs]
        self.threshold = threshold
        self._cache: dict[str, "np.ndarray | None"] = {}

    # ---------- 模板定位 ----------

    def _find_template(self, alias: str) -> Path | None:
        names = TEMPLATES.get(alias, (f"{alias}.png",))
        for directory in self.template_dirs:
            for name in names:
                candidate = directory / name
                if candidate.is_file():
                    return candidate
            # 兼容模板被放在子目录里的发行版
            for name in names:
                for candidate in directory.rglob(name):
                    return candidate
        return None

    def _load(self, alias: str) -> "np.ndarray | None":
        if alias in self._cache:
            return self._cache[alias]
        path = self._find_template(alias)
        image = None
        if path is not None:
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None and image.shape[1] > BASE_WIDTH:
                image = cv2.resize(image, (BASE_WIDTH, BASE_HEIGHT), interpolation=cv2.INTER_AREA)
        self._cache[alias] = image
        return image

    def available(self, alias: str) -> bool:
        return self._load(alias) is not None

    def missing(self) -> list[str]:
        return [alias for alias in TEMPLATES if not self.available(alias)]

    # ---------- 匹配 ----------

    def find(self, shot: Screenshot, alias: str, roi: Rect | None = None, threshold: float | None = None) -> Match | None:
        template = self._load(alias)
        if template is None:
            return None
        base = shot.base
        offset_x = 0
        offset_y = 0
        if roi is not None:
            region = roi.clamp((BASE_WIDTH, BASE_HEIGHT))
            if region.w < template.shape[1] or region.h < template.shape[0]:
                # ROI 比模板还小：退化为整图匹配后再用 ROI 过滤
                region = Rect(0, 0, BASE_WIDTH, BASE_HEIGHT)
            base = base[region.y : region.bottom, region.x : region.right]
            offset_x, offset_y = region.x, region.y
        result = cv2.matchTemplate(base, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        limit = self.threshold if threshold is None else threshold
        if max_val < limit:
            return None
        h, w = template.shape[:2]
        return Match(alias, float(max_val), Rect(offset_x + max_loc[0], offset_y + max_loc[1], w, h))

    def all(self, shot: Screenshot, alias: str, roi: Rect | None = None, threshold: float | None = None) -> list[Match]:
        """同一模板的多处命中（策略网格等），按分数降序。"""
        template = self._load(alias)
        if template is None:
            return []
        base = shot.base
        offset_x = offset_y = 0
        if roi is not None:
            region = roi.clamp((BASE_WIDTH, BASE_HEIGHT))
            base = base[region.y : region.bottom, region.x : region.right]
            offset_x, offset_y = region.x, region.y
        result = cv2.matchTemplate(base, template, cv2.TM_CCOEFF_NORMED)
        limit = self.threshold if threshold is None else threshold
        ys, xs = np.where(result >= limit)
        h, w = template.shape[:2]
        matches = [
            Match(alias, float(result[y, x]), Rect(offset_x + int(x), offset_y + int(y), w, h)) for y, x in zip(ys, xs)
        ]
        matches.sort(key=lambda m: m.score, reverse=True)
        return _dedupe_matches(matches, min_distance=max(8, w // 2))


def _dedupe_matches(matches: list[Match], min_distance: int) -> list[Match]:
    kept: list[Match] = []
    for match in matches:
        center = match.rect.center
        if all(abs(center.x - k.rect.center.x) > min_distance or abs(center.y - k.rect.center.y) > min_distance for k in kept):
            kept.append(match)
    return kept


# ---------------- 颜色 ----------------

def color_ratio(image: "np.ndarray", rect: Rect, lower: tuple[int, int, int], upper: tuple[int, int, int]) -> float:
    """HSV 颜色占比。rect 为传入图像坐标系（与调用方一致）。"""
    require_cv()
    h, w = image.shape[:2]
    r = rect.clamp((w, h))
    patch = image[r.y : r.bottom, r.x : r.right]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8))
    return float(np.count_nonzero(mask)) / mask.size


def is_green(shot: Screenshot, point: Point, radius: int = 10) -> bool:
    rect = Rect(point.x - radius, point.y - radius, radius * 2, radius * 2)
    return color_ratio(shot.base, rect, GREEN_LOWER, GREEN_UPPER) > 0.8


def has_gold_badge(shot: Screenshot, center: Point) -> bool:
    from .screens import GOLD_BADGE_OFFSET

    rect = Rect(center.x + GOLD_BADGE_OFFSET.x, center.y + GOLD_BADGE_OFFSET.y, GOLD_BADGE_OFFSET.w, GOLD_BADGE_OFFSET.h)
    return color_ratio(shot.base, rect, GOLD_LOWER, GOLD_UPPER) > 0.10


def has_color_badge(shot: Screenshot, center: Point) -> bool:
    from .screens import COLOR_BADGE_OFFSET

    rect = Rect(center.x + COLOR_BADGE_OFFSET.x, center.y + COLOR_BADGE_OFFSET.y, COLOR_BADGE_OFFSET.w, COLOR_BADGE_OFFSET.h)
    return color_ratio(shot.base, rect, CYAN_LOWER, CYAN_UPPER) > 0.15 and color_ratio(
        shot.base, rect, GOLD_LOWER, GOLD_UPPER
    ) < 0.05


# ---------------- 图像差分（备战席定位） ----------------

def find_new_dark_square(before: "np.ndarray", after: "np.ndarray", scan: Rect) -> Rect | None:
    """买卡后备战席新增的深色等阶方牌。

    返回方牌外接矩形（scan 所在图像坐标系），失败返回 None。
    """
    require_cv()
    h = min(before.shape[0], after.shape[0])
    w = min(before.shape[1], after.shape[1])
    r = scan.clamp((w, h))
    b = cv2.cvtColor(before[r.y : r.bottom, r.x : r.right], cv2.COLOR_BGR2GRAY)
    a = cv2.cvtColor(after[r.y : r.bottom, r.x : r.right], cv2.COLOR_BGR2GRAY)
    diff = cv2.subtract(b, a)
    _, mask = cv2.threshold(diff, 40, 255, cv2.THRESH_BINARY)
    if cv2.countNonZero(mask) == 0:
        return None
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (10, 10)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Rect | None = None
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < 20 or ch < 20:
            continue
        if best is None or cw * ch > best.w * best.h:
            best = Rect(r.x + x, r.y + y, cw, ch)
    return best


def template_dirs(maa_dir: str | Path | None) -> list[Path]:
    if not maa_dir:
        return []
    root = Path(maa_dir)
    candidates = [
        root / "resource" / "template" / "StrongholdProtocol",
        root / "resource" / "template" / "MiniGame" / "SPA",
    ]
    return [p for p in candidates if p.is_dir()]
