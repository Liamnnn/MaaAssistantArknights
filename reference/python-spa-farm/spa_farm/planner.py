"""角标/蚀刻章进度与刷取计划。

把“要刷哪些策略、每个刷几次、总共多少胜”从流程代码里独立出来，
这样可以用纯逻辑单元测试覆盖，也方便以后接入“最少局数”调度。

“拿满蚀刻章”的最优解不是刷完所有可用策略：
规程要求「20 个策略获得普通标识（3 次通关）」+「60 胜」，
20×3 正好 60 胜，所以只刷 20 个策略即可；多刷的策略纯属浪费。
`strategy_limit` 就是用来卡这个上限的。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PlanStatus:
    strategy: str | None
    clears: int
    target: int
    wins: int
    total_wins: int
    done: bool
    remaining_runs: int
    completed_strategies: int
    required_strategies: int

    def summary(self) -> str:
        if self.done:
            return f"全部目标已完成（{self.completed_strategies}/{self.required_strategies} 策略，{self.wins}/{self.total_wins} 胜）"
        if self.strategy is None:
            return f"策略目标已完成，但总胜场 {self.wins}/{self.total_wins}"
        return (
            f"当前策略 {self.strategy}：{self.clears}/{self.target}；"
            f"策略 {self.completed_strategies}/{self.required_strategies}；"
            f"总胜场 {self.wins}/{self.total_wins}；预计还需 {self.remaining_runs} 局"
        )


class BadgePlan:
    """按配置顺序逐个刷满策略，同时满足总胜场目标。

    strategy_limit > 0 时只取前 N 个策略（默认 20，对应蚀刻章要求）；
    0 表示不限制（刷完列表里的全部策略）。
    """

    def __init__(
        self,
        strategies: list[str],
        per_strategy_clears: int,
        total_wins: int,
        strategy_limit: int = 0,
    ) -> None:
        unique: list[str] = []
        for name in strategies:
            if name and name not in unique:
                unique.append(name)
        self.strategy_limit = max(0, strategy_limit)
        self.strategies = unique[: self.strategy_limit] if self.strategy_limit else unique
        self.per_strategy_clears = max(0, per_strategy_clears)
        self.total_wins = max(0, total_wins)

    # ---------- 查询 ----------

    def completed_strategies(self, clears: Mapping[str, int]) -> int:
        return sum(1 for n in self.strategies if clears.get(n, 0) >= self.per_strategy_clears)

    def _completed_enough(self, clears: Mapping[str, int]) -> bool:
        if not self.strategies:
            return self.total_wins <= 0
        return self.completed_strategies(clears) >= len(self.strategies)

    def next_strategy(self, clears: Mapping[str, int], wins: int) -> str | None:
        """返回下一个要刷的策略。

        优先按配置顺序补足未完成的策略；所有策略满次后若总胜场还不够，
        选通关次数最少的策略继续补胜场（保持各策略次数大致均衡）。
        """
        if not self.strategies:
            return None
        for name in self.strategies:
            if clears.get(name, 0) < self.per_strategy_clears:
                return name
        if wins < self.total_wins:
            return min(self.strategies, key=lambda n: (clears.get(n, 0), self.strategies.index(n)))
        return None

    def is_complete(self, clears: Mapping[str, int], wins: int) -> bool:
        if self.total_wins > 0 and wins < self.total_wins:
            return False
        return self._completed_enough(clears)

    def remaining_runs(self, clears: Mapping[str, int], wins: int) -> int:
        deficits = sum(
            max(0, self.per_strategy_clears - clears.get(n, 0)) for n in self.strategies
        )
        return max(deficits, max(0, self.total_wins - wins))

    def status(self, clears: Mapping[str, int], wins: int) -> PlanStatus:
        strategy = self.next_strategy(clears, wins)
        current = clears.get(strategy, 0) if strategy else 0
        return PlanStatus(
            strategy=strategy,
            clears=current,
            target=self.per_strategy_clears,
            wins=wins,
            total_wins=self.total_wins,
            done=self.is_complete(clears, wins),
            remaining_runs=self.remaining_runs(clears, wins),
            completed_strategies=self.completed_strategies(clears),
            required_strategies=len(self.strategies),
        )

    def validate(self) -> list[str]:
        problems: list[str] = []
        if not self.strategies:
            problems.append("没有配置任何策略：先运行 `spa-farm discover` 或在配置里填 targets.strategies")
        if self.per_strategy_clears <= 0 and self.total_wins <= 0:
            problems.append("per_strategy_clears 与 total_wins 都为 0，没有可刷的目标")
        return problems
