<#
Double-click launcher: start MK: Deadly Alliance in RetroArch (Windows).
Edit the two paths below, then make a shortcut to this file (right-click >
Send to > Desktop). To run without a console window, point the shortcut at:
    powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File "<path>\windows-Play-MortalKombat.ps1"
#>

# ---- EDIT THESE ----------------------------------------------------------
$RetroArch = "C:\RetroArch-Win64\retroarch.exe"
$Core      = "C:\RetroArch-Win64\cores\dolphin_libretro.dll"
$Rom       = "D:\Games\GameCube\Mortal Kombat - Deadly Alliance (USA).rvz"
# ------------------------------------------------------------------------

foreach ($p in @($RetroArch, $Core, $Rom)) {
    if (-not (Test-Path $p)) {
        Add-Type -AssemblyName System.Speech
        (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("Cannot start Mortal Kombat. A file was not found.")
        [System.Windows.Forms.MessageBox]::Show("Not found:`n$p") 2>$null
        exit 1
    }
}

Start-ScheduledTask -TaskName "mkda-menu-reader" -ErrorAction SilentlyContinue
Get-Process retroarch -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Start-Process $RetroArch -ArgumentList "-L `"$Core`" `"$Rom`""
Start-Sleep -Seconds 3
Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("Mortal Kombat loading. Press Start to reach the main menu.")
