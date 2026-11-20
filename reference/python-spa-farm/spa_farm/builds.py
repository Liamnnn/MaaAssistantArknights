"""社区攻略里的成体系打法（build）。

来源（B 站/NGA/9game 攻略，见 docs/STRATEGY.md）：
- 阿米娅兜底/电表倒转：堆远见+奇迹到 200，刷新近乎免费，再升 5 搜 3 投资人；
- 阿米娅助力维：3 助力 + 维多利亚/灵巧 + 后台奇迹/远见，前中期战力稳；
- 坚守迅捷：角峰/暴雨/蛇屠箱三盾，3 坚守 3 助力 2 迅捷，低难度很稳；
- 精准奥术：三精准三奥术，霍尔海雅+华法琳叠层，逻各斯/小羊输出；
- 速本：一本留对子凑三连，234 连跳，碰 5 定阵容。

注意：干员池随赛季变化，`priority` 里不存在的名字会被自动忽略；
真正决定买谁的是 `bonds`（目标盟约）+ 数据里的等阶/费用/叠层。
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import SeasonCatalog


@dataclass(frozen=True)
class BuildPlan:
    id: str
    name: str
    bonds: tuple[str, ...]
    priority: tuple[str, ...]
    upgrade_from_round: int = 1
    max_healers: int = 1
    economy: bool = False
    upgrade_on_odd: bool = False
    notes: str = ""

    def can_upgrade(self, round_no: int) -> bool:
        if round_no < self.upgrade_from_round:
            return False
        return round_no % 2 == 1 if self.upgrade_on_odd else True

    def effective_priority(self, catalog: SeasonCatalog) -> list[str]:
        known = catalog.chess_by_name
        return [name for name in self.priority if name in known]


BUILDS: dict[str, BuildPlan] = {
    "amiya_economy": BuildPlan(
        id="amiya_economy",
        name="阿米娅·远见奇迹经济",
        bonds=("远见", "奇迹", "投资人"),
        priority=("远山", "风丸", "能天使", "哈洛德", "至简", "锡人", "凛御银灰", "老鲤", "可露希尔", "山"),
        upgrade_from_round=3,
        economy=True,
        notes="先把远见/奇迹叠到 200，刷新基本免费；再升 5 搜 3 投资人。适合刷叠层/300 层。",
    ),
    "amiya_victoria": BuildPlan(
        id="amiya_victoria",
        name="阿米娅·助力维",
        bonds=("助力", "维多利亚", "灵巧", "远见", "奇迹"),
        priority=("锡人", "风丸", "耶拉", "维娜·维多利亚", "塞雷娅", "瑰盐", "余", "棘刺", "赫默", "桑葚"),
        upgrade_from_round=3,
        notes="3 助力 + 维多利亚/灵巧 + 后台奇迹/远见；前 3 回合不升，多买卡撑战力。",
    ),
    "guard_swift": BuildPlan(
        id="guard_swift",
        name="坚守迅捷",
        bonds=("坚守", "助力", "迅捷"),
        priority=("角峰", "蛇屠箱", "流明", "引星棘刺", "锏", "莱恩哈特", "德克萨斯"),
        upgrade_from_round=3,
        notes="三盾（角峰/暴雨/蛇屠箱）凑坚守，3 坚守 3 助力 2 迅捷；低难度稳定。",
    ),
    "spirit_swift": BuildPlan(
        id="spirit_swift",
        name="阿米娅·精灵迅",
        bonds=("精准", "灵巧", "迅捷", "远见", "奇迹"),
        priority=("锡人", "莱恩哈特", "蕾缪安", "引星棘刺", "异客", "寒克", "华法琳", "角峰"),
        upgrade_from_round=3,
        upgrade_on_odd=True,
        notes="3 精准 2 灵巧 2 迅捷；偶数回合抓人、奇数回合升本，9 回合上 5；道中兜底强。",
    ),
    "precision_arcane": BuildPlan(
        id="precision_arcane",
        name="精准奥术",
        bonds=("精准", "奥术", "聚合"),
        priority=("灰喉", "卡达", "承曦格雷伊", "空弦", "陨星", "霍尔海雅", "华法琳", "逻各斯", "艾雅法拉"),
        upgrade_from_round=2,
        notes="三精准三奥术，霍尔海雅+华法琳叠层，逻各斯/小羊输出；前排压力小。",
    ),
    "fast_level": BuildPlan(
        id="fast_level",
        name="速本（一本凑三连）",
        bonds=(),
        priority=(),
        upgrade_from_round=4,
        notes="一本留对子，三连后 234 连跳碰 5；通用打法，上限高但吃发牌。",
    ),
}


def select_build(strategy: str | None, goal: str, low_profile: bool = False) -> str:
    """按策略/目标选默认 build。"""
    if goal in ("layer-300", "task-6"):
        return "amiya_economy"
    text = strategy or ""
    if "阿米娅" in text:
        return "spirit_swift"
    if any(key in text for key in ("坚守", "迅捷")):
        return "guard_swift"
    if any(key in text for key in ("精准", "奥术")):
        return "precision_arcane"
    if low_profile:
        return "guard_swift"
    return "fast_level"


def resolve_build(
    catalog: SeasonCatalog,
    build_id: str | None,
    strategy: str | None,
    goal: str,
    low_profile: bool = False,
) -> BuildPlan:
    if build_id and build_id != "auto" and build_id in BUILDS:
        return BUILDS[build_id]
    return BUILDS[select_build(strategy, goal, low_profile)]
