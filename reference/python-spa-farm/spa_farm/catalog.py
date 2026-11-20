"""赛季数据（策略、盟约、干员）与名称匹配。

数据来自 Dr-hydra/MaaAssistantArknights 的 `resource/SPAFarm/`（游戏数据经 torappu/PRTS），
由 `tools/import_spafarm_data.py` 裁剪成这个工具需要的字段，见 data/season_regulation.json。

用途：
- 不再依赖 `discover` 才能拿到策略名单：默认就有当前赛季 31 个可用策略；
- OCR 策略名有错字/引号时，用归一化 + 模糊匹配选中正确策略；
- 提供购买优先级的兜底（按费用/等阶），以及 77 名“叠层”干员名单。
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DATA_PATH = Path(__file__).with_name("data") / "season_regulation.json"

_PUNCT = re.compile(r"[\s【】\[\]「」『』“”\"'·・,，。.!！?？:：;；()（）]")


def normalize_name(text: str) -> str:
    return _PUNCT.sub("", text).casefold()


@dataclass(frozen=True)
class StrategyInfo:
    id: str
    name: str
    type: str
    available: bool


@dataclass(frozen=True)
class BondInfo:
    id: str
    name: str
    core: bool


@dataclass(frozen=True)
class ChessInfo:
    name: str
    tier: int
    price: int
    bonds: tuple[str, ...] = ()
    stacker: bool = False


@dataclass(frozen=True)
class GoalSpec:
    id: str
    label: str
    bonds: tuple[str, ...]
    layers: int


@dataclass
class Etchings:
    total_wins: int = 60
    strategies_with_badge: int = 20
    per_strategy_clears: int = 3
    core_bond_layers: int = 300
    prerequisite_badges: int = 9


@dataclass
class SeasonCatalog:
    meta: dict = field(default_factory=dict)
    strategies: list[StrategyInfo] = field(default_factory=list)
    bonds: list[BondInfo] = field(default_factory=list)
    chess: list[ChessInfo] = field(default_factory=list)
    goals: list[GoalSpec] = field(default_factory=list)
    etchings: Etchings = field(default_factory=Etchings)

    # ---------- 加载 ----------

    @classmethod
    def load(cls, path: str | Path | None = None) -> "SeasonCatalog":
        raw = json.loads(Path(path or DATA_PATH).read_text(encoding="utf-8"))
        catalog = cls(
            meta=raw.get("meta") or {},
            strategies=[
                StrategyInfo(s["id"], s["name"], s.get("type", "GENERAL"), bool(s.get("available")))
                for s in raw.get("strategies") or []
            ],
            bonds=[BondInfo(b["id"], b["name"], bool(b.get("core"))) for b in raw.get("bonds") or []],
            chess=[
                ChessInfo(c["name"], int(c.get("tier", 1)), int(c.get("price", 0)), tuple(c.get("bonds") or []), bool(c.get("stacker")))
                for c in raw.get("chess") or []
            ],
            goals=[
                GoalSpec(g["id"], g.get("label", ""), tuple(g.get("bonds") or []), int(g.get("layers", 0)))
                for g in raw.get("goals") or []
            ],
        )
        e = raw.get("etchings") or {}
        catalog.etchings = Etchings(
            total_wins=int(e.get("total_wins", 60)),
            strategies_with_badge=int(e.get("strategies_with_badge", 20)),
            per_strategy_clears=int(e.get("per_strategy_clears", 3)),
            core_bond_layers=int(e.get("core_bond_layers", 300)),
            prerequisite_badges=int(e.get("prerequisite_badges", 9)),
        )
        return catalog

    # ---------- 查询 ----------

    @property
    def available_strategies(self) -> list[StrategyInfo]:
        return [s for s in self.strategies if s.available]

    def default_strategies(self, limit: int | None = None) -> list[str]:
        names = [s.name for s in self.available_strategies]
        return names[:limit] if limit and limit > 0 else names

    def strategy(self, name: str) -> StrategyInfo | None:
        target = normalize_name(name)
        for s in self.strategies:
            if normalize_name(s.name) == target:
                return s
        return None

    def match_strategy(self, text: str) -> StrategyInfo | None:
        """把 OCR 读到的文本匹配到策略（优先可用策略）。

        顺序：归一化全等 → 互相包含 → difflib 相似度 ≥ 0.75。
        """
        target = normalize_name(text)
        if not target:
            return None
        # 先匹配可用策略，再退到全部（unavailable 的策略页面上仍可能被 OCR 读到）
        candidates = self.available_strategies + [s for s in self.strategies if not s.available]
        for s in candidates:
            if normalize_name(s.name) == target:
                return s
        for s in candidates:
            key = normalize_name(s.name)
            if key and (key in target or target in key) and min(len(key), len(target)) >= 2:
                return s
        names = [normalize_name(s.name) for s in candidates]
        best = difflib.get_close_matches(target, names, n=1, cutoff=0.75)
        if best:
            index = names.index(best[0])
            return candidates[index]
        return None

    @property
    def chess_by_name(self) -> dict[str, ChessInfo]:
        result: dict[str, ChessInfo] = {}
        for c in self.chess:
            result.setdefault(c.name, c)
        return result

    @property
    def stacker_names(self) -> set[str]:
        return {c.name for c in self.chess if c.stacker}

    def goal(self, goal_id: str) -> GoalSpec | None:
        for g in self.goals:
            if g.id == goal_id:
                return g
        return None

    def is_known_oper(self, name: str) -> bool:
        if not name:
            return False
        key = normalize_name(name)
        return any(normalize_name(c.name) == key for c in self.chess) or any(
            normalize_name(b.name) == key for b in self.bonds
        )

    def chess_priority(self) -> list[str]:
        """按 等阶降序、费用降序 的兜底购买顺序（不含重复名）。"""
        ordered = sorted(self.chess, key=lambda c: (c.tier, c.price), reverse=True)
        return _dedupe(c.name for c in ordered)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
