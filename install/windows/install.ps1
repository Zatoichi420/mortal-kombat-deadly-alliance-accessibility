<#
Install the MK:DA talking-menu daemon on Windows as a hidden auto-start task.

    powershell -ExecutionPolicy Bypass -File install\windows\install.ps1
    powershell -ExecutionPolicy Bypass -File install\windows\install.ps1 -Uninstall

Speech uses Windows' built-in System.Speech (SAPI) via PowerShell — no extra
install. Requires Python 3 on PATH.
#>
param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$TaskName   = "mkda-menu-reader"
$RepoRoot   = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$InstallDir = Join-Path $env:LOCALAPPDATA "mkda-talking-menu"
$Log        = Join-Path $InstallDir "menu_reader.log"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    Write-Host "uninstalled."
    return
}

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { throw "Python 3 not found on PATH. Install from https://python.org and re-run." }

# 1. enable RetroArch's network command interface
$cfg = Join-Path $env:APPDATA "RetroArch\retroarch.cfg"
if (Test-Path $cfg) {
    $c = Get-Content $cfg -Raw
    if ($c -match 'network_cmd_enable = "false"' -or $c -match 'network_remote_enable(_user_p1)? = "true"') {
        Read-Host "Quit RetroArch, then press Enter to fix its network settings"
        $c = $c -replace 'network_cmd_enable = "false"', 'network_cmd_enable = "true"'
        $c = $c -replace 'network_remote_enable = "true"', 'network_remote_enable = "false"'
        $c = $c -replace 'network_remote_enable_user_p1 = "true"', 'network_remote_enable_user_p1 = "false"'
        $c | Set-Content $cfg -NoNewline
        Write-Host "  network_cmd_enable = true ; network_remote_enable = false"
    }
} else {
    Write-Host "NOTE: enable RetroArch > Settings > Network > Network Commands."
}

# 2. copy daemon
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item (Join-Path $RepoRoot "menu_reader.py"),(Join-Path $RepoRoot "ra_client.py"),`
          (Join-Path $RepoRoot "mkda_addrs.py"),(Join-Path $RepoRoot "speak.py") $InstallDir -Force

# 3. scheduled task: run at logon, hidden, keep alive
$runner = Join-Path $InstallDir "run.vbs"
@"
' launches the daemon with no console window
Dim sh: Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c """"$py"" ""$InstallDir\menu_reader.py"" >> ""$Log"" 2>&1""", 0, False
"@ | Set-Content $runner -Encoding ASCII

$action  = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$runner`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "MK: Deadly Alliance talking-menu daemon" -Force | Out-Null

# optional: A/B remap so the bottom face button confirms in menus
$RemapDst = Join-Path $env:APPDATA "RetroArch\config\remaps\dolphin-emu\dolphin-emu.rmp"
if (-not (Test-Path $RemapDst)) {
    $a = Read-Host "Install a remap so the BOTTOM face button confirms in GameCube menus (default is the right button; also swaps two attack buttons in a match)? [y/N]"
    if ($a -eq "y" -or $a -eq "Y") {
        New-Item -ItemType Directory -Force -Path (Split-Path $RemapDst) | Out-Null
        Copy-Item (Join-Path $RepoRoot "extras\dolphin-emu.rmp") $RemapDst -Force
        Write-Host "  installed $RemapDst (delete to undo)"
    }
}

Start-ScheduledTask -TaskName $TaskName

Write-Host ""
Write-Host "Installed. Start MK: Deadly Alliance in RetroArch to hear the menus."
Write-Host "  log:  Get-Content `"$Log`" -Wait"
Write-Host "  test: python `"$InstallDir\menu_reader.py`" --probe"
