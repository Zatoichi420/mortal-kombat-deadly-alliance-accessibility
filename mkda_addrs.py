"""MK: Deadly Alliance (GameCube, GMKE5D, USA Rev 1) — addresses & label tables.

All addresses are live GameCube virtual addresses, read straight from the symbol
table of `mk5gc_release.elf` on the disc (unstripped build). Verified readable via
RetroArch `READ_CORE_MEMORY` 2026-09-05.

If the game is ever updated / a different region is used, re-derive with
tools/gc_extract.py + the pyelftools snippet in research/elf-symbols.md.
"""

GAME_ID = "GMKE5D"
GAME_CRC32 = "97e61be9"        # as reported by RetroArch GET_STATUS for this dump

# ---- menu system ----------------------------------------------------------
# Mechanism (verified by disassembly of run_common_menu_ctrl @ 0x800677b4):
#   menu_id      = read_u32(MENU_STACK + (menu_stack_ptr-1)*4)
#   rec          = MAIN_MENU_TBL + menu_id*MENU_REC_STRIDE
#   menu_def_ptr = read_u32(rec)                       # a *_menu struct in MENU_STRUCTS
#   cursor       = read_u32(rec + MENU_CURSOR_OFF)
#   label        = cstr(read_u32(menu_def_ptr + cursor*MENU_ITEM_STRIDE))
MENU_ON            = 0x8041bc90   # u32, nonzero while a menu screen is shown
MENU_STACK_PTR     = 0x8041be4c   # u32
MENU_STACK         = 0x803be928   # array of u32 menu_id, one per stack level
MAIN_MENU_TBL      = 0x80254f60   # array of 0x1c-byte menu records
MENU_REC_STRIDE    = 0x1c
MENU_CURSOR_OFF    = 0x10         # cursor index lives at rec+0x10
MENU_ITEM_STRIDE   = 0x0c         # [label ptr, disp fn, ctrl fn]
CURSOR_POSITION    = 0x8041be50   # (unused: NOT the menu cursor despite the name)
ACTIVE_MSEL_MENU   = 0x8041c774   # u32, which mode-select sub-screen
MODE_MENU_LAST_PAGE= 0x8041c784
F_MODE_SELECTED    = 0x8041c78c
F_OPTION_SELECTED  = 0x8041c788
GAME_STATE         = 0x8041be08
MODE_OF_PLAY       = 0x8041be30
GALLERY_ITEM       = 0x8041ca50
CURSOR_POS_GENERIC = 0x8041ca5c
PNE_CURSOR         = 0x8041c558

# ---- character select ----------------------------------------------------
# The pselect hover index is P1_POS / P2_POS (verified: update_header_art @
# 0x80074334 passes p1_pos to update_plyr_bio, which indexes char_data_tbl).
# It indexes char_data_tbl (stride 0x2c); entry+0x14 -> <name>_bio_tbl; bio[0] -> name.
# P1_CHAR / P2_CHAR hold the *confirmed* pick (== 0x18/24 means "not chosen / random").
# NOTE: live-confirm the P1_POS mapping on first real play via `menu_reader.py --probe`;
# if the spoken name is offset from the highlighted portrait, adjust ROSTER here.
P1_POS    = 0x8041bf8c   # u32 - P1 hovered roster slot (0 = Shang Tsung)
P2_POS    = 0x8041bf88
P1_CHAR   = 0x8041a8c0   # u32 - P1 confirmed pick (0x18 = none yet)
P2_CHAR   = 0x8041a8c4
P1_STATE  = 0x8041bee8   # u32 - 0 not joined; 2 = choosing; 4 = locked
P2_STATE  = 0x8041beec
F_PSEL_INIT    = 0x8041bf28   # u32 - nonzero while the character-select screen is up
CHAR_NONE      = 0x18         # p1_char/p2_char value meaning "not chosen"
CURRENT_ROW    = 0x8041c850
CURRENT_COLUMN = 0x8041c854
PRACTICE_P1_INDEX = 0x8041bdcc
PRACTICE_P2_INDEX = 0x8041bdc8

# ---- character data (for id -> name without a hardcoded table) --------------
CHAR_DATA_TBL   = 0x8025640c
CHAR_DATA_STRIDE = 0x2c
CHAR_DATA_BIO_OFF = 0x14          # entry+0x14 -> <name>_bio_tbl ; bio_tbl[0] -> name str
FEMALE_CHAR_LIST = 0x80248c00     # [9,4,11,15,17,24]

# ---- known menu-definition structs (item stride 12: label, disp_fn, ctrl_fn)
# key = menu_def struct address in .data ; value = friendly screen name.
# Item labels are read straight out of the struct at runtime; these lists are
# only a fallback / for "N of M" when a memory read fails.
MENU_STRUCTS = {
    0x802300e0: ("Pause menu", [
        "Continue", "Movelist / Profile", "Player Select", "Main Menu"]),
    0x8023011c: ("Pause menu", [
        "Continue", "Movelist / Profile", "Player Select", "Main Menu"]),
    0x80230140: ("Main menu", [
        "Arcade", "Versus", "Practice", "Konquest",
        "The Krypt", "Player Profile", "Options", "Kontent"]),
    0x802301ac: ("Options", [
        "Game Options", "Sound Options", "Controller Setup", "Screen Adjust"]),
    0x802301e8: ("Kontent", [
        "Unlocked", "Endings", "Development", "Prizes",
        "Products", "Making of MK", "MK History", "Adema"]),
}
MODE_SELECT_DEF = 0x80230140     # menu_def_ptr for the top-level mode/main menu

# Hover-description narration for the mode-select items (index-aligned with Mode select)
MODE_DESCRIPTIONS = [
    "Arcade. Face opponents across Outworld to defeat the Deadly Alliance.",
    "Versus. Play against a friend or enemy.",
    "Practice. Learn the moves that will make you a master kombatant.",
    "Konquest. Travel on a long journey, earning kurrency as you face hundreds of challenges.",
    "The Krypt. Buy characters, arenas and extras with your earned kurrency.",
    "Player Profile. Create a profile, view profiles, delete a profile.",
    "Options. Game settings, sound settings, controller setup, screen settings.",
    "Kontent. View purchased Krypt items, unlocked endings and exclusive videos.",
]

GAME_OPTIONS_LABELS = [
    "CPU Difficulty", "Rounds to Win", "Round Time", "Mini Game Every", "Blood Level"]

# ---- roster: P1_POS/P2_POS slot -> spoken name ---------------------------
# char_data_tbl order == the on-screen roster order (StrategyWiki + live bio walk:
# slot 0 Shang Tsung, 1 Bo' Rai Cho, 2 Quan Chi confirmed). The daemon prefers to
# dereference char_data_tbl in memory (order-proof); this is the fallback.
ROSTER_FROM_MEMORY = True
ROSTER_FALLBACK = [
    "Shang Tsung", "Bo' Rai Cho", "Quan Chi", "Li Mei", "Scorpion", "Sonya",
    "Kenshi", "Mavado", "Johnny Cage", "Sub-Zero", "Kano", "Kung Lao",
    "Nitara", "Drahmin", "Hsu Hao", "Frost", "Jax", "Kitana",
    "Raiden", "Reptile", "Cyrax",
]
ROSTER_EXTRA = {}   # Blaze/Mokap/Moloch are not in char_data_tbl / not normal slots
