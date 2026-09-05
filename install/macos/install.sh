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

# 1. enable RetroArch's network command interface
CFG="$HOME/Library/Application Support/RetroArch/config/retroarch.cfg"
if [ -f "$CFG" ]; then
    if grep -q '^network_cmd_enable = "false"' "$CFG"; then
        echo "Quit RetroArch, then press Return to enable its network command interface..."
        read -r _
        sed -i '' 's/^network_cmd_enable = "false"/network_cmd_enable = "true"/' "$CFG"
        echo "  set network_cmd_enable = true"
    fi
else
    echo "WARNING: retroarch.cfg not found; make sure 'network_cmd_enable = true' is set"
    echo "  (RetroArch: Settings > Network > Network Commands)."
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
