# 在 Windows 上本地构建（比 GitHub Actions 快）

## 结论

可以。第一次装环境约 30~60 分钟，之后：

| 改了什么 | 需要做的 | 时间 |
| --- | --- | --- |
| 只改 `SPAFarmTaskPlugin.cpp` | 编 `MaaCore`，替换安装目录里的 `MaaCore.dll` | 约 1~3 分钟 |
| 改 WPF 界面/`MiniGame.cs` | 编 `MaaCore` + `dotnet publish`，重新打包 | 约 5~10 分钟 |
| 只改资源 `resource/**` | **不用编译**，直接覆盖安装目录的 `resource` | 几秒 |

GitHub Actions 慢是因为每次都是冷启动：重新下 MaaDeps、全量编 MaaCore、NuGet 还原、打包 295MB。
本地增量编译只重编改动文件。

## 一次性环境

1. **Visual Studio 2022**（17.10+），安装时勾选：
   - “使用 C++ 的桌面开发”（MSVC x64、Windows SDK）
   - “.NET 桌面开发”
2. **CMake** 3.25+（VS 自带也可，装独立版更稳）
3. **Git for Windows**
4. **Python 3.11/3.12**（只用于下载 MaaDeps）
5. **.NET SDK 10.0.302**（仓库 pin 的版本；`dotnet --list-sdks` 能看到）
6. 磁盘预留 20~30GB

## 首次构建

在 **“Developer PowerShell for VS 2022”** 里：

```powershell
git clone -b pr/spa-badge-farm https://github.com/Dr-hydra/MaaAssistantArknights
cd MaaAssistantArknights
git submodule update --init --depth 1 src/MaaUtils 3rdparty/EmulatorExtras
python tools/maadeps-download.py x64-windows

# 仓库要求 .NET 10.0.302，没有 global.json 就建一个
'{"sdk":{"version":"10.0.302","rollForward":"disable"}}' | Set-Content global.json

cmake -B build --preset windows-publish-x64 `
  -DMAA_HASH_VERSION=v6.22.0-spa.1 `
  -DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=Embedded

cmake --build build --config RelWithDebInfo --target MaaCore --parallel
```

只想先验证 C++ 改动：到这里就够了，产物是
`build\bin\RelWithDebInfo\MaaCore.dll`。

## 只改插件 C++（最快路径）

```powershell
cmake --build build --config RelWithDebInfo --target MaaCore --parallel
Copy-Item build\bin\RelWithDebInfo\MaaCore.dll "D:\MAA-spa\MaaCore.dll" -Force
```

然后直接启动 `D:\MAA-spa\MAA.exe`。不需要重新打包，也不需要 GitHub。

## 出完整安装包

```powershell
cmake --build build --config RelWithDebInfo --target MaaAppHostStub MAA.Updater --parallel
dotnet publish src/MaaWpfGui/MaaWpfGui.csproj -c Release -p:Platform=x64 `
  -p:Version=6.22.0 -p:FileVersion=6.22.0 -p:AssemblyVersion=6.22.0 `
  -p:InformationalVersion=v6.22.0-spa.1 -o install
cmake --install build --config RelWithDebInfo
Copy-Item build\bin\RelWithDebInfo\MaaAppHostStub.exe install\MAA.exe -Force
Compress-Archive -Path .\install\* -DestinationPath MAA-v6.22.0-spa.1-win-x64.zip -Force
```

## 用脚本

把本目录的 `build-spa.ps1` 放到仓库根目录：

```powershell
# 只编 MaaCore，并替换到已安装目录
.\build-spa.ps1 -InstallDir "D:\MAA-spa"

# 全量打包
.\build-spa.ps1 -Full
```

脚本会自动检查工具、拉子模块、下 MaaDeps、配置（只做一次）、增量编译。

## 注意

- MaaDeps 下载走 GitHub API，可能限速；可以设 `MAA_DEPS_TOKEN` 环境变量放一个只读 token。
- 不要和 GitHub Actions 同时改同一个分支，容易冲突。
- 只换 `MaaCore.dll` 时，资源（`resource/SPAFarm`、模板）不会更新；改资源要手动覆盖。
- WPF 改了就必须重新 `dotnet publish`，只换 DLL 不生效。
- 杀毒软件把 `build\` 加白名单，能快不少。
