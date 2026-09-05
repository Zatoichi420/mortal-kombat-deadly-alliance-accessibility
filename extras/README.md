# extras/

## `dolphin-emu.rmp` — make the bottom face button confirm

Optional. RetroArch's Dolphin core maps the **GameCube A button** (the one MK:DA
menus use to *confirm*) to **RetroPad A**, which on an Xbox / PlayStation pad is
the **right** face button (B / Circle), not the bottom one. So pressing the
natural "confirm" button (Xbox A / PS Cross) sends GameCube **B** = *Back*, which
on the main menu drops you to the attract loop and replays the intro.

This is a core remap that swaps RetroPad A and B, so the **bottom** face button
(Xbox A / PS Cross) confirms and the right one goes back — the layout most people
expect, and what standalone Dolphin does by default.

**Trade-off:** in a match, GameCube A/B are two of the four attack buttons, so
those two swap too (bottom button = GC A attack). X and Y are untouched. Most
players prefer it this way; if you don't, delete the file.

### Install

Copy it to RetroArch's core-remap folder (create the folder if needed):

- **macOS:** `~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/dolphin-emu.rmp`
- **Linux:** `~/.config/retroarch/config/remaps/dolphin-emu/dolphin-emu.rmp`
- **Windows:** `%APPDATA%\RetroArch\config\remaps\dolphin-emu\dolphin-emu.rmp`

Restart the game. The `install` scripts offer to do this for you.

### Make it MK:DA-only instead of all GameCube/Wii games

Put the same contents in a **game** remap next to it, named after your ROM file
with `.rmp` instead of its extension, e.g.
`remaps/dolphin-emu/Mortal Kombat - Deadly Alliance (USA) (Rev 1).nkit.rmp`,
and delete `dolphin-emu.rmp`. A game remap overrides the core one.
