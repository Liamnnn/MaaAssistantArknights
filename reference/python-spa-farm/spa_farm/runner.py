"""主循环：场景状态机 + 刷取计划。

两种模式：
- badges：完整打每一局（买/部署/开战），按计划轮换策略，统计每个策略的通关次数；
- points：只进极速模拟、等到第 5 回合退出拿卫戍认证，速度优先（沿用 MAA 现有思路）。

所有等待都用「轮询场景」代替固定 sleep，单步延迟由配置控制。
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import screens as S
from .battle import BattlePlayer
from .catalog import SeasonCatalog
from .config import AppConfig
from .device import Adb, Controller, DeviceError
from .geometry import Point
from .ocr import OcrEngine, OcrUnavailable
from .perception import Observation, Perception
from .planner import BadgePlan
from .tracker import Progress, format_duration
from .vision import Matcher, VisionUnavailable, template_dirs

LOG = logging.getLogger("spa_farm")


class RunnerError(RuntimeError):
    pass


@dataclass
class RunStats:
    started_at: float = field(default_factory=time.time)
    last_progress: float = field(default_factory=time.time)
    unknown_since: float | None = None
    unknown_retries: int = 0
    strategy: str | None = None
    in_run: bool = False
    round_no: int = -1
    run_started_at: float = field(default_factory=time.time)

    def mark_progress(self) -> None:
        self.last_progress = time.time()
        self.unknown_since = None
        self.unknown_retries = 0


class Runner:
    def __init__(self, cfg: AppConfig, state_path: str | Path, max_runs: int | None = None) -> None:
        self.cfg = cfg
        self.state_path = Path(state_path)
        self.max_runs = max_runs
        self.progress = Progress.load(self.state_path)
        self.catalog = SeasonCatalog.load()
        if cfg.mode == "badges":
            if cfg.targets.strategies:
                resolved: list[str] = []
                for name in cfg.targets.strategies:
                    matched = self.catalog.match_strategy(name)
                    resolved.append(matched.name if matched else name)
                cfg.targets.strategies = resolved
            else:
                cfg.targets.strategies = self.catalog.default_strategies(cfg.targets.strategy_limit)
                LOG.info("未配置策略，使用赛季数据里的 %s 个可用策略", len(cfg.targets.strategies))
        self.plan = BadgePlan(
            cfg.targets.strategies,
            cfg.targets.per_strategy_clears,
            cfg.targets.total_wins,
            cfg.targets.strategy_limit,
        )
        self.stats = RunStats()
        self.stop_requested = False
        self.controller: Controller | None = None
        self.perception: Perception | None = None
        self.battle: BattlePlayer | None = None
        self.ocr: OcrEngine | None = None
        self._settlement_counted = False
        self._runs_this_session = 0
        self._exit_in_progress = False
        self._last_enter = 0.0
        self._last_strategy_confirm = 0.0
        self._last_squad_click = 0.0

    # ---------- 生命周期 ----------

    def setup(self) -> None:
        if not self.cfg.maa_dir:
            raise RunnerError("需要 --maa 指向 MAA 安装目录（用于读取模板；可选读取 minitouch）")
        dirs = template_dirs(self.cfg.maa_dir)
        if not dirs:
            raise RunnerError(f"MAA 目录下找不到卫戍协议模板：{self.cfg.maa_dir}/resource/template/...")
        try:
            matcher = Matcher(dirs, self.cfg.template_threshold)
        except VisionUnavailable as exc:
            raise RunnerError(str(exc)) from exc
        if not matcher.available("enter_quick") and not matcher.available("goliath"):
            missing = ", ".join(matcher.missing())
            raise RunnerError(f"模板不完整，缺少：{missing}")

        try:
            self.ocr = OcrEngine(self.cfg.ocr_min_score)
            if not self.ocr.available:
                raise OcrUnavailable(
                    "需要 OCR 读取回合号/商店/结算：请安装 rapidocr-onnxruntime（见 requirements.txt）"
                )
        except OcrUnavailable as exc:
            raise RunnerError(str(exc)) from exc

        adb = Adb(self.cfg.adb, self.cfg.serial)
        if not self.cfg.serial:
            devices = Adb.list_devices(self.cfg.adb)
            if len(devices) == 1:
                adb.serial = devices[0]
                LOG.info("自动选择设备：%s", devices[0])
            elif len(devices) > 1:
                raise RunnerError(f"检测到多个设备，请用 --serial 指定：{devices}")
            else:
                raise RunnerError("没有检测到 adb 设备，请先启动模拟器并确认 adb 连接")
        try:
            self.controller = Controller(adb, self.cfg.maa_dir)
            self.controller.start()
        except DeviceError as exc:
            raise RunnerError(str(exc)) from exc
        LOG.info(
            "设备已连接 %s，分辨率 %s，触控方式：%s",
            adb.serial,
            self.controller.screen,
            "minitouch" if self.controller.using_minitouch else "adb input（较慢，部署可能失败）",
        )

        self.perception = Perception(matcher, self.ocr)
        self.battle = BattlePlayer(
            self.controller,
            self.perception,
            self.ocr,
            self.cfg.policy,
            self.cfg.tiles,
            dry_run=self.cfg.dry_run,
            logger=LOG.info,
            catalog=self.catalog,
        )

    def close(self) -> None:
        if self.controller is not None:
            self.controller.close()

    def request_stop(self, signum=None, frame=None) -> None:
        LOG.warning("收到停止信号，等当前动作结束后退出……")
        self.stop_requested = True

    # ---------- 主循环 ----------

    def run(self) -> int:
        self.setup()
        signal.signal(signal.SIGINT, self.request_stop)
        try:
            signal.signal(signal.SIGTERM, self.request_stop)
        except (AttributeError, ValueError):  # pragma: no cover - Windows 兼容
            pass

        assert self.perception is not None
        try:
            while not self.stop_requested:
                if self._should_stop():
                    break
                shot = self.controller.screenshot()  # type: ignore[union-attr]
                obs = self.perception.observe(shot)
                try:
                    self._dispatch(obs)
                except DeviceError as exc:
                    LOG.error("设备操作失败：%s", exc)
                    time.sleep(2)
                self._check_stall()
                time.sleep(self.cfg.timings.scene_poll)
        finally:
            self._save_progress()
            self.close()
        LOG.info("结束：%s", self.status_line())
        return 0

    def _should_stop(self) -> bool:
        if self.max_runs is not None and self._runs_this_session >= self.max_runs:
            LOG.info("达到本次运行上限 %s 局", self.max_runs)
            return True
        if self.cfg.mode == "badges" and self.cfg.targets.enabled:
            if self.plan.is_complete(self.progress.strategies, self.progress.wins) and not self.cfg.targets.keep_farming_after_complete:
                LOG.info("全部目标已完成")
                return True
        return False

    def _dispatch(self, obs: Observation) -> None:
        scene = obs.scene
        LOG.debug("scene=%s", scene)
        if scene == S.Scene.SETTLEMENT:
            self._handle_settlement(obs)
            return
        if scene == S.Scene.ACTIVITY:
            self._handle_activity(obs)
            return
        if scene == S.Scene.STRATEGY:
            self._handle_strategy(obs)
            return
        if scene == S.Scene.SQUAD:
            self._handle_squad(obs)
            return
        if scene == S.Scene.POPUP:
            self._handle_popup(obs)
            return
        if scene == S.Scene.PREP:
            self._handle_prep(obs)
            return
        if scene == S.Scene.BOUNTY:
            self._handle_bounty(obs)
            return
        if scene == S.Scene.BATTLE:
            self._wait_battle(obs)
            return
        self._handle_unknown(obs)

    # ---------- 各场景 ----------

    def _handle_activity(self, obs: Observation) -> None:
        if time.time() - self._last_enter < 2.0:
            time.sleep(self.cfg.timings.scene_poll)
            return
        self._last_enter = time.time()
        if self.stats.in_run:
            # 从结算返回后仍在主界面：上一局流程已结束
            self.stats.in_run = False
        if self.cfg.mode == "badges" and self.plan.is_complete(self.progress.strategies, self.progress.wins):
            if not self.cfg.targets.keep_farming_after_complete:
                return
        self._enter_simulation(obs)

    def _enter_simulation(self, obs: Observation) -> None:
        match = obs.matches.get("enter_quick") or self.perception.find(obs.shot, "enter_quick")  # type: ignore[union-attr]
        if match is None:
            raise RunnerError("在活动主界面找不到「极速模拟」入口，请确认当前停在卫戍协议界面")
        self._click_match(obs, match.rect)
        deadline = time.time() + 10
        while time.time() < deadline:
            shot = self.controller.screenshot()  # type: ignore[union-attr]
            start = self.perception.find(shot, "start_sim")  # type: ignore[union-attr]
            if start:
                self._click_rect(shot, start.rect)
                break
            ready = self.perception.find(shot, "ready_screen")  # type: ignore[union-attr]
            if ready:
                self._click_rect(shot, ready.rect)
                break
            time.sleep(0.3)
        deadline = time.time() + 10
        while time.time() < deadline:
            shot = self.controller.screenshot()  # type: ignore[union-attr]
            ready = self.perception.find(shot, "ready_screen")  # type: ignore[union-attr]
            if ready:
                self._click_rect(shot, ready.rect)
                time.sleep(0.5)
                break
            if self.perception.find(shot, "goliath") or self.perception.find(shot, "confirm_select"):  # type: ignore[union-attr]
                break
            time.sleep(0.3)

    def _handle_strategy(self, obs: Observation) -> None:
        if time.time() - self._last_strategy_confirm < 2.0:
            time.sleep(self.cfg.timings.scene_poll)
            return
        name = self.stats.strategy or self.plan.next_strategy(self.progress.strategies, self.progress.wins)
        if self.cfg.mode == "points":
            name = self.cfg.targets.strategies[0] if self.cfg.targets.strategies else "歌利亚"
        if not name:
            raise RunnerError("没有可刷的策略：请先运行 `spa-farm discover`")
        self.stats.strategy = name
        if self._select_strategy(name):
            self.stats.mark_progress()
            self._settlement_counted = False
            self._exit_in_progress = False
            self.stats.in_run = True
            self.stats.run_started_at = time.time()
            self._last_strategy_confirm = time.time()
            if self.battle is not None:
                self.battle.set_strategy(name)
            LOG.info("已选择策略：%s（%s/%s）", name, self.progress.clears(name), self.cfg.targets.per_strategy_clears)
        else:
            self._screenshot("strategy_select_failed")
            raise RunnerError(f"选不到策略「{name}」，请检查策略页是否在预期界面")

    def _select_strategy(self, name: str) -> bool:
        for attempt in range(8):
            shot = self.controller.screenshot()  # type: ignore[union-attr]
            lines = self.ocr.read(shot, S.STRATEGY_GRID)  # type: ignore[union-attr]
            hit = None
            for line in lines:
                matched = self.catalog.match_strategy(line.text)
                if matched is not None and matched.name == name:
                    hit = line
                    break
            if hit is not None:
                self._click_rect(shot, hit.rect, settle=0.6)
                check = self.controller.screenshot()  # type: ignore[union-attr]
                panel = "".join(line.text for line in self.ocr.read(check, S.STRATEGY_PANEL))  # type: ignore[union-attr]
                panel_match = self.catalog.match_strategy(panel) if panel else None
                if panel_match is not None and panel_match.name == name:
                    if self._confirm_strategy(check):
                        return True
                elif not panel:
                    if self._confirm_strategy(check):
                        return True
                LOG.warning("策略面板显示「%s」，与目标「%s」不符，重试", panel, name)
            # 当前页没有目标：向上滚动网格
            LOG.info("策略网格未找到「%s」，滚动重试（第 %s 次）", name, attempt + 1)
            self._scroll_strategy_grid(shot)
            time.sleep(self.cfg.timings.strategy_page_settle)
        return False

    def _confirm_strategy(self, shot) -> bool:
        match = self.perception.find(shot, "confirm_select")  # type: ignore[union-attr]
        if match:
            self._click_rect(shot, match.rect, settle=0.6)
            return True
        for line in self.ocr.read(shot, S.CONFIRM_SELECT):  # type: ignore[union-attr]
            if "确认" in line.text:
                self._click_rect(shot, line.rect, settle=0.6)
                return True
        return False

    def _scroll_strategy_grid(self, shot) -> None:
        actual = shot.to_actual(S.STRATEGY_GRID_PROBE)
        self.controller.swipe(  # type: ignore[union-attr]
            actual,
            Point(actual.x, actual.y - 300),
            duration_ms=500,
        )

    def _handle_squad(self, obs: Observation) -> None:
        if time.time() - self._last_squad_click < 1.5:
            time.sleep(self.cfg.timings.scene_poll)
            return
        self._last_squad_click = time.time()
        match = obs.matches.get("custom_squad") or self.perception.find(obs.shot, "custom_squad")  # type: ignore[union-attr]
        if match:
            self._click_rect(obs.shot, match.rect, settle=0.8)
        self._confirm_popup()

    def _handle_popup(self, obs: Observation) -> None:
        self.battle._confirm_popup()  # type: ignore[union-attr]

    def _handle_prep(self, obs: Observation) -> None:
        if self.cfg.mode == "points":
            self._points_wait(obs)
            return
        round_no = self.battle.prep(obs.shot)  # type: ignore[union-attr]
        if round_no is not None and round_no >= 0:
            self.stats.round_no = round_no
        self.stats.mark_progress()

    def _points_wait(self, obs: Observation) -> None:
        reader = self.battle.reader  # type: ignore[union-attr]
        round_no = reader.read_number(obs.shot, S.SHOP_ROUND, 1, 30)
        if round_no is not None and round_no != self.stats.round_no:
            self.stats.round_no = round_no
            self.stats.mark_progress()
        if round_no is not None and round_no >= 5 and not self._exit_in_progress:
            LOG.info("第 %s 回合，退出拿点", round_no)
            self._exit_in_progress = True
            self._exit_run(obs)
        else:
            time.sleep(self.cfg.timings.battle_poll)

    def _handle_bounty(self, obs: Observation) -> None:
        # 三选一：优先中间项，然后点确认
        lines = [line for line in obs.texts if "悬赏" in line.text]
        if len(lines) >= 3:
            lines.sort(key=lambda line: line.rect.x)
            self._click_rect(obs.shot, lines[1].rect, settle=0.4)
        for line in self.ocr.read(obs.shot, S.CONFIRM_READY):  # type: ignore[union-attr]
            if "确认" in line.text:
                self._click_rect(obs.shot, line.rect, settle=0.6)
                return

    def _wait_battle(self, obs: Observation) -> None:
        time.sleep(self.cfg.timings.battle_poll)

    def _handle_unknown(self, obs: Observation) -> None:
        if self.stats.unknown_since is None:
            self.stats.unknown_since = time.time()
        self.stats.unknown_retries += 1
        if self.stats.unknown_retries == 5:
            self._screenshot("unknown")
        if time.time() - self.stats.unknown_since > 30:
            self._screenshot("stuck")
            raise RunnerError("连续 30 秒无法识别界面：请检查游戏是否仍在卫戍协议界面")

    # ---------- 结算 ----------

    def _handle_settlement(self, obs: Observation) -> None:
        result = obs.result
        if result is None:
            for _ in range(5):
                time.sleep(0.3)
                shot = self.controller.screenshot()  # type: ignore[union-attr]
                result = self.perception.read_result(shot)  # type: ignore[union-attr]
                if result:
                    break
        if result is None:
            result = "win" if self.cfg.assume_win_on_unknown else "unknown"
            LOG.warning("结算结果识别失败，按 %s 处理", result)

        if not self._settlement_counted:
            self._settlement_counted = True
            self.stats.in_run = False
            self._runs_this_session += 1
            elapsed = time.time() - self.stats.run_started_at
            if self.cfg.mode == "points":
                self.progress.record_points(80)
                LOG.info("点数局完成，累计 %s 点（%s 局）", self.progress.points, self.progress.point_runs)
            else:
                strategy = self.stats.strategy or "?"
                self.progress.record(strategy, result, elapsed, self.stats.round_no)
                eta = self.progress.eta_seconds(self.plan.remaining_runs(self.progress.strategies, self.progress.wins))
                LOG.info(
                    "结算：%s；本局 %.1fs；进度 %s；预计还需 %s",
                    {"win": "胜利", "loss": "失败", "aborted": "中断", "unknown": "未知"}.get(result, result),
                    elapsed,
                    self.status_line(),
                    format_duration(eta),
                )
                if result == "unknown":
                    LOG.warning("未知结果不计入通关次数；如确认这局赢了，可加 --assume-win-on-unknown")
                rate = self.progress.win_rate(window=20)
                if rate is not None:
                    LOG.info("近 20 局胜率：%.1f%%", rate * 100)
                self.stats.strategy = None
                self.stats.round_no = -1
                if self.battle is not None:
                    self.battle.board.reset_for_new_game()
            self._save_progress()

        match = self.perception.find(obs.shot, "return_home")  # type: ignore[union-attr]
        if match:
            self._click_rect(obs.shot, match.rect, settle=1.0)
        self.stats.mark_progress()

    def _exit_run(self, obs: Observation) -> None:
        """刷点数：点左上退出 → 放弃模拟 → 回主界面。"""
        exit_match = self.perception.find(obs.shot, "exit_button")  # type: ignore[union-attr]
        if exit_match:
            self._click_rect(obs.shot, exit_match.rect, settle=0.8)
        else:
            self._click_rect(obs.shot, S.EXIT_BUTTON, settle=0.8)

        deadline = time.time() + 10
        while time.time() < deadline:
            shot = self.controller.screenshot()  # type: ignore[union-attr]
            give_up = self.perception.find(shot, "give_up")  # type: ignore[union-attr]
            if give_up:
                self._click_rect(shot, give_up.rect, settle=0.8)
                continue
            if self.perception.find(shot, "return_home"):  # type: ignore[union-attr]
                # 点数在结算页统一记账，避免退出流程与结算流程重复计数
                self.stats.mark_progress()
                return
            time.sleep(0.4)
        LOG.warning("退出流程超时，等待下一次场景判定")

    # ---------- 工具 ----------

    def _click_rect(self, shot, rect, settle: float = 0.3) -> None:
        point = shot.to_actual(rect.center)
        LOG.debug("click (%s,%s)", point.x, point.y)
        if not self.cfg.dry_run:
            self.controller.tap(point, settle=settle)  # type: ignore[union-attr]
        else:
            time.sleep(settle)

    def _click_match(self, obs: Observation, rect) -> None:
        self._click_rect(obs.shot, rect, settle=self.cfg.timings.wait_after_click)

    def _check_stall(self) -> None:
        if time.time() - self.stats.last_progress > self.cfg.timings.stall_timeout:
            self._screenshot("stall")
            raise RunnerError(f"超过 {self.cfg.timings.stall_timeout:.0f}s 没有进展，已停止并保存截图")

    def _screenshot(self, tag: str) -> None:
        if self.controller is None:
            return
        path = Path(self.cfg.screenshot_dir)
        path.mkdir(parents=True, exist_ok=True)
        target = path / f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.png"
        try:
            import cv2

            cv2.imwrite(str(target), self.controller.screenshot().raw)
            LOG.info("已保存截图：%s", target)
        except Exception as exc:  # pragma: no cover - 仅诊断用途
            LOG.warning("截图保存失败：%s", exc)

    def _save_progress(self) -> None:
        try:
            self.progress.save(self.state_path)
        except OSError as exc:
            LOG.warning("进度保存失败：%s", exc)

    def status_line(self) -> str:
        if self.cfg.mode == "points":
            return f"点数模式：{self.progress.point_runs} 局，{self.progress.points} 点"
        status = self.plan.status(self.progress.strategies, self.progress.wins)
        return status.summary()
