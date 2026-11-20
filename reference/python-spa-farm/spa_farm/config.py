"""配置模型与默认值。

配置文件是 JSON（不引入 PyYAML 依赖），命令行参数优先于配置文件。
坐标、部署格位沿用 MAA 卫戍协议任务资源的 1280x720 基准。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .geometry import Point

DEFAULT_PURCHASE_PRIORITY = [
    # 来源：MAA PR #19325 的 resource/stronghold_protocol/regulation/purchase.json
    # （卫戍协议·规程 三期）。留作默认值，赛季变化时可用配置文件覆盖。
    "塔露拉",
    "维什戴尔",
    "斩业星熊",
    "予愿安洁莉娜",
    "新约能天使",
    "凯尔希·思衡托",
    "望",
    "圣聆初雪",
    "逻各斯",
    "蕾缪安",
    "贝洛内",
    "冻河",
    "赤刃明霄陈",
    "结城理",
    "史尔特尔",
    "耀骑士临光",
    "克莱门莎",
    "锏",
    "帕拉斯",
    "真言",
    "烛煌",
    "艾丽妮",
    "薇薇安娜",
    "维娜·维多利亚",
    "乌尔比安",
    "棘刺",
    "怒潮凛冬",
    "迷迭香",
    "鸿雪",
    "佩佩",
    "隐德来希",
    "酒神",
]

DEFAULT_SAFE_KEYS = [
    "维什戴尔",
    "望",
    "新约能天使",
    "圣聆初雪",
    "蕾缪安",
    "逻各斯",
    "冻河",
    "真言",
    "烛煌",
    "迷迭香",
    "鸿雪",
    "酒神",
]

DEFAULT_HEALERS = [
    "褐果",
    "莎草",
    "哈洛德",
    "瑰盐",
    "乌啾",
    "风絮",
    "流明",
    "夜莺",
    "华法琳",
    "纯烬艾雅法拉",
    "Mon3tr",
    "Touch",
]

DEFAULT_DPS = [
    "怒潮凛冬",
    "艾丽妮",
    "棘刺",
    "佩佩",
    "圣聆初雪",
    "乌尔比安",
    "薇薇安娜",
    "贝洛内",
    "维娜·维多利亚",
    "迷迭香",
    "鸿雪",
    "阿米娅",
    "赤刃明霄陈",
    "司霆惊蛰",
    "维什戴尔",
    "斩业星熊",
    "丰川祥子",
    "结城理",
    "凛御银灰",
    "歌蕾蒂娅",
    "Sharp",
    "领主·Sharp",
    "Pith",
    "Stormeye",
    "预备干员-近卫",
    "预备干员-术师",
    "引星棘刺",
    "克莱门莎",
    "耀骑士临光",
    "荒芜拉普兰德",
    "逻各斯",
    "真言",
    "史尔特尔",
    "锏",
    "塔露拉",
    "夕",
    "蕾缪安",
    "帕拉斯",
    "望",
    "塑心",
]


@dataclass
class Targets:
    """刷取目标。

    strategies 为空时无法进入 badges 模式，可先用 `spa-farm discover` 抓取策略名。
    per_strategy_clears: 每个策略需要通关的次数（角标 3 次、镀层 6 次）。
    total_wins: 累计通关目标（蚀刻章 60 局那类）。
    """

    strategies: list[str] = field(default_factory=list)
    per_strategy_clears: int = 3
    total_wins: int = 60
    # 只刷前 N 个策略；规程蚀刻章要求 20 个策略各 3 次，0 表示不限制
    strategy_limit: int = 20
    keep_farming_after_complete: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.strategies) and (self.per_strategy_clears > 0 or self.total_wins > 0)


@dataclass
class ShopPolicy:
    priorities: list[str] = field(default_factory=lambda: list(DEFAULT_PURCHASE_PRIORITY))
    safe_keys: list[str] = field(default_factory=lambda: list(DEFAULT_SAFE_KEYS))
    healers: list[str] = field(default_factory=lambda: list(DEFAULT_HEALERS))
    dps: list[str] = field(default_factory=lambda: list(DEFAULT_DPS))
    goal: str = "medal"  # medal | task-1..7 | layer-300 | none
    build: str = "auto"  # auto | amiya_economy | amiya_victoria | guard_swift | precision_arcane | fast_level
    focus_bonds: list[str] = field(default_factory=list)
    max_healers: int = 1
    first_round_buys: int = 2
    upgrade_shop: bool = True
    max_upgrades_per_round: int = 8
    refresh_when_maxed: bool = True
    max_refresh_per_round: int = 40
    # 资金低于该值时不再刷新（刷新费 1，留 4 费买 V/VI）
    refresh_floor: int = 4


@dataclass
class TileSet:
    """极速模拟固定部署格位（720p 基准，来自 MAA 的 tiles.json）。"""

    safe: list[Point] = field(default_factory=lambda: [Point(802, 297), Point(810, 365)])
    path: list[Point] = field(default_factory=lambda: [Point(872, 233), Point(795, 233), Point(883, 297)])
    rest: list[Point] = field(default_factory=lambda: [Point(894, 365), Point(907, 439), Point(995, 439)])
    lift: Point = Point(643, 439)

    def groups(self, safe_first: bool) -> list[tuple[str, list[Point]]]:
        groups = [("safe", list(self.safe)), ("path", list(self.path)), ("rest", list(self.rest))]
        if not safe_first:
            groups = [groups[1], groups[2], groups[0]]
        return groups

    def all_points(self) -> list[Point]:
        return [*self.safe, *self.path, *self.rest]


@dataclass
class Timings:
    scene_poll: float = 0.25
    wait_after_click: float = 0.35
    strategy_page_settle: float = 1.0
    battle_poll: float = 1.0
    stall_timeout: float = 600.0
    settle_timeout: float = 900.0
    max_unknown_retries: int = 20
    screenshot_cache_ttl: float = 0.0


@dataclass
class AppConfig:
    mode: str = "badges"  # badges | points
    maa_dir: str | None = None
    adb: str = "adb"
    serial: str | None = None
    resolution: tuple[int, int] | None = None  # None = 自动读取
    debug_dir: str = "debug"
    screenshot_dir: str = "screenshots"
    dry_run: bool = False
    assume_win_on_unknown: bool = False
    targets: Targets = field(default_factory=Targets)
    policy: ShopPolicy = field(default_factory=ShopPolicy)
    tiles: TileSet = field(default_factory=TileSet)
    timings: Timings = field(default_factory=Timings)
    ocr_min_score: float = 0.55
    template_threshold: float = 0.80

    def merged(self, **overrides: Any) -> "AppConfig":
        values = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **values)


def load_config(path: str | Path | None) -> AppConfig:
    if not path:
        return AppConfig()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return config_from_dict(raw)


def config_from_dict(raw: dict[str, Any]) -> AppConfig:
    cfg = AppConfig()
    cfg.mode = str(raw.get("mode", cfg.mode))
    cfg.maa_dir = raw.get("maa_dir", cfg.maa_dir)
    cfg.adb = str(raw.get("adb", cfg.adb))
    cfg.serial = raw.get("serial", cfg.serial)
    if raw.get("resolution"):
        cfg.resolution = (int(raw["resolution"][0]), int(raw["resolution"][1]))
    cfg.debug_dir = str(raw.get("debug_dir", cfg.debug_dir))
    cfg.screenshot_dir = str(raw.get("screenshot_dir", cfg.screenshot_dir))
    cfg.dry_run = bool(raw.get("dry_run", cfg.dry_run))
    cfg.assume_win_on_unknown = bool(raw.get("assume_win_on_unknown", cfg.assume_win_on_unknown))
    cfg.ocr_min_score = float(raw.get("ocr_min_score", cfg.ocr_min_score))
    cfg.template_threshold = float(raw.get("template_threshold", cfg.template_threshold))

    t = raw.get("targets") or {}
    cfg.targets = Targets(
        strategies=list(t.get("strategies") or []),
        per_strategy_clears=int(t.get("per_strategy_clears", cfg.targets.per_strategy_clears)),
        total_wins=int(t.get("total_wins", cfg.targets.total_wins)),
        strategy_limit=int(t.get("strategy_limit", cfg.targets.strategy_limit)),
        keep_farming_after_complete=bool(t.get("keep_farming_after_complete", False)),
    )

    p = raw.get("policy") or {}
    cfg.policy = ShopPolicy(
        priorities=list(p.get("priorities") or DEFAULT_PURCHASE_PRIORITY),
        safe_keys=list(p.get("safe_keys") or DEFAULT_SAFE_KEYS),
        healers=list(p.get("healers") or DEFAULT_HEALERS),
        dps=list(p.get("dps") or DEFAULT_DPS),
        goal=str(p.get("goal", "medal")),
        build=str(p.get("build", "auto")),
        focus_bonds=list(p.get("focus_bonds") or []),
        max_healers=int(p.get("max_healers", 1)),
        first_round_buys=int(p.get("first_round_buys", 2)),
        upgrade_shop=bool(p.get("upgrade_shop", True)),
        max_upgrades_per_round=int(p.get("max_upgrades_per_round", 8)),
        refresh_when_maxed=bool(p.get("refresh_when_maxed", True)),
        max_refresh_per_round=int(p.get("max_refresh_per_round", 40)),
        refresh_floor=int(p.get("refresh_floor", 4)),
    )

    tiles = raw.get("tiles") or {}
    if tiles:
        cfg.tiles = TileSet(
            safe=[Point(*xy) for xy in tiles.get("safe", [])] or cfg.tiles.safe,
            path=[Point(*xy) for xy in tiles.get("path", [])] or cfg.tiles.path,
            rest=[Point(*xy) for xy in tiles.get("rest", [])] or cfg.tiles.rest,
            lift=Point(*tiles["lift"]) if tiles.get("lift") else cfg.tiles.lift,
        )

    tm = raw.get("timings") or {}
    cfg.timings = Timings(
        scene_poll=float(tm.get("scene_poll", cfg.timings.scene_poll)),
        wait_after_click=float(tm.get("wait_after_click", cfg.timings.wait_after_click)),
        strategy_page_settle=float(tm.get("strategy_page_settle", cfg.timings.strategy_page_settle)),
        battle_poll=float(tm.get("battle_poll", cfg.timings.battle_poll)),
        stall_timeout=float(tm.get("stall_timeout", cfg.timings.stall_timeout)),
        settle_timeout=float(tm.get("settle_timeout", cfg.timings.settle_timeout)),
        max_unknown_retries=int(tm.get("max_unknown_retries", cfg.timings.max_unknown_retries)),
        screenshot_cache_ttl=float(tm.get("screenshot_cache_ttl", cfg.timings.screenshot_cache_ttl)),
    )
    return cfg


def save_default_config(path: str | Path) -> None:
    data = {
        "mode": "badges",
        "maa_dir": "C:/Program Files/MAA",
        "serial": "",
        "targets": {
            "strategies": [],
            "per_strategy_clears": 3,
            "total_wins": 60,
            "strategy_limit": 20,
        },
        "policy": {
            "priorities": DEFAULT_PURCHASE_PRIORITY,
        },
        "tiles": {
            "safe": [[802, 297], [810, 365]],
            "path": [[872, 233], [795, 233], [883, 297]],
            "rest": [[894, 365], [907, 439], [995, 439]],
            "lift": [643, 439],
        },
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
