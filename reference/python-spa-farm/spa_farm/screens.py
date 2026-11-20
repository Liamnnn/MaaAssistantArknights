"""卫戍协议界面坐标与模板名。

ROI 全部是 1280x720 基准（与 MAA 的 StrongholdProtocol 任务资源一致），
使用时通过 geometry 换算到实际分辨率。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry import Point, roi


class Scene(str, Enum):
    ACTIVITY = "activity"      # 活动主界面，有「极速模拟」入口
    STRATEGY = "strategy"      # 策略选择页（歌利亚立绘/确认选择按钮）
    SQUAD = "squad"            # 自选编队页
    CONFIRM_INFO = "confirm_info"  # 确认本局信息页（与编队页同款按钮）
    PREP = "prep"              # 回合休整（商店 + 准备就绪）
    POPUP = "popup"            # 「确认准备」弹窗
    SETTLEMENT = "settlement"  # 结算页
    BOUNTY = "bounty"          # 悬赏三选一
    BATTLE = "battle"          # 战斗中（只用于等待）
    UNKNOWN = "unknown"

    def __str__(self) -> str:  # pragma: no cover - 仅日志用
        return self.value


# ---------------- 导航 ----------------
ENTER_QUICK = roi(707, 549, 166, 171)
START_SIM = roi(969, 553, 158, 167)
READY_SCREEN = roi(952, 581, 265, 139)
GOLIATH = roi(620, 84, 600, 400)
CONFIRM_SELECT = roi(946, 572, 271, 148)
CUSTOM_SQUAD_CONFIRM = roi(946, 572, 271, 148)
RETURN_HOME = roi(964, 590, 294, 130)
EXIT_BUTTON = roi(0, 0, 154, 155)
GIVE_UP = roi(717, 573, 242, 141)

# ---------------- 策略选择 ----------------
STRATEGY_GRID = roi(380, 80, 835, 640)
STRATEGY_GRID_STRIP = roi(400, 373, 520, 93)
STRATEGY_PANEL = roi(960, 100, 320, 433)
STRATEGY_PANEL_TITLE = roi(960, 100, 320, 133)
STRATEGY_PANEL_NAME = roi(960, 347, 320, 86)
STRATEGY_SCROLL_TRACK = roi(956, 105, 15, 590)
STRATEGY_SCROLL_TRACK2 = roi(1220, 105, 15, 590)
STRATEGY_GRID_PROBE = Point(1125, 435)

# ---------------- 休整期 ----------------
SHOP_CARDS = roi(120, 513, 1013, 193)
SHOP_GOLD = roi(1190, 512, 43, 32)
SHOP_GOLD_WIDE = roi(1173, 507, 80, 43)
SHOP_ROUND = roi(485, 21, 33, 31)
SHOP_SLOTS = roi(1241, 377, 24, 28)
SHOP_BOTTOM = roi(0, 547, 507, 127)
SHOP_UPGRADE_COST = roi(0, 513, 160, 120)
SHOP_NO_FUNDS = roi(933, 80, 320, 93)
SHOP_TRAIT = roi(0, 167, 467, 245)
READY_BUTTON = roi(1000, 60, 280, 140)
CONFIRM_READY = roi(400, 260, 480, 360)
FACING_CANCEL = roi(200, 0, 933, 547)

# ---------------- 结算 ----------------
SETTLEMENT_TITLE = roi(65, 156, 450, 160)

# ---------------- 商店卡牌内部（相对卡牌中心） ----------------
SHOP_CARD_CENTER_Y = 610
SHOP_BUY_Y = 681
SHOP_COST_BAND = roi(0, 527, 1, 8)
SHOP_TIER_BAND = roi(58, 537, 1, 9)
SHOP_PACT_BAND = roi(0, 645, 1, 20)
SHOP_NAME_BAND = roi(0, 672, 1, 28)
SHOP_EMPTY_BAND = roi(0, 600, 1, 20)
SHOP_COST_REREAD = roi(-11, 520, 23, 23)
SHOP_TIER_FRAME = roi(-62, 533, 17, 17)
SHOP_UPGRADE_COST_OFFSET = roi(-15, 520, 30, 28)
UPGRADE_BUTTON_SPAN = 100

# ---------------- 角标 / 备战席 ----------------
GOLD_BADGE_OFFSET = roi(20, -87, 47, 67)
COLOR_BADGE_OFFSET = roi(27, -73, 37, 43)
BENCH_SCAN = roi(120, 380, 930, 35)
BENCH_PRESS_OFFSET = roi(50, 110, 1, 1)
DRAG_TRAIT = roi(0, 347, 467, 53)
DRAG_NAME = roi(0, 175, 220, 80)
DRAG_TIER_FRAME = roi(13, 219, 26, 22)
SHOP_SELL = roi(1080, 480, 200, 240)
SHOP_REFRESH = Point(1190, 460)
POPUP_NOT_AGAIN = Point(1000, 480)
POPUP_CONFIRM = Point(940, 485)

# ---------------- 模板别名 ----------------
# 值按顺序尝试：MAA 主线（MiniGame@SPA@*）与 PR #19325（StrongholdProtocol@*）命名不同。
TEMPLATES: dict[str, tuple[str, ...]] = {
    "enter_quick": ("StrongholdProtocol@EnterIndependentQuickly.png", "MiniGame@SPA@EnterIndependentQuickly.png"),
    "start_sim": ("StrongholdProtocol@StartSimulation2.png", "MiniGame@SPA@StartSimulation2.png"),
    "ready_screen": ("MiniGame@SPA@ReadyScreen.png",),
    "goliath": ("MiniGame@SPA@Goliath.png",),
    "confirm_select": (
        "StrongholdProtocol@SPRConfirmSelect.png",
        "MiniGame@SPA@GoliathConfirmSelect2.png",
        "MiniGame@SPA@GoliathConfirmSelect.png",
    ),
    "custom_squad": ("MiniGame@SPA@CustomOpersConfirm.png",),
    "return_home": ("MiniGame@SPA@ReturnHome.png",),
    "exit_button": ("MiniGame@SPA@ExitButton.png",),
    "give_up": ("MiniGame@SPA@GiveUp.png",),
    "no_more_hint": ("MiniGame@SPA@NoMoreHint.png",),
    "confirm_hint": ("MiniGame@SPA@ConfirmHint.png",),
}


@dataclass(frozen=True)
class ShopBands:
    """商店卡牌内部各文字所在的 y 区间（720p）。"""

    cost: tuple[int, int] = (527, 535)
    tier: tuple[int, int] = (537, 546)
    empty: tuple[int, int] = (600, 620)
    pact: tuple[int, int] = (645, 665)
    name: tuple[int, int] = (672, 700)


SHOP_BANDS = ShopBands()
