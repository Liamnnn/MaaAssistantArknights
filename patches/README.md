# 补丁使用说明

`spa-optimize.patch` 针对 `Dr-hydra/MaaAssistantArknights` 的 `pr/spa-badge-farm`。

改动只有 3 处，都是“少跑冤枉路”，不改 AI 的买卡/布阵逻辑：

1. `SPAMaxRuns` 默认 20 → 60（20 策略 × 3 次）；
2. `SPAFarmTaskPlugin::set_params` 里 `runs` 默认 20 → 60；
3. 主循环补上 `attempts` 上限，并在达到局数上限时把汇总原因写清楚。

## 应用

```bash
git clone --depth 1 -b pr/spa-badge-farm https://github.com/Dr-hydra/MaaAssistantArknights
cd MaaAssistantArknights
git apply /path/to/spa-optimize.patch
git diff --stat
```

如果 `git apply` 报上下文不符（分支更新过），直接替换这两个文件：
- `src/MaaWpfGui/Configuration/Single/Settings/MiniGame.cs`（本目录附了改好的完整文件）
- 按 patch 里的两个 hunk 手动改 `SPAFarmTaskPlugin.cpp`

## 构建

- 本地：VS 2022 + CMake + .NET 10 SDK，按 `docs/zh-cn/develop/development.md`；
- 或者推到你自己 fork 的 `release/spa` 分支，仓库自带的
  `.github/workflows/release-spa.yml` 会自动构建 Windows 完整包。

改完必须重新编译，`MaaCore.dll`/`MAA.exe` 才会生效；只替换 `resource` 不生效。

## 不共享凭据的做法（推荐）

1. 在 GitHub 网页上 fork `Dr-hydra/MaaAssistantArknights`；
2. 在你的 fork 里新建分支 `release/spa`（从 `pr/spa-badge-farm` 起）；
3. 用网页的 “Upload files” 覆盖这两个文件：
   - `src/MaaCore/Task/MiniGame/SPAFarmTaskPlugin.cpp`
   - `src/MaaWpfGui/Configuration/Single/Settings/MiniGame.cs`
4. 提交后，仓库自带的 `release-spa.yml` 会自动构建；
5. Actions 跑完（约 30~60 分钟）在 Release/Artifacts 下载 `MAA-v6.22.0-spa.1-win-x64.zip`。

这条路不需要把任何 token 给我。
