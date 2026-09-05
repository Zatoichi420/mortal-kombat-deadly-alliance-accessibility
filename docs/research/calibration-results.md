# MK:DA talking-menu — calibration results (2026-09-05)

Method: drove the running game with injected controller input (RetroArch
network_remote, UDP 55400) while reading RAM (UDP 55355) and OCR'ing frames,
plus static disassembly of the unstripped `mk5gc_release.elf` with capstone.

## CONFIRMED WORKING (verified live, end-to-end with speech)

### Menu narration — the main menu and every submenu
Mechanism (from disasm of `run_common_menu_ctrl` @ 0x800677b4, verified live):
```
sp        = read_u32(0x8041be4c)                       # menu_stack_ptr
menu_id   = read_u32(0x803be928 + (sp-1)*4)            # menu_stack top
rec       = 0x80254f60 + menu_id*0x1c                  # main_menu_tbl record
menu_def  = read_u32(rec)                              # -> a *_menu struct
cursor    = read_u32(rec + 0x10)                       # highlighted item, 0-based
label     = cstring(read_u32(menu_def + cursor*0x0c))  # e.g. "     ARCADE      "
count     = walk menu_def by 0x0c until label ptr == 0
```
Live test result — pressing Down on the main menu stepped `cursor` 0..7 and the
label read back exactly:
`ARCADE / VERSUS / PRACTICE / KONQUEST / THE KRYPT / PLAYER PROFILE / OPTIONS / KONTENT`
with count = 8, menu_def = 0x80230140.

menu_id map: 0 pause_menu · 1 main menu (mode_select) · 2 options_menu ·
3 kontent_menu · 4 tym_pause_menu.

The launchd daemon was observed speaking (`say` active) on 6/8 cursor moves during
an automated Down-walk — the pipeline works with no human in the loop.

### Screen classification
`menu_on` (0x8041bc90) != 0  ->  a menu is up.
`f_psel_initialized` (0x8041bf28) != 0  ->  character-select screen is up.
`game_state` (0x8041be08): 1/20 title & attract-idle, 2 attract pselect demo,
5 attract match, 11 in a menu.

## HIGH CONFIDENCE, NOT FULLY LIVE-CONFIRMED

### Character-select hover -> fighter name
`update_header_art` (0x8007422c) passes **`p1_pos` (0x8041bf8c)** / **`p2_pos`
(0x8041bf88)** to `update_plyr_bio`, which indexes `char_data_tbl` (0x8025640c,
stride 0x2c; entry+0x14 -> `<name>_bio_tbl`; bio[0] -> display-name string).

Live evidence: on the character-select screen, pressing Right made the on-screen
bio cycle **SHANG TSUNG -> BO' RAI CHO -> QUAN CHI** — exactly `char_data_tbl`
order — before the automated run lost the screen to the attract timer. The
`p1_pos` reads showed 0 throughout, which is most likely a stale-read / stuck-
cursor artifact of the attract-mode countdown rather than the wrong address, but
this specific address should be re-checked on first real play.

Roster order (char_data_tbl == on-screen order, per StrategyWiki):
```
 0 Shang Tsung   1 Bo' Rai Cho  2 Quan Chi   3 Li Mei     4 Scorpion
 5 Sonya         6 Kenshi       7 Mavado     8 Johnny Cage 9 Sub-Zero
10 Kano         11 Kung Lao    12 Nitara    13 Drahmin    14 Hsu Hao
15 Frost        16 Jax         17 Kitana    18 Raiden     19 Reptile   20 Cyrax
```
`p1_char`/`p2_char` (0x8041a8c0 / 0x8041a8c4) hold the *confirmed* pick after
you press A; value 0x18 (24) = "not chosen yet".

## HOW TO FINISH CALIBRATION ON FIRST REAL PLAY

1. Start MK:DA in RetroArch, press Start to the main menu — you should already
   hear "Arcade, 1 of 8" etc. as you move. (If not: `tail -f
   ~/Library/Logs/mkda-menu-reader.log` and check `menu_reader.py --probe`.)
2. Go into Arcade -> character select. Run
   `python3 ~/mkda-work/menu-reader/menu_reader.py --probe` in a terminal and
   move the roster cursor left/right. Watch the `p1pos=` field.
   - If `p1pos` counts up/down with the highlight and matches the roster order
     above -> done, nothing to change.
   - If it's a different field (`p1c`, `row`, `col`) or offset -> set `P1_POS`
     / `P2_POS` (and re-check the roster list) in
     `~/mkda-work/menu-reader/mkda_addrs.py`, then
     `launchctl kickstart -k gui/$UID/com.orlando.mkda-menu-reader`.
