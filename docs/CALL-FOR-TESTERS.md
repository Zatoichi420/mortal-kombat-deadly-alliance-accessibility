# Help wanted: testing two screen-reader accessibility mods for Mortal Kombat on GameCube

## What these are

Two small, free, open-source tools that make the **GameCube** versions of **Mortal
Kombat: Deadly Alliance** and **Mortal Kombat: Deception** playable without sight,
when the game runs in the **RetroArch** emulator.

They work by reading the running game's memory and **speaking the menus out loud**
through whatever text-to-speech your computer already has — the menu item you're on
("Arcade, 1 of 8"), the sub-menus, and the fighter you're hovering on the
character-select screen. **Nothing is written to the game. No ROM is modified. No
game files are included or distributed.** You supply your own legally-obtained copy
of the game.

They are developed and tested on **macOS**. The code is written to run on **Windows
and Linux** too — the emulator, the memory addresses, and the logic are identical
across platforms; only the "speak this text" and "start automatically" glue is
OS-specific. **That Windows and Linux path has never been run by anyone.** That's
what I need help with.

- **Deadly Alliance:** https://github.com/Zatoichi420/mortal-kombat-deadly-alliance-accessibility
- **Deception:** https://github.com/Zatoichi420/MK-deception-accessibility-mod

Both are MIT-licensed. Both have Issues and Discussions turned on.

## What I need help testing

**Priority 1 — does it work on Windows at all?**

- With **NVDA** running.
- With **JAWS** running.
- With **no screen reader running** (it should fall back to the built-in Windows
  SAPI voice via PowerShell).
- Does speech interrupt cleanly when you move quickly through a menu, or does it
  queue up and lag?

**Priority 2 — does it work on Linux at all?**

- With **Orca**, or whatever screen reader / speech setup you use.
- It expects `speech-dispatcher` + `espeak-ng` (`spd-say` on your PATH). Does that
  path work? Is the speech usable?

**Priority 3 — behaviour once it's running (any OS):**

- Do the **main-menu** items read correctly as you arrow up and down?
- Does **character select** speak the right fighter names for both players?
- How does the **latency** feel — press a direction, how long until you hear it?
- Anything that reads the wrong thing, reads twice, or goes silent when it
  shouldn't.

**Regions:** all addresses are for the **USA** release. If you have a PAL, German,
or Japanese copy and some reverse-engineering interest, there's a documented path
to retarget it (it's reading a symbol table the disc ships, not guessing).

## What you need on your computer

| Thing | Detail |
|---|---|
| **A computer** | Windows 10/11, macOS, or a Linux desktop. |
| **RetroArch** | Latest stable. Install the **"Nintendo - GameCube / Wii (Dolphin)"** core via RetroArch's Online Updater. |
| **The game** | Your own legally-obtained disc image of the **USA** release. Deadly Alliance disc ID `GMKE5D`; Deception disc ID `GQNE5D`. Any dump format (ISO / RVZ / NKit). The game must already boot and play in RetroArch before you start. |
| **Python** | Version 3.8 or newer, on your PATH. Windows: install from python.org and tick "Add Python to PATH". |
| **Text-to-speech** | **Windows:** nothing to install (uses the built-in SAPI voice). **macOS:** nothing to install (`say`). **Linux:** `sudo apt install speech-dispatcher espeak-ng` or your distro's equivalent. |
| **A screen reader** | Whatever you already use — NVDA, JAWS, Orca, VoiceOver. The tool speaks *alongside* your screen reader; it does not replace it. |

You do **not** need a compiler, a GitHub account (unless you want to file a
report), or any paid software.

## Setup, in short

Full step-by-step is in each repo's **README**. The short version:

1. In RetroArch: **Settings → Network → Network Commands → ON** (leave the port at
   55355).
2. Download the project: the green **Code** button → **Download ZIP**, and unzip
   it. (Or `git clone` if you use git.)
3. Run the installer for your OS from inside that folder:
   - **Windows:** `powershell -ExecutionPolicy Bypass -File install\windows\install.ps1`
   - **Linux:** `install/linux/install.sh`
   - **macOS:** `install/macos/install.sh`

   The installer copies the tool to a stable location and registers it to start in
   the background at login.
4. **Or skip the installer entirely** and just run `python deception_reader.py`
   (or `python menu_reader.py` for Deadly Alliance) in a terminal whenever you
   play.
5. Start the game in RetroArch. Within a second or two it should start speaking as
   you move through the menus.

**Optional confirm-button fix:** RetroArch's Dolphin core maps the GameCube
"confirm" button to the *right* face button (B / Circle), not the bottom one, so
pressing the button you'd expect can act as "Back". Each repo has an optional
controller remap in `extras/` that swaps it; the installer offers to apply it.

## How to report back

- **GitHub Issues** on the relevant repo is best — there are templates. Please
  attach:
  - Your OS and version, your screen reader, your Python version.
  - The **log file** (the README says where it is for each OS).
  - The output of `python deception_reader.py --probe` (or `menu_reader.py
    --probe`) taken on the screen where something went wrong — this prints the
    live state without speaking.
- **GitHub Discussions** for "it works!" reports, questions, or general feedback.
- Or reply in the forum thread and I'll help you get a report together.

## Deliberately out of scope

To set expectations: **online play, Profiles, the Krypt, and Konquest (story mode)
are not supported** in Deception and are not being worked on — the project targets
offline Kombat / Versus / Practice / Puzzle / Chess. If any of those matter to
you, they'd make excellent contributions; open an issue and I'll point you at the
right place in the code.

## Legal / ethical note

These repositories contain **no game code, assets, or data** and never will. They
are independent interoperability / accessibility tools: they read values out of
memory at runtime and say them out loud. Please **do not** attach ROMs, disc
images, or extracted game files to issues or PRs. *Mortal Kombat* and related
marks are trademarks of Warner Bros. Entertainment Inc.; these projects are not
affiliated with or endorsed by Warner Bros. or NetherRealm Studios.
