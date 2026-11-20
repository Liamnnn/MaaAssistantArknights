"""对局内操作：读商店、买干员、升级、部署、开战。

这一层是「策略」所在：买什么、什么时候升级、放在哪一格。
界面坐标全部来自 screens.py（720p 基准），颜色/差分判定来自 vision.py。

v0.1 的定位：结构完整、可读、可单元测试；策略参数（购买权重、格位）可配置。
不同赛季/难度下的胜率需要在实机上用 `--dry-run` + 日志校准，见 docs/DESIGN.md。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from . import screens as S
from .builds import BuildPlan, resolve_build
from .catalog import SeasonCatalog
from .config import ShopPolicy, TileSet
from .device import Controller
from .geometry import Point, Rect
from .ocr import OcrEngine, TextLine, has_chinese, parse_int
from .perception import Perception
from .scoring import GoalFocus, build_focus, oper_score, rank_cards
from .vision import Screenshot, color_ratio, find_new_dark_square, is_green

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}


@dataclass
class ShopCard:
    x: int
    cost: int = -1
    tier: int = 0
    name: str = ""
    is_oper: bool = False
    empty: bool = False

    def describe(self) -> str:
        return f"{self.name or '?'}(cost={self.cost}, tier={self.tier}, oper={self.is_oper})"


@dataclass
class ShopInfo:
    gold: int | None = None
    round: int | None = None
    maxed: bool = False
    upgrade_x: int | None = None
    upgrade_cost: int | None = None
    cards: list[ShopCard] = field(default_factory=list)


class ShopReader:
    def __init__(self, ocr: OcrEngine, policy: ShopPolicy, catalog: SeasonCatalog | None = None) -> None:
        self.ocr = ocr
        self.policy = policy
        self.catalog = catalog
        self._known_names = set(policy.priorities) | set(policy.dps) | set(policy.healers) | set(policy.safe_keys)

    # ---------- 数字 ----------

    def read_number(self, shot: Screenshot, rect: Rect, lo: int = 0, hi: int = 99) -> int | None:
        lines = self.ocr.read(shot, rect)
        best: int | None = None
        for line in lines:
            value = parse_int(line.text, lo, hi)
            if value is not None:
                best = value if best is None else max(best, value)
        return best

    def read_gold(self, shot: Screenshot) -> int | None:
        for rect in (S.SHOP_GOLD, S.SHOP_GOLD_WIDE):
            value = self.read_number(shot, rect, 0, 99)
            if value is not None:
                return value
        return None

    # ---------- 商店整体 ----------

    def read(self, shot: Screenshot) -> ShopInfo:
        info = ShopInfo()
        info.gold = self.read_gold(shot)
        info.round = self.read_number(shot, S.SHOP_ROUND, 1, 30)
        bottom = self.ocr.read(shot, S.SHOP_BOTTOM)
        for line in bottom:
            if "满级" in line.text:
                info.maxed = True
            if "升级" in line.text:
                info.upgrade_x = line.rect.center.x
        if not info.maxed and info.upgrade_x is not None:
            off = S.SHOP_UPGRADE_COST_OFFSET
            info.upgrade_cost = self.read_number(
                shot, Rect(info.upgrade_x + off.x, off.y, off.w, off.h), 0, 99
            )
        info.cards = self.read_cards(shot, info.upgrade_x)
        return info

    # ---------- 卡牌 ----------

    def read_cards(self, shot: Screenshot, upgrade_x: int | None) -> list[ShopCard]:
        lines = self.ocr.read(shot, S.SHOP_CARDS)
        if not lines:
            return []
        bands = S.SHOP_BANDS
        centers: list[int] = []
        for line in lines:
            cy = line.rect.center.y
            if bands.cost[0] <= cy <= bands.cost[1]:
                centers.append(line.rect.center.x)
            elif bands.tier[0] <= cy <= bands.tier[1]:
                centers.append(line.rect.center.x + S.SHOP_TIER_BAND.x)
        centers.sort()
        slots: list[int] = []
        for x in centers:
            if not slots or x - slots[-1] > 12:
                slots.append(x)
            else:
                slots[-1] = (slots[-1] + x) // 2
        if upgrade_x is not None:
            slots = [x for x in slots if x > upgrade_x + S.UPGRADE_BUTTON_SPAN]
        cards: list[ShopCard] = []
        for x in slots:
            cards.append(self._parse_card(shot, x, lines, bands))
        return cards

    def _parse_card(self, shot: Screenshot, x: int, lines: list[TextLine], bands) -> ShopCard:
        card = ShopCard(x=x)
        for line in lines:
            cx = line.rect.center.x
            cy = line.rect.center.y
            if abs(cx - x) > 60:
                continue
            text = line.text.strip()
            upper = "".join("I" if ch in "1Ll" else ch.upper() for ch in text)
            if bands.tier[0] <= cy <= bands.tier[1] and cx < x and upper in ROMAN:
                card.tier = ROMAN[upper]
                continue
            if bands.cost[0] <= cy <= bands.cost[1] and abs(cx - x) <= S.SHOP_COST_REREAD.w // 2:
                value = parse_int(text, 0, 9)
                if value is not None:
                    card.cost = value
                    continue
            if bands.empty[0] <= cy <= bands.empty[1] and "NO INFO" in upper:
                card.empty = True
                continue
            if bands.pact[0] <= cy <= bands.pact[1] and has_chinese(text):
                card.is_oper = True
                continue
            if bands.name[0] <= cy <= bands.name[1] and not card.name and self._is_oper_name(text):
                card.name = text
        if card.cost < 0 and not card.empty:
            off = S.SHOP_COST_REREAD
            card.cost = self.read_number(shot, Rect(x + off.x, off.y, off.w, off.h), 0, 9) or -1
        if card.tier == 0:
            frame = S.SHOP_TIER_FRAME
            if color_ratio(shot.base, Rect(x + frame.x, frame.y, frame.w, frame.h), (8, 120, 150), (35, 255, 255)) > 0.1:
                card.tier = 5
        card.is_oper = card.is_oper and not card.empty
        return card

    def _is_oper_name(self, text: str) -> bool:
        if not text or "NO INFO" in text.upper():
            return False
        if text in self._known_names:
            return True
        if self.catalog is not None and self.catalog.is_known_oper(text):
            return True
        return has_chinese(text) and 2 <= len(text) <= 8


@dataclass
class BoardState:
    round_done: int = -1
    occ: dict[str, tuple[str, int]] = field(default_factory=dict)
    healers: int = 0
    purchases: dict[str, int] = field(default_factory=dict)
    pending_deploy: bool = False

    def reset_for_new_game(self) -> None:
        self.round_done = -1
        self.occ.clear()
        self.healers = 0
        self.purchases.clear()
        self.pending_deploy = False


class BattlePlayer:
    def __init__(
        self,
        controller: Controller,
        perception: Perception,
        ocr: OcrEngine,
        policy: ShopPolicy,
        tiles: TileSet,
        dry_run: bool = False,
        logger=print,
        catalog: SeasonCatalog | None = None,
    ) -> None:
        self.controller = controller
        self.perception = perception
        self.ocr = ocr
        self.policy = policy
        self.tiles = tiles
        self.dry_run = dry_run
        self.log = logger
        self.reader = ShopReader(ocr, policy, catalog)
        self.catalog = catalog
        self.policy = policy
        self.effective_policy = policy
        self.build = BuildPlan("generic", "通用", (), (), 1, 1, False, "")
        self.focus = GoalFocus(policy.goal, "无赛季数据", frozenset(), False)
        self.board = BoardState()
        self.set_strategy(None)

    # ---------- build ----------

    def set_strategy(self, strategy: str | None) -> None:
        """切换策略时重选 build（Runner 在选定策略后调用）。"""
        if self.catalog is None:
            return
        self.build = resolve_build(
            self.catalog,
            self.policy.build,
            strategy,
            self.policy.goal,
        )
        focus = build_focus(self.catalog, self.policy.goal, self.policy.focus_bonds)
        if self.build.bonds:
            focus = GoalFocus(self.build.id, self.build.name, frozenset(self.build.bonds), True)
        self.focus = focus
        merged: list[str] = []
        for name in (*self.build.effective_priority(self.catalog), *self.policy.priorities):
            if name not in merged:
                merged.append(name)
        self.effective_policy = replace(
            self.policy,
            priorities=merged,
            max_healers=self.build.max_healers,
        )
        if self.build.notes:
            self.log(f"[build] {self.build.name}：{self.build.notes}")

    # ---------- 小工具 ----------

    def _click_base(self, point: Point, shot: Screenshot, settle: float = 0.25) -> None:
        actual = shot.to_actual(point)
        self.log(f"[action] click base=({point.x},{point.y}) actual=({actual.x},{actual.y})")
        if not self.dry_run:
            self.controller.tap(actual)
        time.sleep(settle)

    def _click_rect(self, rect: Rect, shot: Screenshot, settle: float = 0.25) -> None:
        self._click_base(rect.center, shot, settle)

    def _oper_rank(self, name: str, tier: int) -> int:
        if self.catalog is not None:
            return oper_score(
                self.catalog,
                self.effective_policy,
                self.focus,
                name,
                tier,
                self.board.purchases.get(name, 0),
            )
        if name in self.effective_policy.priorities:
            return 1000 - self.effective_policy.priorities.index(name)
        if tier >= 5:
            return 550 if name in self.policy.dps else 500
        return tier

    def _is_safe(self, name: str) -> bool:
        return name in self.policy.safe_keys

    # ---------- 休整期入口 ----------

    def prep(self, shot: Screenshot) -> int:
        """处理一个休整回合，返回本回合号（识别不到返回 -1）。"""
        shop = self.reader.read(shot)
        round_no = shop.round
        if round_no is None:
            round_no = max(1, self.board.round_done + 1)
            self.log(f"[warn] 回合号识别失败，按 {round_no} 处理")
        if round_no == self.board.round_done:
            self._start_battle(shot)
            return round_no

        self.log(f"[round {round_no}] gold={shop.gold} maxed={shop.maxed} cards={[c.describe() for c in shop.cards]}")

        if self.board.round_done < 0 and round_no == 1:
            self._early_buys(shot, shop)

        if (
            self.policy.upgrade_shop
            and not shop.maxed
            and self.build.can_upgrade(round_no)
        ):
            shop = self._upgrade_loop(shot, shop)

        if shop.maxed and self.policy.refresh_when_maxed:
            shop = self._buy_at_max(shot, shop)
        elif not shop.maxed:
            self._buy_leftovers(shot, shop)

        if self.board.pending_deploy:
            self._deploy_bench()
            self.board.pending_deploy = False

        self.board.round_done = round_no
        self._start_battle(shot)
        return round_no

    # ---------- 购买 ----------

    def _early_buys(self, shot: Screenshot, shop: ShopInfo) -> None:
        bought = 0
        for card in shop.cards:
            if bought >= self.policy.first_round_buys:
                break
            if not self._affordable(card, shop.gold):
                continue
            if card.name in self.policy.healers and self.board.healers >= self.effective_policy.max_healers:
                continue
            if self._buy(shot, card):
                bought += 1
        if bought:
            self.log(f"[buy] 首回合买入 {bought} 名干员")

    def _buy_leftovers(self, shot: Screenshot, shop: ShopInfo) -> None:
        if self.catalog is not None:
            cards = rank_cards(self.catalog, self.policy, self.focus, shop.cards, self.board.purchases)
        else:
            cards = sorted(shop.cards, key=lambda c: self._oper_rank(c.name, c.tier), reverse=True)
        for card in cards:
            if not self._affordable(card, shop.gold):
                continue
            if card.name in self.policy.healers and self.board.healers >= self.effective_policy.max_healers:
                continue
            if self._buy(shot, card):
                shop.gold = self.reader.read_gold(shot) if not self.dry_run else None
                if shop.gold == 0:
                    break

    def _buy_at_max(self, shot: Screenshot, shop: ShopInfo) -> ShopInfo:
        """满级后：优先免费/权重高的 V/VI，否则刷新。"""
        for _ in range(self.policy.max_refresh_per_round):
            current = self.reader.read(shot)
            gold = current.gold if current.gold is not None else shop.gold
            candidates = [c for c in current.cards if c.is_oper and not c.empty and c.cost >= 0]
            if not candidates:
                break
            free = [c for c in candidates if c.cost == 0]
            pick = max(free, key=lambda c: self._oper_rank(c.name, c.tier)) if free else None
            if pick is None:
                affordable = [c for c in candidates if gold is None or c.cost <= gold]
                ranked = [c for c in affordable if self._oper_rank(c.name, c.tier) >= 500]
                pick = max(ranked, key=lambda c: self._oper_rank(c.name, c.tier)) if ranked else None
            if pick is not None:
                self._buy(shot, pick)
                continue
            if gold is not None and gold < self.policy.refresh_floor:
                break
            self._refresh(shot)
            shot = self.controller.screenshot()
        return self.reader.read(shot)

    def _affordable(self, card: ShopCard, gold: int | None) -> bool:
        return card.is_oper and not card.empty and card.cost >= 0 and (gold is None or card.cost <= gold)

    def _buy(self, shot: Screenshot, card: ShopCard) -> bool:
        before = shot.base
        self._click_base(Point(card.x, S.SHOP_CARD_CENTER_Y), shot, settle=0.3)
        selected = self.controller.screenshot()
        texts = self.ocr.read(selected, S.SHOP_TRAIT)
        joined = "".join(t.text for t in texts)
        no_funds = "".join(t.text for t in self.ocr.read(selected, S.SHOP_NO_FUNDS))
        if "资金不足" in no_funds:
            self.log(f"[buy] 资金不足：{card.name}")
            self._close_popup(selected)
            return False
        if not any(key in joined for key in ("特质", "天赋", "技能")):
            self.log(f"[buy] 选中后没有特质面板，跳过（可能是装备）：x={card.x}")
            self._close_popup(selected)
            return False
        if not card.name:
            for line in texts:
                if has_chinese(line.text) and line.text in self.effective_policy.priorities:
                    card.name = line.text
                    break

        self._click_base(Point(card.x, S.SHOP_BUY_Y), selected, settle=0.45)
        after = self.controller.screenshot()
        gold_after = self.reader.read_gold(after)
        self.log(f"[buy] {card.describe()} -> gold={gold_after}")
        self.board.purchases[card.name or "?"] = self.board.purchases.get(card.name or "?", 0) + 1
        if card.name in self.policy.healers:
            self.board.healers += 1
        self._deploy_purchased(before, after.base, card)
        return True

    def _refresh(self, shot: Screenshot) -> None:
        self._click_base(S.SHOP_REFRESH, shot, settle=0.4)

    def _close_popup(self, shot: Screenshot) -> None:
        self._click_base(Point(640, 600), shot, settle=0.2)

    # ---------- 升级 ----------

    def _upgrade_loop(self, shot: Screenshot, shop: ShopInfo) -> ShopInfo:
        for _ in range(self.policy.max_upgrades_per_round):
            if shop.maxed:
                break
            if shop.gold is not None and shop.upgrade_cost is not None and shop.gold < shop.upgrade_cost:
                break
            line = self._find_bottom_text(shot, "升级")
            if line is None:
                break
            self._click_rect(line.rect, shot, settle=0.35)
            # 第一次点击后按钮文案会变成「确认升级」，同一位置再点一次
            self._click_rect(line.rect, shot, settle=0.5)
            after = self.reader.read(self.controller.screenshot())
            if after.maxed or (after.gold is not None and shop.gold is not None and after.gold < shop.gold):
                self.log(f"[upgrade] 升级成功 gold {shop.gold} -> {after.gold}")
                shop = after
                if not shop.upgrade_cost:
                    break
                continue
            self.log("[upgrade] 升级未生效，停止本轮升级")
            break
        return shop

    def _find_bottom_text(self, shot: Screenshot, keyword: str) -> TextLine | None:
        for line in self.ocr.read(shot, S.SHOP_BOTTOM):
            if keyword in line.text:
                return line
        return None

    # ---------- 开战 / 弹窗 ----------

    def _start_battle(self, shot: Screenshot) -> None:
        line = None
        for candidate in self.ocr.read(shot, S.READY_BUTTON):
            if any(k in candidate.text for k in ("准备就绪", "准备", "就绪")):
                line = candidate
                break
        if line is None:
            self.log("[warn] 找不到「准备就绪」按钮，用固定坐标兜底")
            self._click_base(Point(1140, 130), shot, settle=0.6)
        else:
            self._click_rect(line.rect, shot, settle=0.8)
        self._confirm_popup()

    def _confirm_popup(self) -> None:
        shot = self.controller.screenshot()
        lines = self.ocr.read(shot, S.CONFIRM_READY)
        if not any("确认" in line.text for line in lines):
            return
        for line in lines:
            if "不再提示" in line.text:
                self._click_rect(line.rect, shot, settle=0.2)
        for line in lines:
            if "确认" in line.text:
                self._click_rect(line.rect, shot, settle=0.5)
                return
        self._click_base(S.POPUP_CONFIRM, shot, settle=0.5)

    # ---------- 部署 ----------

    def _deploy_purchased(self, before_base, after_base, card: ShopCard) -> None:
        square = find_new_dark_square(before_base, after_base, S.BENCH_SCAN)
        if square is None:
            self.log("[deploy] 没定位到新干员的备战席位置，留到回合末统一部署")
            self.board.pending_deploy = True
            return
        press = Point(square.x + S.BENCH_PRESS_OFFSET.x, square.y + S.BENCH_PRESS_OFFSET.y)
        if not self._deploy_from_bench(press, card.name, card.tier):
            self.board.pending_deploy = True

    def _deploy_bench(self) -> None:
        for _ in range(10):
            shot = self.controller.screenshot()
            units = self._detect_bench_units(shot)
            if not units:
                return
            placed = False
            for point in units:
                if self._deploy_from_bench(point):
                    placed = True
                    break
            if not placed:
                return

    def _detect_bench_units(self, shot: Screenshot) -> list[Point]:
        cropped = shot.crop(S.BENCH_SCAN)
        if cropped.size == 0:
            return []
        import cv2

        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        _, dark = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points: list[Point] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not (18 <= w <= 34 and 15 <= h <= 34):
                continue
            if not (0.8 <= w / h <= 1.8):
                continue
            if cv2.contourArea(contour) < w * h * 0.75:
                continue
            inner = gray[y + 4 : y + h - 4, x + 4 : x + w - 4]
            if inner.size == 0:
                continue
            _, strokes = cv2.threshold(inner, 140, 255, cv2.THRESH_BINARY)
            if cv2.countNonZero(strokes) < inner.size * 0.03:
                continue
            points.append(
                Point(
                    S.BENCH_SCAN.x + x + S.BENCH_PRESS_OFFSET.x,
                    S.BENCH_SCAN.y + y + S.BENCH_PRESS_OFFSET.y,
                )
            )
        points.sort(key=lambda p: p.x, reverse=True)
        return points

    def _deploy_from_bench(self, bench: Point, name: str = "", tier: int = 0) -> bool:
        shot = self.controller.screenshot()
        start = shot.to_actual(bench)
        probe = Point(bench.x + (640 - bench.x) // 4, bench.y + (400 - bench.y) // 4)
        lift = self.tiles.lift

        if self.dry_run:
            self.log(f"[deploy] dry-run 拿起 {name or '?'} @({bench.x},{bench.y})")
            return False

        if not self.controller.using_minitouch:
            # 没有 minitouch 时做不了「按住-预览-选格」，退化为直接拖到第一个空格
            key, target = self._pick_tile(shot, self._is_safe(name))
            if target is None:
                return False
            self.controller.drag(start, shot.to_actual(target), hold_ms=350, move_ms=600, steps=10)
            time.sleep(0.4)
            if self._set_facing(target):
                self.board.occ[key] = (name or "?", tier)
                self.log(f"[deploy] (adb fallback) {name or '?'} -> {key}")
                return True
            return False

        self.controller.press(start)
        time.sleep(0.35)
        probe_actual = shot.to_actual(probe)
        for i in range(1, 6):
            p = Point(
                round(start.x + (probe_actual.x - start.x) * i / 5),
                round(start.y + (probe_actual.y - start.y) * i / 5),
            )
            self.controller.move_to(p, settle_ms=30)

        lift_actual = shot.to_actual(lift)
        for i in range(1, 9):
            p = Point(
                round(probe_actual.x + (lift_actual.x - probe_actual.x) * i / 8),
                round(probe_actual.y + (lift_actual.y - probe_actual.y) * i / 8),
            )
            self.controller.move_to(p, settle_ms=20)

        preview = self.controller.screenshot()
        trait_text = "".join(t.text for t in self.ocr.read(preview, S.DRAG_TRAIT))
        drag_name = self._read_drag_name(preview)
        if drag_name:
            name = drag_name
        green_any = any(is_green(preview, p) for p in self.tiles.all_points())
        if not green_any and "特质" not in trait_text and "天赋" not in trait_text and not drag_name:
            self.log(f"[deploy] 没抓起（{name or '?'}），放回备战席")
            self.controller.release(lift_actual)
            time.sleep(0.4)
            return False

        target_key, target = self._pick_tile(preview, self._is_safe(name))
        if target is None:
            self.controller.release(lift_actual)
            time.sleep(0.3)
            self.log(f"[deploy] 没有可用格位，{name or '?'} 放回备战时")
            return False

        target_actual = preview.to_actual(target)
        steps = 8
        for i in range(1, steps + 1):
            p = Point(
                round(lift_actual.x + (target_actual.x - lift_actual.x) * i / steps),
                round(lift_actual.y + (target_actual.y - lift_actual.y) * i / steps),
            )
            self.controller.move_to(p, settle_ms=20)
        time.sleep(0.15)
        self.controller.release(target_actual)
        time.sleep(0.3)

        if not self._set_facing(target):
            self.log("[deploy] 朝向确认失败，格位可能已被占用")
            return False
        self.board.occ[target_key] = (name or "?", tier)
        self.log(f"[deploy] {name or '?'} -> {target_key} ({target.x},{target.y})")
        return True

    def _read_drag_name(self, shot: Screenshot) -> str:
        for line in self.ocr.read(shot, S.DRAG_NAME):
            text = line.text.strip()
            if not text or "LV" in text.upper():
                continue
            if has_chinese(text) or (text.isascii() and len(text) >= 2 and not text.isdigit()):
                return text
        return ""

    def _pick_tile(self, preview: Screenshot, safe: bool) -> tuple[str, Point | None]:
        groups = self.tiles.groups(safe_first=safe)
        # 先找空位；空位判定优先用绿高亮，读不到绿时退回 occ 记录
        for group_name, points in groups:
            for index, point in enumerate(points):
                key = f"{group_name}{index}"
                if key in self.board.occ:
                    continue
                if is_green(preview, point) or not self._green_detected(preview):
                    return key, point
        # 没有空格：换下本组价值最低的低星（<5）
        for group_name, points in groups:
            candidates = [
                (self._oper_rank(*self.board.occ[f"{group_name}{i}"]), i)
                for i in range(len(points))
                if f"{group_name}{i}" in self.board.occ and self.board.occ[f"{group_name}{i}"][1] < 5
            ]
            if candidates:
                _, index = min(candidates)
                return f"{group_name}{index}", points[index]
        return "", None

    def _green_detected(self, preview: Screenshot) -> bool:
        return any(is_green(preview, p) for p in self.tiles.all_points())

    def _set_facing(self, tile: Point) -> bool:
        shot = self.controller.screenshot()
        actual = shot.to_actual(tile)
        self.controller.drag(
            actual,
            Point(actual.x + 200, actual.y),
            hold_ms=250,
            move_ms=200,
            steps=6,
        )
        for _ in range(8):
            time.sleep(0.2)
            probe = self.controller.screenshot()
            if not any("取消" in line.text for line in self.ocr.read(probe, S.FACING_CANCEL)):
                return True
        return False
