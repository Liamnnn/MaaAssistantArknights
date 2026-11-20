# Headless 启动（不打开 MAA GUI）

`build/spa-headless.ps1` 直接调 `MaaCore.dll`，适合让 agent 启动/监控，不依赖 GUI 点击。

## 前置

- Windows 10/11 x64；
- 已解压优化版 MAA（例如 `D:\MAA-spa`），目录下有 `MaaCore.dll`、`resource\`、`adb\adb.exe`；
- MuMu 已启动，MAA 能正常连接（记下连接地址，例如 `127.0.0.1:16384`）；
- 游戏 1920×1080、默认主题、关闭按键提示、停在卫戍协议主界面或对局内。

## 用法

```powershell
# 普通刷角标（从主界面全自动）
.\spa-headless.ps1 -MaaDir "D:\MAA-spa" `
  -Adb "D:\MAA-spa\adb\adb.exe" -Address "127.0.0.1:16384" `
  -Goal medal -Mode quick -Runs 60

# 等级 12：先手动进对局，再启动，只打 1 局
.\spa-headless.ps1 -MaaDir "D:\MAA-spa" `
  -Adb "D:\MAA-spa\adb\adb.exe" -Address "127.0.0.1:16384" `
  -Goal task-1 -Mode standard -Runs 1 -TimeoutMinutes 40

# 300 层：手动进标准模拟对局，task-6 经济流
.\spa-headless.ps1 -MaaDir "D:\MAA-spa" `
  -Adb "D:\MAA-spa\adb\adb.exe" -Address "127.0.0.1:16384" `
  -Goal task-6 -Mode standard -Runs 1 -TimeoutMinutes 40
```

## 参数

| 参数 | 说明 |
| --- | --- |
| `-MaaDir` | MAA 安装目录（含 `MaaCore.dll`、`resource`） |
| `-Adb` | `adb.exe` 路径 |
| `-Address` | 模拟器 adb 地址（MAA 连接设置里的地址） |
| `-Config` | 连接配置，默认 `General`；MuMu 可试 `MuMuEmulator12` |
| `-Goal` | `medal` / `task-1`..`task-7` |
| `-Mode` | `quick`（极速）/ `standard`（标准/独立） |
| `-Runs` | 最大通关局数（等级12/300 填 1） |
| `-TargetClears` | 每策略通关次数，默认 3 |
| `-LowProfile` | 低配编队开关 |
| `-TimeoutMinutes` | 超时自动停并截图，0=不限制 |
| `-PollSeconds` | 轮询间隔，默认 5 秒 |

## 输出

- 控制台 + `build/spa-headless.log`；
- 超时截图在 `build/screenshots/`；
- 关键日志行（`【对局结算】`、`【刻章达成】`、`【任务完成情况汇总】`）会实时打到控制台。

## 常见错误

| 现象 | 处理 |
| --- | --- |
| `MaaCore.dll not found` | `-MaaDir` 指到解压目录 |
| `LoadResource=0` | `resource` 目录不完整，重新解压 |
| `connect failed` | 换 `-Config MuMuEmulator12`，或检查 adb 地址/MuMu 是否启动 |
| `taskId=0` | 任务参数没被识别；确认是优化版构建（含 `MiniGame@SPA@BadgeFarm`） |
| 一直 `running` 不动 | 看日志最后几行；超时截图；确认游戏停在对局内/主界面 |
| PowerShell 禁止运行脚本 | `Set-ExecutionPolicy -Scope Process Bypass` |

## 注意

- 等级 12 / 300 层仍然建议**先手动进对局**，再启动 `-Runs 1`；headless 不会帮你选难度。
- 普通 60 胜可以从主界面全自动，但插件默认会选“规程等级1”只在标准模式下；极速模式不受影响。
- 这个脚本只启动任务，不做 OCR 判断；进度看日志。
