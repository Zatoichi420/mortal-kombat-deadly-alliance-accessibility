#!/usr/bin/env bash
# Install the MK:DA talking-menu daemon as a systemd --user service (Linux).
# `./install.sh uninstall` to remove.
set -euo pipefail

NAME="mkda-menu-reader"
SRC_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mkda-talking-menu"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ "${1:-}" = "uninstall" ]; then
    systemctl --user disable --now "$NAME.service" 2>/dev/null || true
    rm -f "$UNIT_DIR/$NAME.service"
    rm -rf "$INSTALL_DIR"
    systemctl --user daemon-reload || true
    echo "uninstalled."
    exit 0
fi

# 1. a TTS backend
if ! command -v spd-say >/dev/null && ! command -v espeak-ng >/dev/null && ! command -v espeak >/dev/null; then
    echo "WARNING: no TTS found. Install one, e.g.:"
    echo "  Debian/Ubuntu:  sudo apt install speech-dispatcher espeak-ng"
    echo "  Fedora:         sudo dnf install speech-dispatcher espeak-ng"
    echo "  Arch:           sudo pacman -S speech-dispatcher espeak-ng"
fi

# 2. RetroArch network command interface
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/retroarch/retroarch.cfg"
if [ -f "$CFG" ] && grep -q '^network_cmd_enable = "false"' "$CFG"; then
    echo "Quit RetroArch, then press Return to set network_cmd_enable = true ..."
    read -r _
    sed -i 's/^network_cmd_enable = "false"/network_cmd_enable = "true"/' "$CFG"
    echo "  done"
elif [ ! -f "$CFG" ]; then
    echo "NOTE: set 'network_cmd_enable = true' in RetroArch (Settings > Network > Network Commands)."
fi

# 3. install files + unit
mkdir -p "$INSTALL_DIR" "$UNIT_DIR"
cp "$SRC_DIR"/menu_reader.py "$SRC_DIR"/ra_client.py "$SRC_DIR"/mkda_addrs.py "$SRC_DIR"/speak.py "$INSTALL_DIR/"
sed "s|__INSTALL_DIR__|$INSTALL_DIR|g" "$SRC_DIR/install/linux/$NAME.service" > "$UNIT_DIR/$NAME.service"

systemctl --user daemon-reload
systemctl --user enable --now "$NAME.service"
sleep 1
systemctl --user --no-pager status "$NAME.service" | head -6 || true

echo
echo "Installed. Start MK: Deadly Alliance in RetroArch to hear the menus."
echo "  log:  journalctl --user -u $NAME -f"
echo "  test: python3 \"$INSTALL_DIR/menu_reader.py\" --probe"
