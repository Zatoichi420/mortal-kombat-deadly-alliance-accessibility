#!/bin/bash
# Install the MK:DA talking-menu daemon as a per-user launchd agent (macOS).
# Re-run any time to update. `./install.sh uninstall` to remove.
set -euo pipefail

LABEL="com.orlando.mkda-menu-reader"
SRC_DIR="$(cd "$(dirname "$0")/../.." && pwd)"          # repo root
INSTALL_DIR="$HOME/Library/Application Support/mkda-talking-menu"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/mkda-menu-reader.log"
PYTHON="$(command -v python3 || echo /usr/bin/python3)"
UID_NUM="$(id -u)"

if [ "${1:-}" = "uninstall" ]; then
    launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
    rm -f "$PLIST_DST"
    rm -rf "$INSTALL_DIR"
    echo "uninstalled."
    exit 0
fi

# 1. RetroArch network config: the daemon needs the command interface (55355) ON
#    and must NOT need the network gamepad (55400) — leaving that on is an input
#    hazard (a stuck injected button breaks menu selection).
CFG="$HOME/Library/Application Support/RetroArch/config/retroarch.cfg"
if [ -f "$CFG" ]; then
    need_cmd=$(grep -q '^network_cmd_enable = "false"' "$CFG" && echo 1 || echo 0)
    has_remote=$(grep -qE '^network_remote_enable(_user_p1)? = "true"' "$CFG" && echo 1 || echo 0)
    if [ "$need_cmd" = 1 ] || [ "$has_remote" = 1 ]; then
        echo "Quit RetroArch, then press Return to fix its network settings..."
        read -r _
        sed -i '' 's/^network_cmd_enable = "false"/network_cmd_enable = "true"/' "$CFG"
        sed -i '' 's/^network_remote_enable = "true"/network_remote_enable = "false"/' "$CFG"
        sed -i '' 's/^network_remote_enable_user_p1 = "true"/network_remote_enable_user_p1 = "false"/' "$CFG"
        echo "  network_cmd_enable = true ; network_remote_enable = false"
    fi
else
    echo "WARNING: retroarch.cfg not found. In RetroArch set Settings > Network >"
    echo "  Network Commands = ON, and Network Remote = OFF."
fi

# 2. copy the daemon somewhere launchd is allowed to read (NOT ~/Desktop / iCloud)
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/menu_reader.py" "$SRC_DIR/ra_client.py" "$SRC_DIR/mkda_addrs.py" "$SRC_DIR/speak.py" "$INSTALL_DIR/"

# 3. write the launch agent
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__LOG__|$LOG|g" \
    "$SRC_DIR/install/macos/$LABEL.plist" > "$PLIST_DST"

# 4. keep RetroArch awake in the background so its command port stays responsive
defaults write org.libretro.RetroArch NSAppSleepDisabled -bool YES || true

# 5. (re)load
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"
sleep 1
launchctl print "gui/$UID_NUM/$LABEL" | grep -E 'state = |pid = ' || true

echo
echo "Installed. Start MK: Deadly Alliance in RetroArch and you should hear the menus."
echo "  log:  tail -f \"$LOG\""
echo "  test: python3 \"$INSTALL_DIR/menu_reader.py\" --probe"
