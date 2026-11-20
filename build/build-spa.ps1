<#
.SYNOPSIS
  在 Windows 上构建 Dr-hydra 版 MAA（默认只编 MaaCore）。
.EXAMPLE
  .\build-spa.ps1 -InstallDir "D:\MAA-spa"
  .\build-spa.ps1 -Full -Version v6.22.0-spa.1
#>
param(
    [string]$Repo = ".",
    [string]$InstallDir = "",
    [string]$Version = "v6.22.0-spa.1",
    [string]$VersionNum = "6.22.0",
    [switch]$Full,
    [switch]$Clean,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Set-Location -LiteralPath $Repo

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "缺少 $cmd。$hint"
    }
}

Need git "安装 Git for Windows"
Need cmake "安装 CMake 或使用 Developer PowerShell for VS 2022"
Need dotnet "安装 .NET SDK 10.0.302"
if (-not $SkipDeps) { Need python "安装 Python 3.11/3.12" }

Write-Host "== 子模块 ==" -ForegroundColor Cyan
git submodule update --init --depth 1 src/MaaUtils 3rdparty/EmulatorExtras

if (-not $SkipDeps -and -not (Test-Path "src/MaaUtils/MaaDeps")) {
    Write-Host "== 下载 MaaDeps（首次较慢）==" -ForegroundColor Cyan
    python tools/maadeps-download.py x64-windows
}

if (-not (Test-Path "global.json")) {
    '{"sdk":{"version":"10.0.302","rollForward":"disable"}}' | Set-Content -Encoding utf8 global.json
}

if ($Clean) {
    Remove-Item -Recurse -Force build, install -ErrorAction SilentlyContinue
}

Write-Host "== CMake 配置 ==" -ForegroundColor Cyan
if (-not (Test-Path "build/CMakeCache.txt")) {
    cmake -B build --preset windows-publish-x64 `
        -DMAA_HASH_VERSION=$Version `
        -DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=Embedded
}

Write-Host "== 编译 MaaCore ==" -ForegroundColor Cyan
cmake --build build --config RelWithDebInfo --target MaaCore --parallel

if ($Full) {
    Write-Host "== 编译 apphost / updater ==" -ForegroundColor Cyan
    cmake --build build --config RelWithDebInfo --target MaaAppHostStub MAA.Updater --parallel

    Write-Host "== 发布 WPF GUI ==" -ForegroundColor Cyan
    dotnet publish src/MaaWpfGui/MaaWpfGui.csproj -c Release -p:Platform=x64 `
        -p:Version=$VersionNum -p:FileVersion=$VersionNum -p:AssemblyVersion=$VersionNum `
        -p:InformationalVersion=$Version -o install

    Write-Host "== 安装资源 ==" -ForegroundColor Cyan
    cmake --install build --config RelWithDebInfo
    Copy-Item build\bin\RelWithDebInfo\MaaAppHostStub.exe install\MAA.exe -Force
    Get-ChildItem install -Filter *.pdb -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path .\install\* -DestinationPath "MAA-$Version-win-x64.zip" -Force
    Write-Host "包：MAA-$Version-win-x64.zip" -ForegroundColor Green
}
elseif ($InstallDir) {
    $dll = "build\bin\RelWithDebInfo\MaaCore.dll"
    if (-not (Test-Path $dll)) { throw "找不到 $dll" }
    Copy-Item $dll (Join-Path $InstallDir "MaaCore.dll") -Force
    Write-Host "已替换：$InstallDir\MaaCore.dll" -ForegroundColor Green
}
else {
    Write-Host "MaaCore.dll：build\bin\RelWithDebInfo\MaaCore.dll" -ForegroundColor Green
}

$sw.Stop()
Write-Host ("用时 {0:N1} 分钟" -f $sw.Elapsed.TotalMinutes) -ForegroundColor Green
