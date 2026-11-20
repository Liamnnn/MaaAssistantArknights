# spa-farm

《明日方舟》「卫戍协议」刷取工具（独立 Python 实现，复用 MAA 的界面坐标与模板）。

> **状态：v0.1 / 需要实机校准。**
> 代码结构、进度记账、策略轮换、设备控制已经完成并有单元测试；
> 对局内的购买/部署策略是「可运行的基线」，胜率需要在你的机器上用 `--dry-run` 和日志校准。
> 详见 [docs/DESIGN.md](docs/DESIGN.md) 的「已知限制」。

## 它解决什么问题

MAA 主线的卫戍协议任务（`MiniGame@SPA`）只做一件事：
进「极速模拟」→ 等到第 5 回合 → 退出 → 再进，用来刷卫戍认证点数。
它**不打完一局**，所以拿不到「通关 N 次」类的蚀刻章/策略角标。

这个工具补上后半段：

| 能力 | 说明 |
| --- | --- |
| 点数模式 | 沿用 MAA「第 5 回合退出」的思路，但等待改成轮询 + 自适应，不再固定 sleep |
| 完整对局 | 读商店 → 买干员 → 升级 → 部署 → 开战 → 结算，一局一局打 |
| 目标盟约购买 | 参考 fork 的 goal 机制：task-N/layer-300 时优先目标盟约与叠层干员 |
| 攻略 build | 5 套社区打法（阿米娅助力维/经济、坚守迅捷、精准奥术、速本），`--build` 切换 |
| 胜率统计 | 每局记录 win/loss，`status` 显示总胜率与近 20 局胜率 |
| 策略轮换 | 按配置顺序把每个策略刷到目标次数，再自动换下一个 |
| 进度持久化 | 每局落盘，进程被杀也能续跑；支持 ETA、每策略次数统计 |
| 多分辨率 | 识别统一在 1280×720 基准图，点击换算到 1920×1080 / 1600×900 |
| 可校准 | `check` / `probe` / `discover` 三个命令 + 失败自动截图 |
| 安全 | `--dry-run` 只识别不点击；单步日志可审计 |

## 前置条件

1. Windows 10/11，Python 3.10+。
2. 已安装 MAA 6.x，并且 MAA 能正常连接模拟器。
   - 本工具只**读取** MAA 的 `resource/template` 和 `resource/minitouch`，不修改任何 MAA 文件。
3. 模拟器 1920×1080 横屏，游戏使用默认主题；卫戍协议内「更换主题」保持默认。
4. 安装 `rapidocr-onnxruntime`（两种模式都需要 OCR：点数模式要读回合号）。
4. 已解锁「极速模拟」，并且游戏停在卫戍协议活动主界面（能看到「极速模拟」入口）。
5. 首次使用建议先跑 `check`。

minitouch 很关键：部署干员需要「按住 → 持续移动 → 拖到格位」，
`adb shell input swipe` 抓不起干员。工具会优先使用 MAA 自带的 minitouch；
如果启动失败会退回 adb input，并明确提示（此时部署大概率失败）。

## Windows 免安装包（推荐）

如果目标电脑已经装了 MAA 和 MuMu，直接下载 `spa-farm-win64-v0.4.zip`：

1. 解压整个 `spa-farm-win64` 文件夹（路径尽量短，不要中文）；
2. 启动 MuMu + 明日方舟，进入卫戍协议主界面；
3. 双击 `start.bat`，按提示选择菜单。

包内自带 Python 3.12、opencv、onnxruntime、RapidOCR 模型和 platform-tools，
不需要安装 Python 或 pip；只需要 MAA 的 `resource/template` 和 `resource/minitouch`。

## 从源码安装

```powershell
cd spa-farm
python -m pip install -r requirements.txt
```

## 快速开始

```powershell
# 0) 自检：设备、截图、模板、OCR
python -m spa_farm check --maa "C:/Program Files/MAA" --touch

# 1) 只刷点数（最稳，先验证连接和导航）
python -m spa_farm run --maa "C:/Program Files/MAA" --mode points --max-runs 3

# 2) 看一眼「拿满蚀刻章」的计划与局数（内置赛季数据，不需要先 discover）
python -m spa_farm plan

# 3) 先 dry-run 看识别和决策是否正确（用内置的 20 个策略）
python -m spa_farm run --maa "C:/Program Files/MAA" --mode badges --dry-run --max-runs 1

# 4) 实跑
python -m spa_farm run --maa "C:/Program Files/MAA" --mode badges

# 5) 查进度
python -m spa_farm status --state progress.json

# 可选：自己扫一遍策略页，核对 OCR 与数据里的名字
python -m spa_farm discover --maa "C:/Program Files/MAA" --out strategies.json
```

`run.bat` 等价于 `python -m spa_farm`，可以直接把参数接在后面。

## 常用参数

| 参数 | 说明 |
| --- | --- |
| `--maa` | MAA 安装目录（必需） |
| `--serial` | adb 序列号；只连一个设备时可省略 |
| `--mode points/badges` | 点数 / 完整对局 |
| `--strategy A --strategy B` | 覆盖配置里的策略列表 |
| `--target 6` | 每个策略通关次数（3=金角标，6=镀层） |
| `--wins 60` | 累计通关目标 |
| `--max-runs N` | 本次最多几局 |
| `--dry-run` | 只识别、不点击 |
| `--goal` | 购买聚焦：`medal` / `task-1..7` / `layer-300` |
| `--build` | 打法：`auto` / `amiya_economy` / `amiya_victoria` / `guard_swift` / `precision_arcane` / `fast_level` |
| `--assume-win-on-unknown` | 结算标题识别失败时按胜利计（默认不计） |
| `--log-level DEBUG` | 打印每次点击/OCR |

## 配置

`init-config` 生成的 JSON 里主要字段：

```jsonc
{
  "mode": "badges",
  "maa_dir": "C:/Program Files/MAA",
  "serial": "",
  "targets": {
    // 留空 = 自动用内置赛季数据里的可用策略；strategy_limit=20 对应蚀刻章要求
    "strategies": [],
    "per_strategy_clears": 3,
    "strategy_limit": 20,
    "total_wins": 60
  },
  "policy": {
    "goal": "medal",                 // medal / task-1..7 / layer-300
    "priorities": ["塔露拉", "维什戴尔", "..."]  // 泛用购买权重
  },
  "tiles": {
    "safe": [[802, 297], [810, 365]],
    "path": [[872, 233], [795, 233], [883, 297]],
    "rest": [[894, 365], [907, 439], [995, 439]],
    "lift": [643, 439]
  }
}
```

`tiles` 来自 MAA 的 `stronghold_protocol/regulation/tiles.json`（720p 基准），
如果新赛季地图变了，用 `probe` 截图后按同样格式改。

## 目录

```
spa_farm/
  device.py      ADB 截图、minitouch 触控、回落 input
  vision.py      模板匹配、颜色判定、备战席差分
  ocr.py         RapidOCR 封装与数字规整
  screens.py     720p 基准 ROI / 模板别名 / 场景枚举
  perception.py  场景判定（结算/策略/编队/休整/弹窗/活动中）
  battle.py      商店解析、购买、升级、部署、开战
  catalog.py     赛季数据（策略/盟约/干员/目标）与名称模糊匹配
  data/          内置赛季数据（来自 fork 的 SPAFarm 资源，已裁剪）
  planner.py     角标目标与最少局数调度
  tracker.py     进度持久化与 ETA
  runner.py      状态机主循环（points / badges）
  cli.py         命令行
tests/           单元测试（23 个，不依赖设备）
docs/DESIGN.md   设计、与 MAA 的差异、校准步骤、路线图
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试覆盖：坐标换算、调度（含 20 策略上限）、赛季数据与名称模糊匹配、目标盟约评分、
进度持久化、商店 OCR 行解析、结算记账/去重。当前 46 个测试。
视觉和触控需要真机，不在单元测试范围内。

## 与 MAA 的关系

- 策略名单、盟约、干员、关键目标层数来自 `Dr-hydra/MaaAssistantArknights` 的
  `resource/SPAFarm/`（游戏数据经 torappu/PRTS），已裁剪为 `spa_farm/data/season_regulation.json`；
- 界面坐标、模板、部署格位数据来自 MAA 官方仓库的卫戍协议任务资源；
- 状态机与「第 5 回合退出」思路参考 MAA 的 `MiniGame@SPA` 链；
- 买卡/部署策略参考 MAA PR #19325（`feat/stronghold-protocol`）公开的公开实现，
  但为独立 Python 重写，没有复制其源码。

MAA 以 AGPL-3.0 发布；本工具复用其资源数据，同样按 AGPL-3.0 使用与分发。

## 已知限制（必读）

1. **对局策略未经实机验证，无法保证胜率。** 现在的 build 把社区攻略的盟约/干员/升级节奏
   编码进去了，但发牌、账号、OCR 误差都会影响结果；详见 [docs/STRATEGY.md](docs/STRATEGY.md)。
2. **300 层蚀刻章**不在本工具里：`plan` 会把它列为阶段 3，需要手动用经济流
   （奇迹/远见/投资人）叠层；专门的叠层策略模块还没做（见 DESIGN 的路线图）。
3. **结算结果识别**依赖「模拟完成 / 模拟中断」两行字；识别不到时默认不计胜场，
   可用 `--assume-win-on-unknown` 放宽。
4. **策略名 OCR** 受字体/主题影响；内置数据 + 模糊匹配能兜住大部分错字，但 `discover` 后仍建议人工核对一遍。
5. 每局 10~15 分钟是正常的（60 胜 ≈ 10 小时以上），建议挂着跑并注意模拟器稳定性。
