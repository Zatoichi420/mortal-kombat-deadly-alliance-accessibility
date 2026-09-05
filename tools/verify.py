#!/usr/bin/env python3
"""Verify the menu-cursor and character-select mechanism live, and build the
roster id->name map. Writes research/calibration-verify.md.

Mechanism under test (from disassembly of run_common_menu_ctrl / p_pselect_choose):
  menu_id      = read_u32(MENU_STACK + (menu_stack_ptr-1)*4)     # MENU_STACK 0x803be928
  rec          = MAIN_MENU_TBL + menu_id*0x1c                     # MAIN_MENU_TBL 0x80254f60
  menu_def_ptr = read_u32(rec)                                    # e.g. 0x80230140 mode_select_menu
  cursor       = read_u32(rec + 0x10)
  label        = cstr(read_u32(menu_def_ptr + cursor*0xc))
  CSS hovered char = read_u32(P1_CHAR 0x8041a8c0) / P2_CHAR 0x8041a8c4
"""
from __future__ import annotations
import time
from ra_client import RAClient
from see import see
from nav import goto_mode_select, classify
import mkda_addrs as A

MAIN_MENU_TBL = 0x80254F60
REC_STRIDE = 0x1C
CURSOR_OFF = 0x10
R = RAClient()
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); OUT.append(s)

def cstr(addr, n=40):
    if not (0x80003000 <= addr < 0x81800000): return ""
    raw = R.read_memory(addr, n)
    return raw.split(b"\0")[0].decode("latin1", "replace").strip()

def active_menu():
    sp = R.read_u32(A.MENU_STACK_PTR)
    if sp < 1: return None
    menu_id = R.read_u32(A.MENU_STACK + (sp - 1) * 4)
    if menu_id > 8: return None
    rec = MAIN_MENU_TBL + menu_id * REC_STRIDE
    menu_def = R.read_u32(rec)
    cursor = R.read_u32(rec + CURSOR_OFF)
    # num items
    n = 0
    while n < 20:
        lp = R.read_u32(menu_def + n * 0xC)
        if not (0x80200000 <= lp < 0x80300000): break
        n += 1
    label = cstr(R.read_u32(menu_def + cursor * 0xC)) if 0 <= cursor < n else "?"
    return dict(menu_id=menu_id, menu_def=menu_def, cursor=cursor, n=n, label=label)


def test_menu_cursor():
    log("\n===== MENU CURSOR TEST (mode-select) =====")
    if not goto_mode_select(R, verbose=False):
        log("!! could not reach mode-select"); return
    R.tap_repeat("up", 9, gap=0.14); time.sleep(0.5)
    for i in range(10):
        am = active_menu()
        ocr = " | ".join(see())
        log(f"  down#{i}: {am}   OCR-desc: {ocr[:80]}")
        R.press("down"); time.sleep(0.55)
    R.tap_repeat("up", 9, gap=0.14); time.sleep(0.4)


def test_charselect():
    log("\n===== CHARACTER SELECT TEST =====")
    if not goto_mode_select(R, verbose=False):
        log("!! not at mode-select"); return
    R.tap_repeat("up", 9, gap=0.14); time.sleep(0.4)     # ARCADE
    R.press("a"); time.sleep(3.0)
    for _ in range(5):
        l = see(); st = classify(l)
        log(f"  entering CSS... {st} | {' | '.join(l)[:80]}")
        if st == "char-select": break
        R.press("a"); time.sleep(2.0)
    roster = {}
    for i in range(26):
        p1c = R.read_u32(A.P1_CHAR); p1p = R.read_u32(A.P1_POS)
        row = R.read_u32(A.CURRENT_ROW); col = R.read_u32(A.CURRENT_COLUMN)
        lines = see()
        # bio name = first 1-2 all-caps lines before STATUS:
        name = None
        for j, ln in enumerate(lines):
            if ln.strip().upper().startswith("STATUS"):
                name = " ".join(lines[:j]).strip(); break
        if not name and lines:
            name = lines[0]
        log(f"  i={i:2} p1_char={p1c} p1_pos={p1p} row={row} col={col}  bio={name!r}")
        if p1c is not None and 0 <= p1c < 40:
            roster.setdefault(p1c, name)
        R.press("right"); time.sleep(0.5)
    log("\n  ROSTER MAP (p1_char -> bio name):")
    for k in sorted(roster):
        log(f"    {k:2} : {roster[k]}")
    R.tap_repeat("b", 6, gap=0.3)


if __name__ == "__main__":
    log("RetroArch:", R.version(), R.status())
    test_menu_cursor()
    test_charselect()
    import pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "research" / "calibration-verify.md"
    p.write_text("# MK:DA live calibration\n\n```\n" + "\n".join(OUT) + "\n```\n")
    log(f"\nsaved -> {p}")
