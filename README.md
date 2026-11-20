# 卫戍协议刷取优化 · 上下文仓库

这个仓库是把一次完整的优化过程打包下来，方便换到 Windows 电脑后继续：
**用 Dr-hydra 的 MAA 构建刷卫戍协议蚀刻章，并在本地做代码级优化。**

## 先读什么

1. [HANDOFF.md](HANDOFF.md)：现在到哪一步、下一步做什么、有哪些坑；
2. [docs/RUNBOOK.md](docs/RUNBOOK.md)：现成 release 的 3/60 跑法（改设置就能用）；
3. [docs/BUILD-WINDOWS.md](docs/BUILD-WINDOWS.md)：Windows 本地构建，增量编译 1~3 分钟；
4. [docs/CODE-OPTIMIZATION.md](docs/CODE-OPTIMIZATION.md)：已做的补丁和待做的 300 层目标；
5. [docs/CONVERSATION.md](docs/CONVERSATION.md)：完整对话记录（已脱敏）。

## 当前状态

- 上游：`Dr-hydra/MaaAssistantArknights`（PR #19308 的完整角标刷取实现）；
- 已构建：`MAA-v6.22.0-spa.1-win-x64.zip`（Release 链接和 SHA256 见 [artifact/README.md](artifact/README.md)）；
- 已打补丁：默认 60 局、attempts 上限、汇总提示；
- 待做：300 层 goal、策略缓存、按优先级选策略；
- 已归档但**不是当前路线**：Python 版工具，放在 `reference/python-spa-farm/` 仅供参考。

## 目录

```
HANDOFF.md              交接说明（建议先看）
docs/
  CONVERSATION.md       对话全文（token 已脱敏）
  RUNBOOK.md            3/60 最优设置、分阶段刷取
  BUILD-WINDOWS.md      Windows 本地构建步骤
  CODE-OPTIMIZATION.md  补丁说明与 300 层缺口
  REVIEW-fork.md        对 Dr-hydra 实现的代码审查
  STRATEGY.md           B 站/NGA 攻略与 build 整理
patches/
  spa-optimize.patch    可直接 git apply 的补丁
  SPAFarmTaskPlugin.cpp 改好的完整 C++ 文件
  MiniGame.cs           改好的完整 C# 文件
build/
  build-spa.ps1         一键构建脚本（默认只编 MaaCore）
  spa-headless.ps1      headless 启动任务（调 MaaCore.dll，不点 GUI）
artifact/
  README.md             构建产物信息（二进制不进 git）
reference/
  python-spa-farm/      Python 原型（已弃用，仅参考）
```

## 安全

对话里出现过的 GitHub token 已在 `CONVERSATION.md` 中替换为 `github_pat_REDACTED`。
如果你之前创建过带 `Administration` 权限的 token，请去 GitHub 删除。

## 远端

当前可直接访问（作为 MAA fork 的独立分支，不影响 dev-v2/release）：

- https://github.com/Liamnnn/MaaAssistantArknights/tree/context/spa-optimization
- Windows 上克隆：

```powershell
git clone --depth 1 -b context/spa-optimization https://github.com/Liamnnn/MaaAssistantArknights.git spa-context
cd spa-context
# 先读 HANDOFF.md，再按 docs/BUILD-WINDOWS.md 构建
```

另有一个空的 private 仓库 `Liamnnn/spa-farm-context` 预留；把该仓库加进 token 的
Repository access 后，可以把它作为正式仓库推送过去（不影响使用）。
