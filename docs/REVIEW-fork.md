# Dr-hydra/MaaAssistantArknights 卫戍协议实现：代码审查与优化建议

审查对象：fork `Dr-hydra/MaaAssistantArknights`，分支 `pr/spa-badge-farm`（PR #19308），
以及 release `v6.22.0-spa.1`（`MAA-v6.22.0-spa.1-win-x64.zip`）。

结论先行：**这个实现比从零写的 Python 版完整得多，应该以它为主力**。
它已经覆盖：选策略（读面板通关次数/刻章）、买卡/刷新/升级、合成、装备分发、
召唤物、布阵与朝向、结算统计、断线/签到/公告等浮层处理，以及 7 条关键目标（叠层）任务线。
下面只列“还能优化什么”，不重复它已经做对的部分。

---

## 1. 它现在怎么工作（核对源码后）

- 入口：`MiniGame@SPA@BadgeFarm` → `SPAFarmTaskPlugin::_run()`（`src/MaaCore/Task/MiniGame/SPAFarmTaskPlugin.cpp`）。
- 参数：`profile`（low/full）、`goal`（`medal` 或 `task-1..7`）、`medalWins`（3/6）、
  `mode`（quick/standard）、`runs`（通关局数上限）、`attempts`。
- 策略数据：`resource/SPAFarm/farm-rules.json`，61 个策略，**其中 available=true 31 个**（21 普通 + 10 盟约）。
- 计数：`report_match_finished()` 里 **`m_runs_completed` 只在胜利时 +1**，失败只加 `m_attempts_done`；
  主循环用 `m_runs_completed >= m_runs` 停。这个语义是对的：`runs=60` 表示 60 胜，不是 60 次尝试。
- 完成判定：medal 模式在 `handle_strategy_screen()` 里要求**所有 available 策略**都达到 target 才停。

## 2. 对“拿满蚀刻章”的直接影响

按规程蚀刻章条件（60 胜、20 个策略普通标识、9 枚前置章、核心盟约 300 层）：

| 目标 | 现有实现 | 建议设置 |
| --- | --- | --- |
| 60 胜 | 支持 | `runs=60` |
| 20 个策略 × 3 次 | 支持，但默认会刷满 31 个策略 | 目标 3 次，`runs=60` 会在 20 个策略满次时停下 |
| 7 条关键目标 | 支持 | 依次跑 `task-1..7`，每次 1 局起 |
| 300 层 | **没有对应 goal** | 目前只能手动用 `task-6` 的经济流多打几局，看不到层数进度 |

**最优配置（不改代码）**：

```
模式：刷角标
目标：策略徽章（medal）
模拟：极速模拟
低配：按你的编队情况
彩色角标：不勾（3 次即可满足“普通标识”；6 次是角标镀层，不是蚀刻章）
最大通关局数：60
```

这样 60 胜正好覆盖 20 个策略 × 3 次，比默认刷满 31 个策略（93 胜）少约 35% 的局数。

## 3. 可优化的点（按收益排序）

### 3.1 300 层没有目标（缺口，不是性能问题）

`GoalTaskSpec` 定义了 `layers` 字段（100/50），但全文件**没有任何地方读取它**：

```cpp
struct GoalTaskSpec { std::string id; std::vector<std::string> bonds; int layers = 100; ... };
const std::vector<GoalTaskSpec> kGoalTasks = {
    { "task-1", { "炎", "莱塔尼亚", "奥术" }, 100, { "杰西卡" } },
    ...
    { "task-6", { "奇迹", "远见", "投资人" }, 50, { "杰西卡" } },
};
```

也就是说 task-6 只负责“用经济盟约打一局”，并不会检查“核心盟约到没到 50/300 层”，
更不会在 300 层时停。要补这个目标需要：

1. 在休整期 OCR「核心盟约」面板，读出目标盟约当前层数（界面在右侧，`m_active_core_bonds` 已有盟约名）；
2. 每局记录最大值，达到 300 就置 `goal_done` 并停止；
3. 加一个 `layer-300` goal（bonds 用 `{奇迹, 远见, 投资人}` 或按蚀刻章要求选一个核心盟约）；
4. GUI 增加选项与本地化。

这是唯一一个“现有实现拿不到”的蚀刻章，优先级最高。

### 3.2 默认 `runs=20` 与“刷满”语义冲突

`MiniGame.cs` 里 `SPAMaxRuns` 默认 20，UI 上限 999。
medal 模式要 31×3=93 胜才会自然结束，默认 20 会在第 20 胜时静默停止，
用户容易以为“刷完了”。建议：

- 默认值改成 0 = 不限制（或用 `available × target` 自动算）；
- 启动日志里明确打印“预计需要 N 胜”；
- 达到 `runs` 但策略未刷满时，汇总里标记“未完成”。

### 3.3 策略页每次全量扫描

`handle_strategy_screen()` 每次选策略都要：最多 40 页 × 每页 4 列，
未知格子要点击 + 读右侧面板 + 可能滚动。`m_seen_strategy_icons` 只存在内存里，
MAA 重启后要重新点一遍所有格子。

优化：

- 把「格子指纹 → 策略名」缓存持久化到 `debug/` 或配置目录，重启后直接按指纹识别；
- 已达标策略在指纹命中后直接跳过（现在已做到，但依赖缓存）；
- 记录每页的滚动偏移，直接跳到第一个未完成策略所在页（需要位置稳定性，风险中等）。

预期：每局开局省 5~15 秒，60 局约 5~15 分钟；主要是重启后的首局收益大。

### 3.4 固定 sleep 偏多

全文 54 处 `sleep_ms/sleep_sec`，热点路径上常见 800/1000/1200ms 的固定等待
（买卡、升级、部署、结算）。其中一部分可以改成“轮询状态变化”：

- 升级：等资金变化或按钮位移（≤400ms 轮询）；
- 买卡：等资金下降或「资金不足」出现；
- 结算：等「返回主页」可点，而不是固定 1500ms。

预期：每局 1~3 分钟，60 局 1~3 小时。风险：轮询过密会拖慢截图/OCR，需要按实测调。

### 3.5 `attempts` 参数没有参与主循环

`set_params()` 解析了 `attempts`，但 `_run()` 没有用 `m_attempts_done >= m_attempts` 做上限。
失败率高的阵容会无限尝试（只受防卡死保护）。建议加上限，避免“卡在一个策略上刷一晚上”。

### 3.6 单文件 1.3 万行

`SPAFarmTaskPlugin.cpp` 13034 行、头文件 941 行，函数最长近千行。
不影响运行，但 review/合并/后续赛季维护成本很高。若要进上游，建议按
`screen/`、`shop/`、`deploy/`、`strategy/`、`data/` 拆分（PR #19308 的 review 里也会被要求）。

## 4. 不建议做的事

- 不要再写一套 Python CV 对局 AI：这个 fork 的识别/布阵/装备/召唤物逻辑已经是实测过的，
  重写只会丢掉这些细节。
- 不要用 `input swipe` 替代 MAA 的 minitouch：部署的“按住-抓起-预览”必须精确触控。

## 5. 如果要改，建议的最小改动顺序

1. `runs` 默认值与“未完成”提示（10 行以内，零风险）；
2. `attempts` 上限（5 行）；
3. 策略指纹缓存持久化（50 行）；
4. `layer-300` goal + 层数 OCR + 停止条件（200~400 行，需要实机校准 ROI）；
5. 固定 sleep → 轮询（分散在热点函数，逐处改，收益最大但最需要实测）。

## 6. 许可与来源

该 fork 基于 MAA（AGPL-3.0），`resource/SPAFarm/` 的数据与 `SPAFarmTaskPlugin.cpp`
注明是逐函数移植自小黑盒扩展 `ai-desktop.arknights-medal-farm` 的 `core/service.pretty.mjs`，
上游为 GPL-3.0-or-later。若要合并进 MAA 官方仓库，需要保留归属说明并确认许可兼容；
自用/自己发行则按 AGPL-3.0 处理。
