# How it works

## The idea

Mortal Kombat: Deadly Alliance is a 2002 GameCube game with no accessibility. You
can't add code to it easily, but you **can** read its memory while it runs in an
emulator. This project is a small Python program that watches the game's RAM and
speaks the menu item you're on.

```
  RetroArch  ──(Dolphin core, running MK:DA)
      │
      │  UDP :55355   "READ_CORE_MEMORY <addr> <n>"
      ▼
  menu_reader.py  ── every ~80 ms: read the menu cursor, look up the label,
      │              speak it when it changes (debounced, interruptible)
      ▼
   say / spd-say / SAPI          (whatever TTS the OS has)
```

Nothing is written to the game. The daemon only reads.

## Why it's the same on Windows, macOS and Linux

The addresses this tool reads (`0x8041bc90`, `0x80254f60`, …) are **GameCube
virtual addresses**. They are a property of the *game*, not the host. RetroArch's
`dolphin_libretro` core exposes GameCube main memory (MEM1) at guest address
`0x80000000` through the same `READ_CORE_MEMORY` command on every platform. So the
hard part — the reverse engineering — is done once and works everywhere. Only the
"speak this string" and "run at startup" parts are OS-specific, and those are
small (`speak.py` + the three `install/` folders).

Requirements that are identical everywhere:
- RetroArch with the **Dolphin** core, running MK:DA **USA** (disc id `GMKE5D`).
- `network_cmd_enable = "true"` in `retroarch.cfg`
  (Settings → Network → Network Commands).
- Python 3.8+.

## The menu-cursor mechanism (reverse-engineered, verified live)

The disc ships `mk5gc_release.elf` — the same program as the boot executable, but
**with its debug symbol table intact** (18,360 named symbols). That's how the
addresses below were found, by disassembling the game's own
`run_common_menu_ctrl` function rather than guessing.

```
menu_stack_ptr = read_u32(0x8041be4c)
menu_id        = read_u32(0x803be928 + (menu_stack_ptr - 1) * 4)   # 0..4
record         = 0x80254f60 + menu_id * 0x1c                       # main_menu_tbl
menu_def       = read_u32(record)          # -> one of the *_menu structs
cursor         = read_u32(record + 0x10)   # highlighted item, 0-based
label_ptr      = read_u32(menu_def + cursor * 0x0c)
label          = C-string at label_ptr     # e.g. "     ARCADE      "
item_count     = walk menu_def by 0x0c until the label pointer is 0
```

`menu_id`: 0 = pause menu, 1 = main menu, 2 = Options, 3 = Kontent, 4 = Test
Your Might pause. `menu_on` at `0x8041bc90` is non-zero whenever a menu is up.

Live test result — Down-walking the main menu stepped `cursor` 0→7 and the label
read back exactly `ARCADE / VERSUS / PRACTICE / KONQUEST / THE KRYPT / PLAYER
PROFILE / OPTIONS / KONTENT`.

## Character select

`f_psel_initialized` (`0x8041bf28`) ≠ 0 → the character-select screen is up.
The hovered fighter is `p1_pos` (`0x8041bf8c`) / `p2_pos` (`0x8041bf88`), an index
into `char_data_tbl` (`0x8025640c`, stride `0x2c`; entry `+0x14` → a bio table
whose first pointer is the display-name string). Roster order is the on-screen
order: Shang Tsung, Bo' Rai Cho, Quan Chi, Li Mei, Scorpion, Sonya, Kenshi,
Mavado, Johnny Cage, Sub-Zero, Kano, Kung Lao, Nitara, Drahmin, Hsu Hao, Frost,
Jax, Kitana, Raiden, Reptile, Cyrax.

This one address wants a 60-second confirmation on first real play — see
[CALIBRATION.md](CALIBRATION.md).

## Game Options and the other full-screen adjusters

Screens like **Game Options** are *not* the same menu system — they don't set
`menu_on`. `game_state == 18` plus the last menu item you picked identifies the
screen; the row cursor is `cursor_position` (`0x8041be50`, the symbol the main
menu does *not* use); labels come from `game_options_tbl` (`0x80254fec`, 5 rows of
`[label, up_fn, down_fn, disp_fn]`); and the current value of each row is a
`tmp_*` variable (`0x8041be5c`–`0x8041be6c`, all inside the one block the daemon
already reads). So it speaks e.g. "Game Options. CPU Difficulty: Medium". Sound
Options / Controller Setup / Screen Adjust are the same shape but not wired yet.

## Match start

`game_state == 5` = a round is being fought. `p1_char` / `p2_char`
(`0x8041a8c0` / `0x8041a8c4`) then hold the **internal** character id — the first
word of each `char_data_tbl` entry, *not* the roster slot — so the daemon builds a
one-time `id → slot` reverse map from `char_data_tbl` and announces the matchup
once per round, left fighter first: "Shang Tsung versus Johnny Cage".

## Latency

RetroArch answers ~one network command per emulated frame (~16.5 ms). A poll
therefore reads in **3 bulk blocks** (the `.sdata` variable cluster + `menu_stack`
+ `main_menu_tbl`), not ~15 point reads; item counts and label strings are cached
(they never change); and there's no settle delay on a cursor move — `say`
interrupts the previous word and the ~50 ms poll is the debounce. Keypress →
speech is ~75 ms (it was ~1.5 s before this work). Details:
[AUDIT-menu-latency.md](AUDIT-menu-latency.md).

## Files

| file | role |
|---|---|
| `menu_reader.py` | the daemon — classify screen, resolve label, speak on change |
| `ra_client.py` | RetroArch UDP client (`READ_CORE_MEMORY`, `GET_STATUS`, …). Pure sockets. |
| `mkda_addrs.py` | every address + the menu label / roster tables. **Edit here** to retarget. |
| `speak.py` | cross-platform interruptible TTS |
| `tools/` | the reverse-engineering / calibration helpers used to build this (macOS-oriented) |
| `docs/research/` | the raw research notes (four deep dives + the symbol map) |
