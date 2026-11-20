<#
.SYNOPSIS
  不打开 MAA GUI，直接通过 MaaCore.dll 启动一局/多局卫戍协议任务。
.EXAMPLE
  .\spa-headless.ps1 -MaaDir "D:\MAA-spa" -Adb "D:\MAA-spa\adb\adb.exe" -Address "127.0.0.1:16384" -Goal task-1 -Mode standard -Runs 1
.EXAMPLE
  .\spa-headless.ps1 -MaaDir "D:\MAA-spa" -Adb "D:\MAA-spa\adb\adb.exe" -Address "127.0.0.1:16384" -Goal task-6 -Mode standard -Runs 1
#>
param(
    [Parameter(Mandatory = $true)][string]$MaaDir,
    [Parameter(Mandatory = $true)][string]$Adb,
    [Parameter(Mandatory = $true)][string]$Address,
    [string]$Config = "General",
    [string]$Goal = "medal",
    [ValidateSet("quick", "standard")][string]$Mode = "quick",
    [int]$Runs = 1,
    [int]$TargetClears = 3,
    [switch]$LowProfile,
    [int]$TimeoutMinutes = 0,
    [int]$PollSeconds = 5
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$logFile = Join-Path $here "spa-headless.log"
$shotDir = Join-Path $here "screenshots"
New-Item -ItemType Directory -Force -Path $shotDir | Out-Null

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

if (-not (Test-Path (Join-Path $MaaDir "MaaCore.dll"))) { throw "MaaCore.dll not found under $MaaDir" }
if (-not (Test-Path (Join-Path $MaaDir "resource"))) { throw "resource not found under $MaaDir" }
if (-not (Test-Path $Adb)) { throw "adb not found: $Adb" }

$env:PATH = "$MaaDir;$env:PATH"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class MaaCoreApi
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool SetDllDirectory(string path);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstSetUserDir(string path);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstLoadResource(string path);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern IntPtr AsstCreate();

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void AsstDestroy(IntPtr handle);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstConnect(IntPtr handle, string adbPath, string address, string config);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern int AsstAppendTask(IntPtr handle, string type, string paramsJson);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstStart(IntPtr handle);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstStop(IntPtr handle);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstRunning(IntPtr handle);

    [DllImport("MaaCore.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern byte AsstConnected(IntPtr handle);
}
"@

[MaaCoreApi]::SetDllDirectory($MaaDir) | Out-Null
Write-Log "MaaDir=$MaaDir"
Write-Log ("SetUserDir=" + [MaaCoreApi]::AsstSetUserDir($MaaDir))
Write-Log ("LoadResource=" + [MaaCoreApi]::AsstLoadResource((Join-Path $MaaDir "resource")))

$handle = [MaaCoreApi]::AsstCreate()
if ($handle -eq [IntPtr]::Zero) { throw "AsstCreate failed" }
Write-Log "handle=$handle"

try {
    Write-Log "connecting $Address (config=$Config) ..."
    $ok = [MaaCoreApi]::AsstConnect($handle, $Adb, $Address, $Config)
    Write-Log ("AsstConnect=" + $ok)
    if ($ok -eq 0) { throw "connect failed; check adb/address/config" }
    Write-Log ("AsstConnected=" + [MaaCoreApi]::AsstConnected($handle))

    $task = @{
        task_names = @("MiniGame@SPA@BadgeFarm")
        params = @{
            spa_farm = @{
                low_profile = [bool]$LowProfile
                target_clears = $TargetClears
                max_runs = $Runs
                goal = $Goal
                mode = $Mode
            }
        }
    } | ConvertTo-Json -Compress -Depth 6
    Write-Log "task=$task"

    $taskId = [MaaCoreApi]::AsstAppendTask($handle, "MiniGame", $task)
    Write-Log "taskId=$taskId"
    if ($taskId -eq 0) { throw "AsstAppendTask failed" }

    $started = [MaaCoreApi]::AsstStart($handle)
    Write-Log "AsstStart=$started"
    if ($started -eq 0) { throw "AsstStart failed" }

    $logPath = Join-Path $MaaDir "debug\maa.log"
    if (-not (Test-Path $logPath)) { $logPath = Join-Path $MaaDir "debug\gui.log" }
    Write-Log "watching $logPath"

    $startedAt = Get-Date
    $seen = @{}
    while (([MaaCoreApi]::AsstRunning($handle)) -ne 0) {
        Start-Sleep -Seconds $PollSeconds
        $elapsed = ((Get-Date) - $startedAt).TotalMinutes
        if ($TimeoutMinutes -gt 0 -and $elapsed -ge $TimeoutMinutes) {
            Write-Log "timeout after $TimeoutMinutes min, stopping"
            [MaaCoreApi]::AsstStop($handle) | Out-Null
            try {
                Add-Type -AssemblyName System.Windows.Forms, System.Drawing
                $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
                $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
                $g = [System.Drawing.Graphics]::FromImage($bmp)
                $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
                $shot = Join-Path $shotDir ("headless-timeout-{0}.png" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
                $bmp.Save($shot, [System.Drawing.Imaging.ImageFormat]::Png)
                Write-Log "screenshot=$shot"
            } catch { Write-Log ("screenshot failed: " + $_.Exception.Message) }
            break
        }
        if (Test-Path $logPath) {
            $lines = Get-Content -Path $logPath -Tail 40 -ErrorAction SilentlyContinue
            foreach ($line in $lines) {
                if ($line -match "【对局结算】|【刻章达成】|【任务完成情况汇总】|【刻章】") {
                    if (-not $seen.ContainsKey($line)) {
                        $seen[$line] = 1
                        Write-Log ("MATCH " + $line)
                    }
                }
            }
        }
        Write-Log ("running ... {0:N1} min" -f $elapsed)
    }

    Write-Log "task finished (AsstRunning=0)"
}
finally {
    [MaaCoreApi]::AsstStop($handle) | Out-Null
    [MaaCoreApi]::AsstDestroy($handle)
    Write-Log "destroyed"
}
