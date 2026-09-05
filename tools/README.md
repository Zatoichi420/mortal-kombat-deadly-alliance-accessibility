# tools/ — reverse-engineering & calibration helpers

These are **not** needed to run the talking-menu daemon. They are what was used to
build it, kept here so the work is reproducible and so a new region/revision can
be retargeted. Most are macOS-oriented (they shell out to `say` / Apple Vision
OCR) but the logic is portable.

| script | what it does |
|---|---|
| `gc_extract.py` | minimal GameCube disc reader — pull `main.dol` / `mk5gc_release.elf`, list & extract files. Works on plain ISO and NKit ISO. |
| `ppcdis.py` | disassemble a function in `mk5gc_release.elf` (capstone) and resolve `r13`/`r2` small-data accesses to global-variable names. Needs `pip install pyelftools capstone`. |
| `nav.py` | drive the game to a known screen (main menu, character select) using injected input + OCR, for calibration. |
| `see.py` | OCR the current RetroArch frame via the AI-service pipeline. |
| `diffscan.py` | press a button, diff RAM, report addresses that behave like a cursor. |
| `calibrate.py`, `verify.py` | full automated walks of the menus / roster, dumping address ↔ label maps. |
| `test_daemon_menu.py` | run the daemon's `narrate()` against a live menu walk, printing every phrase. |

Input injection (used by `nav.py`/`calibrate.py`/`verify.py`) requires, in
`retroarch.cfg`:
```
network_remote_enable = "true"
network_remote_enable_user_p1 = "true"
```
It sends RetroArch's 20-byte network-gamepad packet on UDP 55400 — see
`ra_client.py`. This is only for calibration; the daemon never injects input.
