# 在 Dr-hydra 代码上做优化（需要重新编译 Windows 版）

先说结论：**这台机器是 macOS，没有 MSVC，也没有 Windows 环境，无法产出可运行的
`MaaCore.dll`/`MAA.exe`。** 下面是可以直接改的代码点和构建方式；改完必须重新编译，
否则只能用现成 release 按 `使用方案.md` 的 3/60 配置跑。

## 1. 默认局数 20 → 60（最小改动，收益最大）

文件：`src/MaaWpfGui/Configuration/Single/Settings/MiniGame.cs`

```csharp
// 原
public int SPAMaxRuns { get; set; } = 20;
// 改
public int SPAMaxRuns { get; set; } = 60;
```

说明：60 = 20 策略 × 3 次，正好覆盖蚀刻章；默认 20 会提前停。
如果不想改默认值，也可以在 GUI 里手动填 60（现成 release 就能做）。

## 2. 给失败尝试加上限，避免卡在一个策略上刷一整晚

文件：`src/MaaCore/Task/MiniGame/SPAFarmTaskPlugin.cpp`，`_run()` 主循环末尾：

```cpp
if (m_runs_completed >= m_runs) {
    break;
}
// 新增：尝试次数上限（set_params 已经解析了 attempts，但主循环没用）
if (m_attempts > 0 && m_attempts_done >= m_attempts) {
    stop_reason = "达到尝试次数上限";
    finished_ok = false;
    break;
}
```

对应 GUI 里把 `attempts` 暴露出来（`AsstProxy`/`ToolboxViewModel` 已有参数透传，
加一个 NumericUpDown 即可）。

## 3. 达到局数但没刷满时，汇总要明确提示

同文件 `report_task_summary()` 已经会打印「已达标策略 x/31」。
把 `stop_reason` 在 `m_runs_completed >= m_runs` 时改成：

```cpp
stop_reason = "达到设定通关局数上限（" + std::to_string(m_runs) + " 胜），策略 "
              + std::to_string(m_done_strategies.size()) + "/" + std::to_string(total_available_strategies())
              + " 已达标";
```

避免用户以为已经拿满。

## 4. 策略指纹缓存落盘（省每局开局 5~15 秒）

`m_seen_strategy_icons`（12×12 灰度 + 名字）目前只在内存里，MAA 重启后要重新点一遍
所有策略格。可以在 `load_all_data()` 后从 `debug/spa_strategy_cache.json` 读取，
在 `handle_strategy_screen()` 新增策略时写回。

数据结构：

```json
{"version":1,"icons":[{"name":"阿米娅","pixels":[0,12,...144个]}]}
```

收益主要在重启后的第一局；连续跑时缓存已在内存，收益小。

## 5. 300 层 goal（缺口，工作量最大）

`GoalTaskSpec.layers` 定义了但没被读取。要补：

1. 在休整期 OCR 右侧「核心盟约」面板，读目标盟约的层数（界面坐标需实机校准）；
2. 每局记录最大值，达到 300 置 `goal_done` 并停止；
3. `kGoalTasks` 加 `{"layer-300", {"奇迹","远见","投资人"}, 300, {"杰西卡"}}`；
4. GUI 的 goal 列表加一项和本地化。

没有实机截图无法定 ROI，这一项建议拿到截图后再做。

## 6. 构建方式（二选一）

### A. 本地 Windows + Visual Studio

MAA 官方文档：`docs/zh-cn/develop/development.md`。需要 VS 2022 + CMake + .NET 10 SDK，
首次还要跑 `tools/maadeps-download.py x64-windows`，编译 20~40 分钟。

### B. GitHub Actions（推荐，不用装 VS）

1. Fork `Dr-hydra/MaaAssistantArknights` 到你的账号；
2. 把改好的 `MiniGame.cs` / `SPAFarmTaskPlugin.cpp` 上传覆盖；
3. 推到 `release/spa` 分支（仓库自带 `.github/workflows/release-spa.yml`，
   监听这个分支，自动构建 Windows 完整包）；
4. Actions 跑完后在 Release/Artifacts 下载 `MAA-v6.22.0-spa.1-win-x64.zip`。

> 这一步需要你的 GitHub 账号；我这边没有凭据，不能替你推。

## 7. 不要做的事

- 不要用 Python 版对局 AI 替代这套：fork 的买卡/布阵/装备/召唤物是逐函数移植的，
  重写只会丢细节。
- 不要为了「彩色角标」刷 6 次：那是角标镀层，不是蚀刻章条件。
- 不要覆盖官方 MAA 目录：fork 版本号低，自动更新会把插件冲掉。
