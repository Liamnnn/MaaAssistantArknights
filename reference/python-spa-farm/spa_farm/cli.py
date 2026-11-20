"""命令行入口。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from . import screens as S
from .builds import BUILDS, resolve_build
from .catalog import SeasonCatalog
from .config import AppConfig, load_config, save_default_config
from .device import Adb, Controller, DeviceError
from .ocr import OcrEngine, OcrUnavailable
from .perception import Perception
from .geometry import Point
from .planner import BadgePlan
from .scoring import build_focus
from .runner import Runner, RunnerError
from .tracker import Progress, format_duration
from .vision import Matcher, Screenshot, VisionUnavailable, template_dirs

LOG = logging.getLogger("spa_farm")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS, help="配置文件（JSON）")
    common.add_argument("--maa", dest="maa_dir", default=argparse.SUPPRESS, help="MAA 安装目录，用于读取模板/minitouch")
    common.add_argument("--serial", default=argparse.SUPPRESS, help="adb 序列号（只连了一个设备时可省略）")
    common.add_argument("--adb", default=argparse.SUPPRESS, help="adb 可执行文件路径")
    common.add_argument(
        "--log-level",
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    common.add_argument("--log-file", default=argparse.SUPPRESS, help="同时写入日志文件")

    parser = argparse.ArgumentParser(
        prog="spa-farm",
        description="明日方舟「卫戍协议」刷取工具（独立 Python 实现，复用 MAA 的模板与坐标）",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="开始刷", parents=[common])
    run.add_argument("--mode", choices=["badges", "points"], help="badges=完整打；points=只刷点数")
    run.add_argument("--strategy", action="append", default=None, help="策略名，可重复；不填则读配置/进度")
    run.add_argument("--target", type=int, default=None, help="每个策略需要的通关次数")
    run.add_argument("--wins", type=int, default=None, help="累计通关目标")
    run.add_argument("--state", default="progress.json", help="进度文件")
    run.add_argument("--max-runs", type=int, default=None, help="本次最多打几局")
    run.add_argument("--dry-run", action="store_true", help="只识别不点击")
    run.add_argument("--assume-win-on-unknown", action="store_true", help="结算识别失败时按胜利计")
    run.add_argument("--goal", default=None, help="购买聚焦目标：medal / task-1..7 / layer-300")
    run.add_argument("--build", default=None, help="打法：auto / amiya_economy / amiya_victoria / guard_swift / precision_arcane / fast_level")
    run.add_argument("--screenshot-dir", default=None)

    check = sub.add_parser("check", help="自检：设备、截图、模板、OCR", parents=[common])
    check.add_argument("--screenshot", default=None, help="保存一张当前截图")
    check.add_argument("--touch", action="store_true", help="同时测试 minitouch 启动（会 push 到设备）")

    probe = sub.add_parser("probe", help="抓一帧并打印场景/OCR，校准用", parents=[common])
    probe.add_argument("--save", default="probe.png", help="保存截图路径")

    discover = sub.add_parser("discover", help="扫描策略名（需停在卫戍协议主界面）", parents=[common])
    discover.add_argument("--out", default=None, help="把策略列表写入 JSON 文件")
    discover.add_argument("--rounds", type=int, default=4, help="滚动扫描轮数")

    status = sub.add_parser("status", help="查看进度", parents=[common])
    status.add_argument("--state", default="progress.json")

    plan = sub.add_parser("plan", help="打印拿满蚀刻章的刷取顺序与预计局数", parents=[common])
    plan.add_argument("--state", default="progress.json")
    plan.add_argument("--goal", default=None, help="购买聚焦目标：medal / task-1..7 / layer-300")
    plan.add_argument("--build", default=None, help="打法预设")

    init = sub.add_parser("init-config", help="生成一份默认配置", parents=[common])
    init.add_argument("--out", default="spa-farm.json")
    return parser


def setup_logging(level: str, log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def make_config(args) -> AppConfig:
    cfg = load_config(getattr(args, "config", None))
    cfg = cfg.merged(
        maa_dir=getattr(args, "maa_dir", None),
        serial=getattr(args, "serial", None),
        adb=getattr(args, "adb", None),
        mode=getattr(args, "mode", None),
        dry_run=getattr(args, "dry_run", None) or None,
        assume_win_on_unknown=getattr(args, "assume_win_on_unknown", None) or None,
        screenshot_dir=getattr(args, "screenshot_dir", None),
    )
    if getattr(args, "goal", None):
        cfg.policy.goal = args.goal
    if getattr(args, "build", None):
        cfg.policy.build = args.build
    return cfg


def cmd_run(args) -> int:
    cfg = make_config(args)
    if args.strategy:
        cfg.targets.strategies = list(args.strategy)
    if args.target is not None:
        cfg.targets.per_strategy_clears = args.target
    if args.wins is not None:
        cfg.targets.total_wins = args.wins
    if getattr(args, "goal", None):
        cfg.policy.goal = args.goal
    if cfg.mode == "badges":
        if not cfg.targets.strategies:
            catalog = SeasonCatalog.load()
            cfg.targets.strategies = catalog.default_strategies(cfg.targets.strategy_limit)
        plan = BadgePlan(
            cfg.targets.strategies,
            cfg.targets.per_strategy_clears,
            cfg.targets.total_wins,
            cfg.targets.strategy_limit,
        )
        problems = plan.validate()
        if problems and not cfg.targets.strategies:
            for problem in problems:
                LOG.error(problem)
            return 2
    runner = Runner(cfg, args.state, max_runs=args.max_runs)
    try:
        return runner.run()
    except (RunnerError, DeviceError, OcrUnavailable, VisionUnavailable) as exc:
        LOG.error("%s", exc)
        return 1


def cmd_check(args) -> int:
    cfg = make_config(args)
    ok = True
    try:
        adb = Adb(cfg.adb, cfg.serial)
        devices = Adb.list_devices(cfg.adb)
        print(f"adb devices: {devices}")
        if not cfg.serial:
            if len(devices) == 1:
                adb.serial = devices[0]
            elif not devices:
                print("[x] 没有检测到设备")
                return 1
        adb.ensure()
        size = adb.screen_size()
        print(f"[√] 设备 {adb.serial}，分辨率 {size[0]}x{size[1]}")
        shot = Screenshot(adb.screencap())
        print(f"[√] 截图 {shot.width}x{shot.height}")
        if args.screenshot:
            import cv2

            cv2.imwrite(args.screenshot, shot.raw)
            print(f"    已保存 {args.screenshot}")

        dirs = template_dirs(cfg.maa_dir)
        print(f"模板目录：{dirs or '（未配置 --maa）'}")
        if dirs:
            matcher = Matcher(dirs)
            missing = matcher.missing()
            if missing:
                ok = False
                print(f"[!] 缺少模板：{', '.join(missing)}")
            else:
                print("[√] 卫戍协议模板齐全")
            for alias in ("enter_quick", "goliath", "return_home"):
                match = matcher.find(shot, alias)
                print(f"    {alias}: {'命中 ' + str(match.rect.to_list()) if match else '未命中'}")
            ocr = OcrEngine(cfg.ocr_min_score)
            if ocr.available:
                perception = Perception(matcher, ocr)
                obs = perception.observe(shot)
                print(f"[√] OCR 可用，当前场景：{obs.scene}")
            else:
                print("[!] OCR 不可用：pip install rapidocr-onnxruntime")

        if args.touch:
            controller = Controller(adb, cfg.maa_dir)
            controller.start()
            print(f"    触控方式：{'minitouch' if controller.using_minitouch else 'adb input'}")
            controller.close()
    except (DeviceError, VisionUnavailable) as exc:
        print(f"[x] {exc}")
        return 1
    return 0 if ok else 1


def cmd_probe(args) -> int:
    cfg = make_config(args)
    adb = Adb(cfg.adb, cfg.serial)
    if not cfg.serial:
        devices = Adb.list_devices(cfg.adb)
        if len(devices) == 1:
            adb.serial = devices[0]
    adb.ensure()
    shot = Screenshot(adb.screencap())
    import cv2

    cv2.imwrite(args.save, shot.raw)
    print(f"截图：{args.save}  {shot.width}x{shot.height}")
    dirs = template_dirs(cfg.maa_dir)
    matcher = Matcher(dirs) if dirs else None
    ocr = OcrEngine(cfg.ocr_min_score)
    if matcher and ocr.available:
        obs = Perception(matcher, ocr).observe(shot)
        print(f"场景：{obs.scene}  结算：{obs.result}")
        for line in obs.texts:
            print(f"  {line.text!r} @ {line.rect.to_list()}")
    elif ocr.available:
        for line in ocr.read(shot):
            print(f"  {line.text!r} @ {line.rect.to_list()}")
    else:
        print("[!] OCR 不可用")
    return 0


def cmd_discover(args) -> int:
    cfg = make_config(args)
    cfg.mode = "badges"
    adb = Adb(cfg.adb, cfg.serial)
    devices = Adb.list_devices(cfg.adb)
    if not cfg.serial and len(devices) == 1:
        adb.serial = devices[0]
    adb.ensure()
    controller = Controller(adb, cfg.maa_dir)
    controller.start()
    ocr = OcrEngine(cfg.ocr_min_score)
    if not ocr.available:
        print("[x] 需要 OCR：pip install rapidocr-onnxruntime")
        return 1
    dirs = template_dirs(cfg.maa_dir)
    matcher = Matcher(dirs)
    perception = Perception(matcher, ocr)

    names: list[str] = []
    catalog = SeasonCatalog.load()
    print(f"赛季数据：{len(catalog.available_strategies)} 个可用策略，直接用 `plan` 也能生成默认计划")

    def collect(shot) -> None:
        for line in ocr.read(shot, S.STRATEGY_GRID):
            text = line.text.strip()
            matched = catalog.match_strategy(text)
            if matched is not None:
                if matched.name not in names:
                    names.append(matched.name)
                continue
            if 2 <= len(text) <= 8 and all("\u4e00" <= ch <= "\u9fff" for ch in text) and text not in names:
                names.append(text)

    try:
        # 先导航到策略页
        for _ in range(20):
            shot = controller.screenshot()
            obs = perception.observe(shot)
            if obs.scene == S.Scene.STRATEGY:
                break
            if obs.scene == S.Scene.ACTIVITY:
                match = perception.find(shot, "enter_quick")
                if match:
                    controller.tap(shot.to_actual(match.rect.center))
                    time.sleep(0.8)
                    continue
            ready = perception.find(shot, "ready_screen")
            if ready:
                controller.tap(shot.to_actual(ready.rect.center))
            time.sleep(0.8)
        else:
            print("[x] 没能导航到策略页，请先停在卫戍协议主界面")
            return 1

        for _ in range(max(1, args.rounds)):
            shot = controller.screenshot()
            collect(shot)
            actual = shot.to_actual(S.STRATEGY_GRID_PROBE)
            controller.swipe(actual, Point(actual.x, actual.y - 300), duration_ms=500)
            time.sleep(0.8)
    finally:
        controller.close()

    print(f"识别到 {len(names)} 个策略：")
    for name in names:
        print(" -", name)
    if args.out:
        Path(args.out).write_text(json.dumps({"strategies": names}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.out}")
    return 0


def cmd_status(args) -> int:
    progress = Progress.load(args.state)
    print(f"总场次：{progress.runs}，通关：{progress.wins}，中断：{progress.aborted}")
    avg = progress.average_run_seconds()
    rate = progress.win_rate()
    print(f"平均每局：{format_duration(avg)}")
    print(f"胜率：{rate * 100:.1f}%" if rate is not None else "胜率：暂无数据")
    for name, clears in sorted(progress.strategies.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {name}: {clears}")
    if progress.points:
        print(f"点数：{progress.points}（{progress.point_runs} 局）")
    return 0


def cmd_plan(args) -> int:
    cfg = make_config(args)
    catalog = SeasonCatalog.load()
    meta = catalog.meta
    targets = cfg.targets
    strategies = targets.strategies or catalog.default_strategies(targets.strategy_limit)
    plan = BadgePlan(
        strategies,
        targets.per_strategy_clears,
        targets.total_wins,
        targets.strategy_limit,
    )
    progress = Progress.load(args.state)

    data_version = (meta.get("data_version") or "?").splitlines()[0]
    print(f"赛季：{meta.get('name', '?')}（{meta.get('version', '?')}，数据 {data_version}）")
    print(f"可用策略：{len(catalog.available_strategies)} 个；本次计划使用 {len(plan.strategies)} 个")
    focus = build_focus(catalog, cfg.policy.goal, cfg.policy.focus_bonds)
    build = resolve_build(catalog, cfg.policy.build, None, cfg.policy.goal)
    print(f"默认打法：{build.name}（{build.id}）")
    print(f"购买聚焦：{focus.label}" + (f"（盟约：{', '.join(sorted(focus.bonds))}）" if focus.bonds else ""))
    print("可用打法：" + "、".join(f"{b.id}={b.name}" for b in BUILDS.values()))
    print()
    print("阶段 1 · 策略角标 + 60 胜")
    print(f"  策略：{len(plan.strategies)} × {plan.per_strategy_clears} 次 = {len(plan.strategies) * plan.per_strategy_clears} 胜")
    print(f"  目标：{plan.total_wins} 胜；按 100% 胜率预计 {plan.remaining_runs(progress.strategies, progress.wins)} 局")
    print("        （失败不消耗胜场，但会增加尝试次数）")
    print(f"  当前：{plan.status(progress.strategies, progress.wins).summary()}")
    print()
    print("阶段 2 · 关键目标（用 MAA fork 的 goal 选项逐条跑）")
    for goal in catalog.goals:
        print(f"  {goal.id}: {goal.label}，目标 {goal.layers} 层")
    print()
    print("阶段 3 · 300 层蚀刻章")
    print(f"  现有 fork 没有对应 goal；需要用「{catalog.goal('task-6').label if catalog.goal('task-6') else '奇迹/远见/投资人'}」")
    print(f"  经济流反复叠层，并在局内确认核心盟约达到 {catalog.etchings.core_bond_layers} 层。")
    print()
    print("提示：跑关键目标时加 `--goal task-N`，买卡会优先该目标盟约与叠层干员。")
    print("说明：蚀刻章要求「20 个策略各 3 次通关」+「60 胜」，两者恰好重合；")
    print("      不要勾选「彩色角标」（6 次），那是角标镀层，不是蚀刻章条件。")
    return 0


def cmd_init_config(args) -> int:
    save_default_config(args.out)
    print(f"已生成 {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # argparse 的 SUPPRESS 默认值不会写入 namespace，统一补 None
    for name in ("config", "maa_dir", "serial", "adb", "log_file"):
        if not hasattr(args, name):
            setattr(args, name, None)
    if not hasattr(args, "log_level"):
        args.log_level = "INFO"
    setup_logging(getattr(args, "log_level", "INFO"), getattr(args, "log_file", None))
    handlers = {
        "run": cmd_run,
        "plan": cmd_plan,
        "check": cmd_check,
        "probe": cmd_probe,
        "discover": cmd_discover,
        "status": cmd_status,
        "init-config": cmd_init_config,
    }
    return handlers[args.command](args)
