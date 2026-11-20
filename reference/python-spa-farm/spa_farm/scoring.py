"""购买评分（参考 Dr-hydra fork 的 goal / 盟约机制）。

fork 的 `apply_goal_bonds()` 会按目标切换“核心盟约”：
medal → {精准, 奥术}；task-N → 对应的 2~3 个盟约。
它的买卡评分（`score_shop_cards`）会对核心盟约、叠层干员、合成进度加权。

这里把同样的思路做成一个可测试的纯函数：
- 目标盟约的干员优先；
- 带「层数+」特质、且命中目标盟约的叠层干员再优先；
- 已有 1/2 张同名卡时给合成进度加权；
- 其余情况回落到“购买权重表 / 等阶 / 费用”。
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import SeasonCatalog
from .config import ShopPolicy

MEDAL_BONDS = ("精准", "奥术")
LAYER_BONDS = ("奇迹", "远见", "投资人")


@dataclass(frozen=True)
class GoalFocus:
    goal: str
    label: str
    bonds: frozenset[str]
    is_task: bool  # task-N / layer-300：目标盟约优先于泛用强度

    @property
    def active(self) -> bool:
        return bool(self.bonds)


def build_focus(catalog: SeasonCatalog, goal: str, override: list[str] | None = None) -> GoalFocus:
    goal = (goal or "medal").strip()
    if override:
        return GoalFocus(goal, "自定义盟约", frozenset(override), True)
    if goal == "medal":
        return GoalFocus(goal, "策略徽章（精准/奥术）", frozenset(MEDAL_BONDS), False)
    if goal == "layer-300":
        return GoalFocus(goal, "300 层（奇迹/远见/投资人）", frozenset(LAYER_BONDS), True)
    spec = catalog.goal(goal)
    if spec is not None:
        return GoalFocus(goal, spec.label, frozenset(spec.bonds), True)
    return GoalFocus(goal, "未指定（按强度）", frozenset(), False)


def oper_score(
    catalog: SeasonCatalog,
    policy: ShopPolicy,
    focus: GoalFocus,
    name: str,
    tier: int,
    purchases: int = 0,
) -> int:
    """返回购买优先级分数，越大越先买。"""
    info = catalog.chess_by_name.get(name)
    bonds = set(info.bonds) if info else set()
    price = info.price if info else 0
    stacker = bool(info and info.stacker)
    hits = len(bonds & set(focus.bonds))
    duplicate_bonus = 120 if purchases % 3 == 2 else 60 if purchases % 3 == 1 else 0

    # 目标盟约模式：命中盟约的干员压过泛用强度，叠层干员再抬一档
    if focus.is_task and hits:
        return 1000 + 150 * hits + (300 if stacker else 0) + tier * 5 + duplicate_bonus

    if name in policy.priorities:
        base = 1000 - policy.priorities.index(name)
    else:
        base = tier * 20 + price
    if hits:
        base += 120 * hits
    if stacker and hits:
        base += 100
    return base + duplicate_bonus


def rank_cards(
    catalog: SeasonCatalog,
    policy: ShopPolicy,
    focus: GoalFocus,
    cards,
    purchases: dict[str, int] | None = None,
) -> list:
    """按分数降序返回卡牌（不修改入参）。"""
    purchases = purchases or {}
    return sorted(
        cards,
        key=lambda c: oper_score(catalog, policy, focus, c.name, c.tier, purchases.get(c.name, 0)),
        reverse=True,
    )
