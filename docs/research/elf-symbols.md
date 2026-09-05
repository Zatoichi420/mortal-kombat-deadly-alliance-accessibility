# MK:DA GameCube (GMKE5D) — symbol map from `mk5gc_release.elf`

**Huge win:** the disc ships `mk5gc_release.elf` (4.7 MB) alongside `main.dol`. Same program
(identical entry point `0x80005304`), but the ELF is **not stripped** — 18,360 symbols
(9,967 data objects, 6,092 functions) with real names. No cheat-search needed for the menu
side; addresses below are read directly from the symbol table and are live GC addresses
(static executable, .text fixed at `0x80005b80`).

Extracted with `tools/gc_extract.py`; parsed with pyelftools. Working copy:
`~/mkda-work/disc/mk5gc_release.elf`.

## Live state variables (.sdata / .sbss, ~0x8041a6c0–0x80420ac0)

### Menu system (mode-select, options, kontent, pause — all share one engine)
| addr | sym | meaning |
|---|---|---|
| `0x8041bc90` | `menu_on` | nonzero while a menu screen is displayed |
| `0x8041be50` | `cursor_position` | index of the highlighted item in the active menu |
| `0x8041be4c` | `menu_stack_ptr` | depth into `menu_stack` |
| `0x803be928` | `menu_stack` (40 B) | nav stack — entries point at the active `*_menu` struct |
| `0x8041be48` | `menu_pad` | which pad controls the menu |
| `0x8041be0c` | `menu_delay` | input repeat delay counter |
| `0x8041c774` | `active_msel_menu` | which mode-select sub-screen (main / options / kontent) |
| `0x8041c784` | `mode_menu_last_page` | paging within mode-select |
| `0x8041c78c` | `f_mode_selected` | a mode was chosen |
| `0x8041c788` | `f_option_selected` | an option item was chosen |
| `0x8041beb8` | `option_chosen` | |
| `0x8041be08` | `game_state` | high-level state (1 seen during attract) |
| `0x8041be30` | `mode_of_play` | (8 seen during attract) |
| `0x803e3718` | `mode_menu_sel_items` (128 B) | runtime item array for mode-select |
| `0x803e3698` | `kontent_menu_sel_items` (128 B) | runtime item array for kontent |

### Character select (pselect)
| addr | sym | meaning |
|---|---|---|
| `0x8041a8c0` | `p1_char` | P1 hovered/selected character id |
| `0x8041a8c4` | `p2_char` | P2 hovered/selected character id |
| `0x8041bee8` | `p1_state` | 0 = not joined, then choosing / locked |
| `0x8041beec` | `p2_state` | |
| `0x8041ca34` | `p1_pos` | P1 cursor pos on the grid (also a `p1_pos` at `0x8041bf8c`) |
| `0x8041ca30` | `p2_pos` | P2 cursor pos (also `0x8041bf88`) |
| `0x8041c850` | `current_row` | grid row (shared cursor context) |
| `0x8041c854` | `current_column` | grid column |
| `0x8041bf40` / `0x8041bf3c` | `p1_select_flags` / `p2_select_flags` | |
| `0x8041bf28` | `f_psel_initialized` | pselect screen is up |
| `0x8041a8d8` / `0x8041a8dc` | `p1_handicap` / `p2_handicap` | |

### Practice / other cursors
| addr | sym | meaning |
|---|---|---|
| `0x8041bdcc` / `0x8041bdc8` | `practice_p1_index` / `practice_p2_index` | practice char-select |
| `0x8041c558` / `0x8041c55c` | `pne_cursor` / `current_pne_cursor_pos` | profile name-entry keyboard cursor |
| `0x8041ca5c` | `cursor_pos` | generic (gallery / lists) |
| `0x8041ca50` | `gallery_current_item` | kontent gallery |

## VERIFIED menu-cursor mechanism (disasm of `run_common_menu_ctrl` @ 0x800677b4)

The active menu and its cursor are NOT `cursor_position` (that symbol is unused for
this). The real path, confirmed live 2026-09-05:

```
menu_id      = read_u32(0x803be928 + (read_u32(0x8041be4c) - 1) * 4)   # menu_stack[sp-1]
rec          = 0x80254f60 + menu_id * 0x1c                              # main_menu_tbl record
menu_def_ptr = read_u32(rec)          # -> a *_menu struct, e.g. 0x80230140 mode_select_menu
cursor       = read_u32(rec + 0x10)   # 0-based highlighted item index
label        = cstr(read_u32(menu_def_ptr + cursor * 0x0c))            # "     ARCADE      "
num_items    = count menu_def_ptr entries (stride 0x0c) until label ptr == NULL
```

menu_id values: 0 = pause_menu, 1 = mode_select_menu (the main menu), 2 = options_menu,
3 = kontent_menu, 4 = tym_pause_menu (Test Your Might pause). `main_menu_tbl` record is
7 words: [menu_def_ptr, menu_id, x, y, cursor, ?, ?]  (cursor at word index 4 = +0x10).

Live-verified: on the main menu, pressing Down stepped `cursor` 0..7 and label read back
ARCADE / VERSUS / PRACTICE / KONQUEST / THE KRYPT / PLAYER PROFILE / OPTIONS / KONTENT,
`num_items` = 8, `menu_def_ptr` = 0x80230140.

## Menu definition structs (.data) — item stride = 12 B: [char* label, disp_fn, ctrl_fn]

**`mode_select_menu` @ `0x80230140`** (8 items):
`ARCADE`, `VERSUS`, `PRACTICE`, `KONQUEST`, `THE KRYPT`, `PLAYER PROFILE`, `OPTIONS`, `KONTENT`
(labels stored padded with spaces, e.g. `"     ARCADE      "` — trim before speaking)

**`options_menu` @ `0x802301ac`** (4 items):
`GAME OPTIONS`, `SOUND OPTIONS`, `CONTROLLER SETUP`, `SCREEN ADJUST` (`0x802551a8`)

**`kontent_menu` @ `0x802301e8`** (8 items):
`UNLOCKED`, `ENDINGS`, `DEVELOPMENT`, `PRIZES`, `PRODUCTS`, `MAKING OF MK`, `MK HISTORY`, `ADEMA`

**`pause_menu` @ `0x802300e0`** (4 items):
`CONTINUE`, `MOVELIST/PROFILE`, `PLAYER SELECT`, `MAIN MENU`

**`game_options_tbl` @ `0x80254fec`** (5 rows, each [label, up_fn, down_fn, disp_fn]):
`CPU DIFFICULTY`, `ROUNDS TO WIN`, `ROUND TIME`, `MINI GAME EVERY`, `BLOOD LEVEL`

Hover-description text (shown beside each mode-select item) lives in the `*_menu_info`
structs (`arcade_menu_info` @ `0x8027a244`, etc.) and is nice extra narration:
- ARCADE: "FACE OPPONENTS ACROSS OUTWORLD TO DEFEAT THE DEADLY ALLIANCE"
- KONQUEST: "TRAVEL ON A LONG JOURNEY, EARNING KURRENCY AS YOU FACE HUNDREDS OF CHALLENGES"
- etc.

## Character data

**`char_data_tbl` @ `0x8025640c`**, stride **0x2c (44 B)**, 22 entries. Each entry:
`+0x14` → `<name>_bio_tbl` pointer. Table order (by the bio_tbl referenced):
```
 0 shang(Shang Tsung)  1 fatman(Bo' Rai Cho)  2 quan(Quan Chi)  3 limei(Li Mei)
 4 scorp(Scorpion)     5 sonya(Sonya)         6 blind(Kenshi)   7 mavado(Mavado)
 8 cage(Johnny Cage)   9 subzero(Sub-Zero)   10 kano(Kano)     11 kunglao(Kung Lao)
12 nitara(Nitara)     13 drahmin(Drahmin)   14 khan(Hsu Hao)   15 frost(Frost)
16 jax(Jax)           17 kitana(Kitana)     18 raiden(Raiden)  19 reptile(Reptile)
20 cyrax(Cyrax)      [21 ?]
```
**Not yet confirmed** that `p1_char` indexes this table in this order — verify by observation
or by driving the CSS with injected input. Boss/secret chars (Moloch, Blaze, Mokap) are not
in char_data_tbl.

**`<char>_bio_tbl`** (92 B each, e.g. `scorp_bio_tbl` @ `0x80255c10`): array of char*:
`[0]` = display name ("SCORPION"), then STATUS / ALIGNMENT / WEIGHT+HEIGHT / FIGHT STYLES /
DIFFICULTY strings. So **name = *(*(char_data_tbl + id*0x2c + 0x14))**.

**Name string pool** `@stringBase0` @ `0x80255904` (779 B) holds all fighter names as
plain uppercase ASCII: SCORPION, JAX, SHANG TSUNG, KUNG LAO, LI MEI, KENSHI, CYRAX, HSU HAO,
MOLOCH, SONYA, RAIDEN, FROST, QUAN CHI, MAVADO, KITANA, REPTILE, NITARA, DRAHMIN, SUB-ZERO,
BO' RAI CHO, KANO, BLAZE, MOKAP.

**`female_char_list` @ `0x80248c00`** = `[9, 4, 11, 15, 17, 24]` (char ids of the 6 women) —
a cross-check on whatever id space `p1_char` uses.

**`plyr_info` @ `0x8025639c`** — struct of pointers: `&p1_state, &p1_char, &p1_pos,
&p1_select_flags, ... &p2_state, &p2_char, &p2_pos, ...` (confirms the addresses above).

## Useful functions (for later Ghidra / behaviour questions)
`menu_ctrl_handler` `0x80067a68`, `menu_display_handler` `0x80067b30`, `get_active_menu_id`
`0x80067cb8`, `push_menu` `0x80067ce8`, `pop_menu` `0x80067c58`, `menu_init` `0x80067df4`,
`mode_menu_ctrl` `0x80065cec`, `mode_select_init` `0x8012b2f0`, `p_mode_select` `0x8012ae68`,
`display_mode_menu_item` `0x80129bbc`, `main_menu_disp` `0x800672cc`,
`main_menu_goto_pselect_ctrl` `0x80065f3c`, `pselect_init` `0x80075b24`, `p_pselect`
`0x800751d4`, `p_pselect_choose` `0x8007053c`, `restore_pselect_screen` `0x80071840`.
