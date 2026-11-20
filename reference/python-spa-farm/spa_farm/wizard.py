"""Windows 双击启动向导。

目标：在一台已经装好 MAA 和 MuMu 的 Windows 电脑上，解压后双击 `启动.bat` 就能用，
不需要手动装 Python、不需要命令行参数。

做四件事：
1. 自动找 MAA 安装目录（找不到再让你粘贴路径）；
2. 自动找 adb（优先用 MAA 自带的，其次用包内 platform-tools）；
3. 自动选模拟器设备、写 `spa-farm.json`；
4. 给出菜单：自检 / 刷点数 / 刷角标 / 关键目标 / 计划。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .catalog import SeasonCatalog
from .config import AppConfig, config_from_dict
from .device import Adb, Controller, DeviceError
from .ocr import OcrEngine
from .planner import BadgePlan
from .runner import Runner, RunnerError
from .tracker import Progress
from .vision import Matcher, Screenshot, VisionUnavailable, template_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "spa-farm.json"


# ---------------- 环境探测 ----------------

def _valid_maa_dir(path: Path) -> bool:
    template = path / "resource" / "template"
    return (template / "MiniGame" / "SPA").is_dir() or (template / "StrongholdProtocol").is_dir()


def find_maa_dir(hint: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if hint:
        candidates.append(Path(hint))
    env = os.environ.get("MAA_DIR")
    if env:
        candidates.append(Path(env))
    if CONFIG_PATH.exists():
        try:
            configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("maa_dir")
            if configured:
                candidates.append(Path(configured))
        except (OSError, json.JSONDecodeError):
            pass
    roots = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Downloads",
        Path("D:/"),
        Path("E:/"),
        Path("F:/"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for name in ("MAA", "MaaAssistantArknights", "MAA-v6", "Maa"):
            candidates.append(root / name)
        try:
            for child in root.iterdir():
                if child.is_dir() and (child / "MAA.exe").exists():
                    candidates.append(child)
        except OSError:
            continue
    for candidate in candidates:
        try:
            if candidate and candidate.exists() and _valid_maa_dir(candidate):
                return candidate
        except OSError:
            continue
    return None


def find_adb(maa_dir: Path | None) -> Path | None:
    for candidate in (
        (maa_dir / "adb" / "adb.exe") if maa_dir else None,
        (maa_dir / "platform-tools" / "adb.exe") if maa_dir else None,
        BASE_DIR / "adb" / "adb.exe",
        BASE_DIR / "platform-tools" / "adb.exe",
    ):
        if candidate and candidate.is_file():
            return candidate
    import shutil

    which = shutil.which("adb")
    return Path(which) if which else None


def choose_serial(adb: Adb) -> str | None:
    for attempt in range(5):
        devices = Adb.list_devices(str(adb.adb))
        if len(devices) == 1:
            return devices[0]
        if len(devices) > 1:
            print("检测到多个设备：")
            for i, device in enumerate(devices, 1):
                print(f"  {i}. {device}")
            raw = input("请输入序号：").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(devices):
                return devices[int(raw) - 1]
        print("没有检测到设备，请先启动 MuMu 和明日方舟（5 秒后重试）……")
        time.sleep(5)
    return None


def load_or_create_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            return config_from_dict(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    data = {
        "mode": cfg.mode,
        "maa_dir": cfg.maa_dir,
        "adb": cfg.adb,
        "serial": cfg.serial,
        "targets": {
            "strategies": cfg.targets.strategies,
            "per_strategy_clears": cfg.targets.per_strategy_clears,
            "total_wins": cfg.targets.total_wins,
            "strategy_limit": cfg.targets.strategy_limit,
        },
        "policy": {"goal": cfg.policy.goal},
        "tiles": {
            "safe": [[p.x, p.y] for p in cfg.tiles.safe],
            "path": [[p.x, p.y] for p in cfg.tiles.path],
            "rest": [[p.x, p.y] for p in cfg.tiles.rest],
            "lift": [cfg.tiles.lift.x, cfg.tiles.lift.y],
        },
    }
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_environment(cfg: AppConfig) -> bool:
    maa = find_maa_dir(cfg.maa_dir)
    if maa is None:
        print("没有自动找到 MAA。请把 MAA 安装目录粘贴到下面（例如 D:\\MAA）。")
        while True:
            raw = input("MAA 目录：").strip().strip('"')
            if raw and _valid_maa_dir(Path(raw)):
                maa = Path(raw)
                break
            print("这个目录里没有 resource\\template\\MiniGame\\SPA，请确认是 MAA 安装目录。")
    cfg.maa_dir = str(maa)
    print(f"[√] MAA：{maa}")

    adb = find_adb(maa)
    if adb is None:
        print("[x] 找不到 adb.exe。请确认 MAA 目录下有 adb\\adb.exe，或把 platform-tools 放到本目录。")
        return False
    cfg.adb = str(adb)
    print(f"[√] adb：{adb}")

    client = Adb(cfg.adb, cfg.serial)
    serial = choose_serial(client)
    if not serial:
        print("[x] 没能连接模拟器。请确认 MuMu 已启动、MAA 能连上。")
        return False
    cfg.serial = serial
    print(f"[√] 设备：{serial}")
    save_config(cfg)
    return True


# ---------------- 功能 ----------------

def do_check(cfg: AppConfig) -> None:
    dirs = template_dirs(cfg.maa_dir)
    print(f"模板目录：{dirs}")
    if dirs:
        matcher = Matcher(dirs)
        missing = matcher.missing()
        print("[√] 模板齐全" if not missing else f"[!] 缺少模板：{', '.join(missing)}")
    else:
        print("[x] 没找到 resource/template/StrongholdProtocol 或 MiniGame/SPA")
    adb = Adb(cfg.adb, cfg.serial)
    try:
        shot = Screenshot(adb.screencap())
        print(f"[√] 截图 {shot.width}x{shot.height}")
    except (DeviceError, VisionUnavailable) as exc:
        print(f"[x] 截图失败：{exc}")
        return
    ocr = OcrEngine()
    print("[√] OCR 可用" if ocr.available else "[!] OCR 不可用（缺 rapidocr）")
    ctrl = Controller(adb, cfg.maa_dir)
    try:
        ctrl.start()
        print(f"[√] 触控：{'minitouch' if ctrl.using_minitouch else 'adb input（部署可能失败）'}")
    except DeviceError as exc:
        print(f"[!] 触控初始化失败：{exc}")
    finally:
        ctrl.close()


def do_plan(cfg: AppConfig) -> None:
    catalog = SeasonCatalog.load()
    plan = BadgePlan(
        cfg.targets.strategies or catalog.default_strategies(cfg.targets.strategy_limit),
        cfg.targets.per_strategy_clears,
        cfg.targets.total_wins,
        cfg.targets.strategy_limit,
    )
    progress = Progress.load(BASE_DIR / "progress.json")
    print(f"赛季：{catalog.meta.get('name')}，可用策略 {len(catalog.available_strategies)} 个")
    print(f"阶段 1：{len(plan.strategies)} 策略 × {plan.per_strategy_clears} 次 = "
          f"{len(plan.strategies) * plan.per_strategy_clears} 胜（目标 {plan.total_wins} 胜）")
    print(f"当前：{plan.status(progress.strategies, progress.wins).summary()}")
    print("阶段 2：关键目标 " + "、".join(g.id for g in catalog.goals))
    print("阶段 3：300 层（暂无自动读取层数，用经济流手动确认）")


def do_run(
    cfg: AppConfig,
    mode: str,
    clears: int,
    wins: int,
    goal: str,
    strategies: list[str] | None,
    max_runs: int | None = None,
    dry_run: bool = False,
) -> None:
    cfg.mode = mode
    cfg.targets.per_strategy_clears = clears
    cfg.targets.total_wins = wins
    cfg.policy.goal = goal
    cfg.dry_run = dry_run
    if strategies:
        cfg.targets.strategies = strategies
    runner = Runner(cfg, BASE_DIR / "progress.json", max_runs=max_runs)
    try:
        runner.run()
    except (RunnerError, DeviceError) as exc:
        print(f"[x] {exc}")


def menu(cfg: AppConfig) -> None:
    while True:
        print()
        print("=" * 46)
        print("  卫戍协议刷取工具")
        print("=" * 46)
        print("  1. 自检（设备/模板/OCR/触控）")
        print("  2. 只刷点数（建议先跑这个验证连接）")
        print("  3. 刷策略角标（20 策略 × 3 次 = 60 胜）")
        print("  4. 刷关键目标（task-1..7）")
        print("  5. 查看计划与进度")
        print("  6. 演练一局（只识别不点击，检查坐标/OCR）")
        print("  0. 退出")
        choice = input("请选择：").strip()
        if choice == "1":
            do_check(cfg)
        elif choice == "2":
            raw = input("刷几局？（留空 = 一直刷，Ctrl+C 停）：").strip()
            max_runs = int(raw) if raw.isdigit() else None
            do_run(cfg, "points", 0, 0, "medal", None, max_runs=max_runs)
        elif choice == "3":
            raw = input("每个策略通关几次？3=普通标识，6=彩色（留空 3）：").strip()
            clears = int(raw) if raw in ("3", "6") else 3
            raw_wins = input("目标胜场（留空 60）：").strip()
            wins = int(raw_wins) if raw_wins.isdigit() else 60
            do_run(cfg, "badges", clears, wins, "medal", None)
        elif choice == "4":
            goal = input("目标编号（task-1..task-7）：").strip()
            if not goal.startswith("task-"):
                print("编号不对")
                continue
            strategy = input("用哪个策略刷？（留空 = 杰西卡）：").strip() or "杰西卡"
            do_run(cfg, "badges", 1, 1, goal, [strategy])
        elif choice == "5":
            do_plan(cfg)
        elif choice == "6":
            do_run(cfg, "badges", 3, 60, "medal", None, max_runs=1, dry_run=True)
        elif choice == "0":
            return
        else:
            print("请输入 0-5")


def main(argv: list[str] | None = None) -> int:
    try:
        os.system("chcp 65001 >nul")
    except OSError:
        pass
    print("卫戍协议刷取工具 · 首次启动会查找 MAA 和模拟器")
    cfg = load_or_create_config()
    if not ensure_environment(cfg):
        input("按回车退出……")
        return 1
    if argv and "--check" in argv:
        do_check(cfg)
        input("按回车退出……")
        return 0
    try:
        menu(cfg)
    except KeyboardInterrupt:
        print("\n已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
