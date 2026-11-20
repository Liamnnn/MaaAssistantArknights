# 交接说明

## 目标

用 `Dr-hydra/MaaAssistantArknights`（卫戍协议角标刷取）刷满蚀刻章；
以后改代码在 Windows 本地构建，不走 GitHub Actions（太慢）。

## 已经确认的事实

- MAA 主线只有“刷点数”：进极速模拟、第 5 回合退出，不打完一局；
- Dr-hydra 的 fork 才有完整 AI：选策略、买卡、升级、布阵、结算；
- 当前赛季共 61 个策略，其中 **31 个 available**；
- 蚀刻章要求「20 个策略各 3 次通关」+「60 胜」，**20×3=60**，刚好重合；
- fork 默认 `最大通关局数=20`，会在第 20 胜停下，只完成约 7 个策略（坑）；
- 刷满 31 个可用策略要 93 胜，多 33 局；勾“彩色角标”（6 次）对蚀刻章没有额外帮助；
- `GoalTaskSpec.layers` 定义了但没被使用 → **fork 没有 300 层 goal**；
- 胜率无法保证：发牌、账号干员、OCR 误差都会影响。

## 当前产物

- Release：https://github.com/Liamnnn/MaaAssistantArknights/releases/tag/v6.22.0-spa.1
- 文件：`MAA-v6.22.0-spa.1-win-x64.zip`（281MB）
- SHA256：`0996b31dc19fb792a96eada8f6bbf769a1493872e42174ff08536015cef96214`
- 构建 run：`44664334236`（success），提交 `1a54f6c714`
- 补丁：默认 60 局、attempts 上限、达到上限时汇总写清楚进度

## 下一步（在 Windows 上）

1. 装环境：VS 2022（C++ + .NET 桌面）、CMake、Git、Python、.NET SDK 10.0.302；
2. 按 [docs/BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md) 做一次全量构建；
3. 以后只改 `SPAFarmTaskPlugin.cpp` 时：
   ```powershell
   .\build\build-spa.ps1 -InstallDir "D:\MAA-spa"
   ```
   约 1~3 分钟，替换 `MaaCore.dll` 即可；
4. 启动任务：优先用 `build/spa-headless.ps1`（见 `docs/HEADLESS.md`），
   不依赖 GUI 点击；等级12/300 先手动进对局再 `-Runs 1`；
5. 优先做这几个改动：
   - **300 层 goal**：需要休整期右侧「核心盟约」面板截图，定层数 OCR 的 ROI；
   - 达到 20 个策略就停（而不是 31 个）；
   - 策略指纹缓存落盘（省重启后首局扫描时间）；
   - 按“简单策略优先”排序，进一步降胜率风险；
5. 实测：跑 10 局，看日志里的胜率；低于 60% 再调。

## 跑法速查

小工具 → 牛杂 → 卫戍协议：

- 模式：刷角标
- 目标：策略徽章
- 模拟：极速模拟
- 低配：有自选编队就不勾
- 彩色角标：不勾
- 最大通关局数：60

刷完 60 胜后，目标依次切 `task-1` … `task-7`，每项先填 3 局。
300 层用 `task-6` 经济流手动确认。

## 不要做

- 不要覆盖官方 MAA 目录；fork 版本号低，自动更新会覆盖插件；
- 不要为了“彩色角标”刷 6 次；
- 不要把 GitHub token 写进仓库或聊天；
- 不要用 Python 版对局 AI 替代 fork（买卡/布阵/装备细节不如 fork）。

## 已知坑

- 只换 `MaaCore.dll` 不会更新 `resource/`；改资源要手动覆盖；
- 改 WPF 必须 `dotnet publish`，只换 DLL 不生效；
- 构建目录加杀毒白名单；
- 游戏必须 1920×1080、默认主题、关闭按键提示、从卫戍协议主界面开始、无未完成对局。
