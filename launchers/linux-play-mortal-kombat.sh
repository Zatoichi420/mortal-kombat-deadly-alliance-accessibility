#!/usr/bin/env bash
# Launcher: start MK: Deadly Alliance in RetroArch (Linux).
# Edit the paths, `chmod +x`, and drop a .desktop file in ~/.local/share/applications
# (or just run it). Works with a Flatpak RetroArch too — see RETROARCH below.
set -u

# ---- EDIT THESE --------------------------------------------------------
RETROARCH="retroarch"                       # or: flatpak run org.libretro.RetroArch
CORE="$HOME/.config/retroarch/cores/dolphin_libretro.so"
ROM="$HOME/Games/GameCube/Mortal Kombat - Deadly Alliance (USA).rvz"
# --------------------------------------------------------------------

say() { command -v spd-say >/dev/null && spd-say -w "$1" || { command -v espeak-ng >/dev/null && espeak-ng "$1"; }; }

for f in "$CORE" "$ROM"; do
    [ -e "$f" ] || { say "Cannot start Mortal Kombat, a file was not found"; echo "not found: $f" >&2; exit 1; }
done

systemctl --user start mkda-menu-reader.service 2>/dev/null || true
pkill -x retroarch 2>/dev/null || true
sleep 1
$RETROARCH -L "$CORE" "$ROM" &
sleep 3
say "Mortal Kombat loading. Press Start to reach the main menu."
