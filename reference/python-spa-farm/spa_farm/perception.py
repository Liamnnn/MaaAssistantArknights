"""场景识别：把一帧截图归类成卫戍协议的某个界面。

顺序按「先便宜后昂贵」：模板匹配（毫秒级）→ 小 ROI OCR → 全屏 OCR（只在未知时）。
战斗回合与过场落在 UNKNOWN 是正常的，runner 会按等待处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from . import screens as S
from .geometry import Rect
from .ocr import OcrEngine, TextLine
from .vision import Match, Matcher, Screenshot


@dataclass
class Observation:
    scene: S.Scene
    shot: Screenshot
    matches: dict[str, Match] = field(default_factory=dict)
    texts: list[TextLine] = field(default_factory=list)
    result: str | None = None  # 结算页："win" / "loss"

    @property
    def in_battle(self) -> bool:
        return self.scene in (S.Scene.BATTLE, S.Scene.PREP)


class Perception:
    def __init__(self, matcher: Matcher, ocr: OcrEngine | None) -> None:
        self.matcher = matcher
        self.ocr = ocr

    # ---------- 基础 ----------

    def find(self, shot: Screenshot, alias: str, roi: Rect | None = None) -> Match | None:
        return self.matcher.find(shot, alias, roi)

    def _ocr_contains(self, shot: Screenshot, rect: Rect, keywords: Sequence[str]) -> bool:
        if self.ocr is None:
            return False
        lines = self.ocr.read(shot, rect)
        return any(any(k in line.text for k in keywords) for line in lines)

    def _full_text(self, shot: Screenshot) -> list[TextLine]:
        if self.ocr is None:
            return []
        try:
            return self.ocr.read(shot)
        except Exception:  # OCR 后端异常不应让整局崩掉
            return []

    # ---------- 主判定 ----------

    def observe(self, shot: Screenshot) -> Observation:
        matches: dict[str, Match] = {}

        def match(alias: str, roi: Rect | None = None) -> bool:
            found = self.matcher.find(shot, alias, roi)
            if found:
                matches[alias] = found
            return found

        # 1. 结算页（返回主页按钮）
        if match("return_home"):
            return Observation(S.Scene.SETTLEMENT, shot, matches, result=self.read_result(shot))

        # 2. 自选编队 / 确认本局信息：两者共用「准备就绪」按钮模板
        if match("custom_squad"):
            return Observation(S.Scene.SQUAD, shot, matches)

        # 3. 策略选择页
        if match("goliath") or match("confirm_select"):
            return Observation(S.Scene.STRATEGY, shot, matches)

        # 4. 确认准备弹窗（会遮挡准备按钮，必须先判）
        if self.ocr is not None:
            popup_lines = self.ocr.read(shot, S.CONFIRM_READY)
            if any("确认" in line.text for line in popup_lines):
                return Observation(S.Scene.POPUP, shot, matches, popup_lines)

        # 5. 回合休整（准备就绪）
        if self.ocr is not None:
            lines = self.ocr.read(shot, S.READY_BUTTON)
            if any(any(k in line.text for k in ("准备就绪", "准备", "就绪")) for line in lines):
                return Observation(S.Scene.PREP, shot, matches, lines)

        # 6. 活动主界面
        if match("enter_quick"):
            return Observation(S.Scene.ACTIVITY, shot, matches)

        # 7. 未知：全屏 OCR 找悬赏/战斗/活动内通用按钮
        texts = self._full_text(shot)
        if texts:
            joined = "".join(line.text for line in texts)
            bounty_hits = sum(1 for line in texts if "悬赏" in line.text)
            if bounty_hits >= 2:
                return Observation(S.Scene.BOUNTY, shot, matches, texts)
            if any(word in joined for word in ("战斗中", "回合", "倍速", "放弃模拟")):
                return Observation(S.Scene.BATTLE, shot, matches, texts)

        return Observation(S.Scene.UNKNOWN, shot, matches, texts)

    # ---------- 结算 ----------

    def read_result(self, shot: Screenshot) -> str | None:
        if self.ocr is None:
            return None
        for line in self.ocr.read(shot, S.SETTLEMENT_TITLE):
            text = line.text.replace(" ", "")
            if "模拟完成" in text or text == "完成":
                return "win"
            if "模拟中断" in text or "中断" in text:
                return "loss"
        return None
