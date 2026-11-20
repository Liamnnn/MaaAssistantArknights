"""刷取进度持久化与统计。

所有统计数据都写在一个 JSON 文件里，进程被杀掉也能续跑；
每局结束都会落盘，异常退出最多丢一局。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

RunResult = Literal["win", "loss", "aborted", "unknown"]

STATE_VERSION = 1


@dataclass
class RunRecord:
    ts: float
    strategy: str
    result: RunResult
    seconds: float
    rounds: int = 0
    points: int = 0


@dataclass
class Progress:
    strategies: dict[str, int] = field(default_factory=dict)
    wins: int = 0
    runs: int = 0
    aborted: int = 0
    points: int = 0
    point_runs: int = 0
    history: list[RunRecord] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = STATE_VERSION

    # ---------- 查询 ----------

    def clears(self, strategy: str) -> int:
        return self.strategies.get(strategy, 0)

    def average_run_seconds(self, window: int = 20) -> float | None:
        recent = [r.seconds for r in self.history[-window:] if r.result in ("win", "loss") and r.seconds > 1]
        if not recent:
            return None
        return sum(recent) / len(recent)

    def win_rate(self, window: int | None = None) -> float | None:
        records = self.history[-window:] if window else self.history
        decided = [r for r in records if r.result in ("win", "loss")]
        if not decided:
            return None
        return sum(1 for r in decided if r.result == "win") / len(decided)

    def eta_seconds(self, remaining_runs: int, window: int = 20) -> float | None:
        avg = self.average_run_seconds(window)
        if avg is None:
            return None
        return avg * max(0, remaining_runs)

    # ---------- 写入 ----------

    def record(self, strategy: str, result: RunResult, seconds: float, rounds: int = 0) -> None:
        self.runs += 1
        if result == "win":
            self.wins += 1
            self.strategies[strategy] = self.clears(strategy) + 1
        elif result == "aborted":
            self.aborted += 1
        self.history.append(RunRecord(time.time(), strategy, result, round(seconds, 1), rounds))
        self.history = self.history[-500:]
        self.updated_at = time.time()

    def record_points(self, points: int) -> None:
        self.points += max(0, points)
        self.point_runs += 1
        self.updated_at = time.time()

    # ---------- 持久化 ----------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Progress":
        p = cls()
        p.strategies = {str(k): int(v) for k, v in (raw.get("strategies") or {}).items()}
        p.wins = int(raw.get("wins", 0))
        p.runs = int(raw.get("runs", 0))
        p.aborted = int(raw.get("aborted", 0))
        p.points = int(raw.get("points", 0))
        p.point_runs = int(raw.get("point_runs", 0))
        p.created_at = float(raw.get("created_at", time.time()))
        p.updated_at = float(raw.get("updated_at", time.time()))
        p.history = [
            RunRecord(
                ts=float(h.get("ts", 0)),
                strategy=str(h.get("strategy", "")),
                result=h.get("result", "unknown"),
                seconds=float(h.get("seconds", 0)),
                rounds=int(h.get("rounds", 0)),
                points=int(h.get("points", 0)),
            )
            for h in (raw.get("history") or [])
            if isinstance(h, dict)
        ]
        return p

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> "Progress":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ( json.JSONDecodeError, OSError):
            # 状态文件损坏时备份，避免直接覆盖掉排查线索
            try:
                path.replace(path.with_suffix(path.suffix + ".corrupt"))
            except OSError:
                pass
            return cls()
        return cls.from_dict(raw)


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"
