-- Launcher: start MK: Deadly Alliance in RetroArch (macOS), with the talking-menu daemon.
--
-- Build it into a double-clickable app:
--   osacompile -o "$HOME/Desktop/Play Mortal Kombat.app" launchers/macos-launcher.applescript
-- Then activate it with VoiceOver (VO-Space). First run: macOS asks permission — choose Open.

-- ---- EDIT THIS PATH -------------------------------------------------------
set romPath to "/Volumes/GameLibrary/OpenEmu/Game Library/roms/GameCube/Mortal Kombat - Deadly Alliance (USA) (Rev 1).nkit.iso"
-- ----------------------------------------------------------------------

set corePath to (POSIX path of (path to home folder)) & "Library/Application Support/RetroArch/cores/dolphin_libretro.dylib"

try
	do shell script "test -f " & quoted form of romPath
on error
	do shell script "say 'The game disc file was not found. The drive may not be connected.'"
	display alert "Can't start Mortal Kombat" message "Game disc file not found." as critical
	return
end try
try
	do shell script "test -f " & quoted form of corePath
on error
	do shell script "say 'The Dolphin core is missing from RetroArch.'"
	display alert "Can't start Mortal Kombat" message "Dolphin GameCube core not found in RetroArch." as critical
	return
end try

do shell script "launchctl kickstart gui/$(id -u)/com.orlando.mkda-menu-reader 2>/dev/null; true"
do shell script "killall RetroArch 2>/dev/null; true"
delay 1
do shell script "open -a RetroArch --args -L " & quoted form of corePath & " " & quoted form of romPath
delay 4
do shell script "open -a RetroArch"
do shell script "say 'Mortal Kombat loading. Press Start to reach the main menu.'"
