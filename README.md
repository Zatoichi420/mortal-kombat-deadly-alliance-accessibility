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

## Setup — step by step

This assumes you **already have** RetroArch installed, the Dolphin core added, and
your MK: Deadly Alliance **USA** disc image, and that the game already boots and
plays in RetroArch. If not, do that first (RetroArch's Online Updater installs
the "Nintendo - GameCube / Wii (Dolphin)" core; load the disc image as content).

### 1. Turn on RetroArch's network command interface

The daemon talks to RetroArch over a local UDP port; it's off by default.

- In RetroArch: **Settings → Network → Network Commands → ON**
  (in the RGUI menu; the setting right below is the port, leave it at `55355`).
- Or edit `retroarch.cfg` while RetroArch is **closed** and set:
  ```
  network_cmd_enable = "true"
  ```
  `retroarch.cfg` lives at:
  `~/Library/Application Support/RetroArch/config/retroarch.cfg` (macOS) ·
  `~/.config/retroarch/retroarch.cfg` (Linux) ·
  `%APPDATA%\RetroArch\retroarch.cfg` (Windows).

The install script in step 3 will offer to flip this for you.

### 2. Check you have Python and a voice

- **Python 3.8+** on your PATH. Test in a terminal: `python --version` (or `python3 --version`).
  Windows: install from <https://python.org> and tick "Add to PATH".
- **Text-to-speech:**
  - macOS — nothing to do (`say` is built in).
  - Windows — nothing to do (uses the built-in SAPI voice via PowerShell).
  - Linux — install one: `sudo apt install speech-dispatcher espeak-ng`
    (or `dnf`/`pacman` equivalent). Test: `spd-say hello`.

### 3. Get the code and install the daemon

```bash
git clone https://github.com/Zatoichi420/mortal-kombat-deadly-alliance-accessibility
cd mortal-kombat-deadly-alliance-accessibility
```

Then run the installer for your OS. It copies the daemon to a stable location,
registers it to start automatically and stay running, and (if needed) offers to
set `network_cmd_enable`.

| OS | command |
|---|---|
| **macOS** | `install/macos/install.sh` |
| **Linux** | `install/linux/install.sh` |
| **Windows** | `powershell -ExecutionPolicy Bypass -File install\windows\install.ps1` |

Each installer takes an `uninstall` argument to undo everything.

> **Not ready to auto-install?** You can skip step 3 entirely and just run
> `python menu_reader.py` in a terminal whenever you play. The installer only
> automates "start it in the background at login".

### 4. Play

1. Start MK: Deadly Alliance in RetroArch (load the disc image as content, or use
   a playlist entry — however you normally launch it).
2. The daemon notices the game within a second or two. Nothing is spoken during
   the intro logos.
3. Press **Start** to get past the logos to the main menu. As you move up/down
   you'll hear **"Arcade, 1 of 8"**, **"Versus, 2 of 8"**, and so on. The Options
   and Kontent sub-menus and the pause menu work the same way.
4. In Arcade → character select, moving across the roster speaks the fighter names.
   (Please sanity-check this once — see [docs/CALIBRATION.md](docs/CALIBRATION.md) §1.)

### 5. Check it's working / troubleshoot

```bash
python menu_reader.py --once     # from the repo folder — should print a state line
```
- **"cannot reach RetroArch"** → the game isn't running, or step 1 (network
  commands) isn't done, or you edited `retroarch.cfg` while RetroArch was open
  (it rewrites the file on exit and undoes your change — close it first).
- **Silent on the menus** → check the daemon is running and see the log:
  - macOS: `tail -f ~/Library/Logs/mkda-menu-reader.log`
  - Linux: `journalctl --user -u mkda-menu-reader -f`
  - Windows: `Get-Content "$env:LOCALAPPDATA\mkda-talking-menu\menu_reader.log" -Wait`
- **macOS: RetroArch goes unresponsive when it's not the front window** → it's
  being "App Napped". Keep RetroArch focused while playing; the daemon retries and
  recovers on its own when you switch back.

### Optional: a one-click launcher

[`launchers/`](launchers/) has a start-the-game-with-one-action script per OS.
Open the one for your OS, edit the two paths at the top (RetroArch, your disc
image), and — on macOS — build it into an app:
`osacompile -o "$HOME/Desktop/Play Mortal Kombat.app" launchers/macos-launcher.applescript`.

## Running it by hand / debugging

```bash
python menu_reader.py              # foreground
python menu_reader.py --probe      # live raw state, no speech
python menu_reader.py --once       # one snapshot, then exit
python menu_reader.py --descriptions   # speak the long mode blurbs
```

Environment variables: `MK_RA_HOST` (default `127.0.0.1`), `MK_RA_PORT`
(`55355`), `MK_VOICE`, `MK_RATE_WPM`, `MK_SPEAK_BACKEND`
(`say`/`spd-say`/`espeak`/`powershell`/`log`/`auto`).

Logs: `~/Library/Logs/mkda-menu-reader.log` (macOS) ·
`journalctl --user -u mkda-menu-reader` (Linux) ·
`%LOCALAPPDATA%\mkda-talking-menu\menu_reader.log` (Windows).

## Status

- **Working & verified live:** main-menu / Options / Kontent / pause-menu
  narration with list position ("Arcade, 1 of 8"); ~75 ms keypress → speech.
- **Working, please confirm on first play:**
  - **Game Options** — reads each row and its current value
    ("Game Options. CPU Difficulty: Medium"). Sound / Controller Setup / Screen
    Adjust are not wired yet.
  - **Character select** — speaks the hovered fighter (`P1_POS` / `P2_POS`);
    the address wants a 60-second check, see [docs/CALIBRATION.md](docs/CALIBRATION.md).
  - **Match start** — announces the matchup once, left fighter first
    ("Shang Tsung versus Johnny Cage").
- **Not covered** (use RetroArch's OCR key): in-match HUD/text, the Krypt, the
  profile name-entry keyboard, Practice sub-screens.
- Latency + all bug fixes: [docs/AUDIT-menu-latency.md](docs/AUDIT-menu-latency.md),
  [docs/BUG-menu-selection.md](docs/BUG-menu-selection.md),
  [docs/BUG-confirm-button.md](docs/BUG-confirm-button.md).

### Confirm button

RetroArch's Dolphin core maps the GameCube **A** button (what MK:DA menus use to
*confirm*) to **RetroPad A** — the **right** face button on an Xbox/PlayStation pad
(B / Circle), **not** the bottom one. So pressing the natural confirm button
(Xbox A / PS Cross) sends GameCube **B** = *Back*, which on the main menu drops you
to the attract loop and replays the intro. **Press the right face button
(B / Circle), or Start, to confirm** — or install the optional remap in
[`extras/`](extras/) (the `install` scripts offer to) so the **bottom** button
confirms like you'd expect. Full write-up:
[docs/BUG-confirm-button.md](docs/BUG-confirm-button.md).

### Also fixed

The daemon now ignores the title/attract screens (`game_state`) and waits for a
stable screen before its first announcement, and the installers disable RetroArch's
network gamepad (`network_remote`, UDP 55400) which the daemon never needs. See
[docs/BUG-menu-selection.md](docs/BUG-menu-selection.md).

## Retargeting / other regions

Everything you need is in [docs/CALIBRATION.md](docs/CALIBRATION.md) and
[docs/research/](docs/research/). The game ships an **unstripped** copy of its own
executable (`mk5gc_release.elf`), so retargeting is reading a symbol table, not
guessing — `tools/` has the extractor and disassembler.

## Contributing

Yes please — especially Windows/Linux testing, the character-select
confirmation, and addresses for other regions. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).
Be kind: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Legal

This repository contains **no game code, assets, or data**. It is an independent
interoperability / accessibility tool: it reads values out of memory at runtime
and says them out loud. You supply your own copy of the game.

*Mortal Kombat* and related marks are trademarks of Warner Bros. Entertainment
Inc. This project is not affiliated with or endorsed by Warner Bros. or
NetherRealm Studios. See [LICENSE](LICENSE) (MIT).
