"""OCR 封装。

默认使用 RapidOCR（onnxruntime，随 pip 包带模型，中英文和数字都够用）。
识别结果统一为 1280x720 基准坐标，和模板匹配的坐标系一致。

如果没装 OCR 依赖：刷点数（points 模式）仍然可用，badges 模式会明确报错。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .geometry import BASE_HEIGHT, BASE_WIDTH, Rect
from .vision import Screenshot

_INSTALL_HINT = (
    "缺少 OCR 依赖：`pip install rapidocr-onnxruntime`（或 `rapidocr`），"
    "badges 模式需要 OCR 读取商店/结算/策略名；只想刷点数可用 --mode points"
)


@dataclass(frozen=True)
class TextLine:
    text: str
    rect: Rect  # 1280x720 基准坐标
    score: float = 1.0

    @property
    def center(self):
        return self.rect.center


class OcrUnavailable(RuntimeError):
    pass


class OcrEngine:
    def __init__(self, min_score: float = 0.55) -> None:
        self.min_score = min_score
        self._engine = None

    # ---------- 懒加载 ----------

    def _load(self):
        if self._engine is not None:
            return self._engine
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            return self._engine
        except ImportError:
            pass
        try:
            from rapidocr import RapidOCR  # type: ignore

            self._engine = RapidOCR()
            return self._engine
        except ImportError as exc:  # pragma: no cover - 依赖缺失路径
            raise OcrUnavailable(_INSTALL_HINT) from exc

    @property
    def available(self) -> bool:
        try:
            self._load()
            return True
        except OcrUnavailable:
            return False

    # ---------- 识别 ----------

    def read(self, shot: Screenshot, rect: Rect | None = None) -> list[TextLine]:
        engine = self._load()
        if rect is None:
            image = shot.base
            offset_x = offset_y = 0
        else:
            r = rect.clamp((BASE_WIDTH, BASE_HEIGHT))
            image = shot.base[r.y : r.bottom, r.x : r.right]
            offset_x, offset_y = r.x, r.y
        if image.size == 0:
            return []
        raw = engine(image)
        rows = _normalize_result(raw)
        lines: list[TextLine] = []
        for box, text, score in rows:
            text = str(text).strip()
            if not text or score < self.min_score:
                continue
            x0 = min(p[0] for p in box) + offset_x
            y0 = min(p[1] for p in box) + offset_y
            x1 = max(p[0] for p in box) + offset_x
            y1 = max(p[1] for p in box) + offset_y
            lines.append(TextLine(text, Rect(int(x0), int(y0), int(x1 - x0), int(y1 - y0)), float(score)))
        lines.sort(key=lambda line: (line.rect.y, line.rect.x))
        return lines

    def read_text(self, shot: Screenshot, rect: Rect | None = None) -> str:
        return "".join(line.text for line in self.read(shot, rect))

    def contains(self, shot: Screenshot, rect: Rect, keyword: str) -> bool:
        return any(keyword in line.text for line in self.read(shot, rect))


def _normalize_result(raw) -> list:
    """兼容 rapidocr_onnxruntime（返回 (result, elapse)）与 rapidocr（返回对象）。"""
    if raw is None:
        return []
    if isinstance(raw, tuple):
        raw = raw[0]
    if raw is None:
        return []
    # 新版 rapidocr 返回带 .boxes/.txts/.scores 的对象
    if hasattr(raw, "boxes") and hasattr(raw, "txts"):
        boxes = getattr(raw, "boxes")
        txts = getattr(raw, "txts")
        scores = getattr(raw, "scores")
        result = []
        for box, text, score in zip(boxes or [], txts or [], scores or []):
            result.append((_as_points(box), text, float(score)))
        return result
    # 旧版：[[box, text, score], ...]
    result = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            result.append((_as_points(item[0]), item[1], float(item[2])))
    return result


def _as_points(box) -> Sequence[Sequence[float]]:
    # numpy array / list 都可能有嵌套层级
    if hasattr(box, "tolist"):
        box = box.tolist()
    points = []
    for point in box:
        if hasattr(point, "tolist"):
            point = point.tolist()
        points.append((float(point[0]), float(point[1])))
    return points


# ---------------- 文本规整 ----------------

_DIGIT_TRANS = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "D": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "Z": "2",
        "z": "2",
        "G": "6",
        "g": "9",
        "T": "7",
    }
)


def normalize_digits(text: str) -> str:
    text = text.translate(_DIGIT_TRANS)
    return re.sub(r"[^\d]", "", text)


def parse_int(text: str, lo: int = 0, hi: int = 9999) -> int | None:
    digits = normalize_digits(text)
    if not digits or len(digits) > 4:
        return None
    value = int(digits)
    if value < lo or value > hi:
        return None
    return value


def has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)
