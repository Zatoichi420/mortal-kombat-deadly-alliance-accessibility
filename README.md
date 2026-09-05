# Mortal Kombat: Deadly Alliance — talking menus (screen-reader accessibility)

A small tool that makes the **GameCube** version of *Mortal Kombat: Deadly
Alliance* usable without sight. When the game runs in RetroArch's Dolphin core,
it speaks the menu item you're on ("Arcade, 1 of 8", "Versus, 2 of 8", …), the
Options and Kontent sub-menus, the pause menu, and the fighter you're hovering on
the character-select screen.

It reads the game's memory over RetroArch's network command interface and speaks
through the OS's own text-to-speech. **It never modifies or writes to the game.**

Works on **Windows, macOS and Linux** — the reverse-engineered addresses are
GameCube addresses and are the same on every host; only the text-to-speech and
the "start on login" glue differ per OS. See [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

## Requirements

- **RetroArch** with the **Dolphin** core (`dolphin_libretro`).
- *Mortal Kombat: Deadly Alliance*, **USA release** (disc id `GMKE5D`) — your own
  legally-obtained copy. Any dump format (ISO / RVZ / NKit) is fine.
  Other regions work after a short retarget — see [docs/CALIBRATION.md](docs/CALIBRATION.md).
- **Python 3.8+**.
- A TTS backend:
  - macOS — built in (`say`).
  - Windows — built in (SAPI via PowerShell).
  - Linux — `speech-dispatcher` + `espeak-ng` (`sudo apt install speech-dispatcher espeak-ng`, or your distro's equivalent).

## Setup

### 1. Turn on RetroArch's network commands (once)

RetroArch → **Settings → Network → Network Commands → ON**, or set in
`retroarch.cfg`:

```
network_cmd_enable = "true"
```

(The installers below will offer to do this for you.)

### 2. Install the daemon

Clone the repo, then:

**macOS**
```bash
install/macos/install.sh
```
Installs a launchd agent. Also copies the daemon out of `~/Desktop`/iCloud (which
sandboxed background processes can't read) into `~/Library/Application Support/`.

**Linux**
```bash
install/linux/install.sh
```
Installs a `systemd --user` service.

**Windows** (PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File install\windows\install.ps1
```
Registers a hidden auto-start Scheduled Task.

Each installer has an `uninstall` argument.

### 3. Play

Start MK: Deadly Alliance in RetroArch however you normally do. The daemon waits
quietly until it sees the game running, then narrates. Press Start past the logos
to reach the main menu and you should hear the items as you move.

Optional double-click launchers that start RetroArch with the game are in
[`launchers/`](launchers/) — edit the paths at the top of the one for your OS.

## Running it by hand / debugging

```bash
python menu_reader.py              # foreground
python menu_reader.py --probe      # live raw state, no speech
python menu_reader.py --once       # one snapshot, then exit
python menu_reader.py --descriptions   # speak the long mode blurbs
```

Environment variables: `MKDA_RA_HOST` (default `127.0.0.1`), `MKDA_RA_PORT`
(`55355`), `MKDA_VOICE`, `MKDA_RATE_WPM`, `MKDA_SPEAK_BACKEND`
(`say`/`spd-say`/`espeak`/`powershell`/`log`/`auto`).

Logs: `~/Library/Logs/mkda-menu-reader.log` (macOS) ·
`journalctl --user -u mkda-menu-reader` (Linux) ·
`%LOCALAPPDATA%\mkda-talking-menu\menu_reader.log` (Windows).

## Status

- **Working & verified live:** main menu, Options, Kontent, and pause-menu
  narration with list position ("N of M").
- **Needs a 60-second confirm on first play:** the character-select fighter
  names — see [docs/CALIBRATION.md](docs/CALIBRATION.md).
- **Not yet covered** (falls through to RetroArch's own OCR key): in-match text,
  the Krypt, the profile name-entry keyboard, Practice sub-screens.

## Retargeting / other regions

Everything you need is in [docs/CALIBRATION.md](docs/CALIBRATION.md) and
[docs/research/](docs/research/). The game ships an **unstripped** copy of its own
executable (`mk5gc_release.elf`), so retargeting is reading a symbol table, not
guessing — `tools/` has the extractor and disassembler.

## Legal

This repository contains **no game code, assets, or data**. It is an independent
interoperability / accessibility tool: it reads values out of memory at runtime
and says them out loud. You supply your own copy of the game.

*Mortal Kombat* and related marks are trademarks of Warner Bros. Entertainment
Inc. This project is not affiliated with or endorsed by Warner Bros. or
NetherRealm Studios. See [LICENSE](LICENSE) (MIT).
