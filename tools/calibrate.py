#!/usr/bin/env python3
"""Drive MK:DA with injected input + OCR to map menu/character-select state to RAM.

Outputs a calibration report to stdout (and --save writes it to
research/calibration-<timestamp>.md). Read-only w.r.t. the game except for the
button presses it injects; safe to re-run.

Steps:
  1. Escape attract mode -> main menu (Start/B, confirmed by OCR).
  2. Walk the main menu with Down, recording cursor_position + OCR label + the
     active menu-struct pointer.
  3. Enter the first item (Arcade) -> character select; press Right across the
     roster recording p1_char + OCR fighter name.
  4. Back out.
"""

from __future__ import annotations

import argparse
import sys
import time

from ra_client import RAClient, RetroArchError
from see import see
import mkda_addrs as A

R = RAClient()


def rd(addr):
    try:
        return R.read_u32(addr)
    except RetroArchError:
        return None


def snap():
    return {
        "menu_on": rd(A.MENU_ON), "cursor": rd(A.CURSOR_POSITION),
        "stack_ptr": rd(A.MENU_STACK_PTR), "active_msel": rd(A.ACTIVE_MSEL_MENU),
        "game_state": rd(A.GAME_STATE), "mode_of_play": rd(A.MODE_OF_PLAY),
        "p1_state": rd(A.P1_STATE), "p2_state": rd(A.P2_STATE),
        "p1_char": rd(A.P1_CHAR), "p2_char": rd(A.P2_CHAR),
        "row": rd(A.CURRENT_ROW), "col": rd(A.CURRENT_COLUMN),
        "psel_init": rd(A.F_PSEL_INIT), "f_mode_sel": rd(A.F_MODE_SELECTED),
    }


def menu_stack_slots():
    try:
        b = R.read_memory(A.MENU_STACK, 40)
    except RetroArchError:
        return []
    return [int.from_bytes(b[i:i + 4], "big") for i in range(0, 40, 4)]


def label_at(struct_ptr, idx, stride=12):
    if not struct_ptr or not (0x80200000 <= struct_ptr < 0x80300000):
        return None
    try:
        lp = R.read_u32(struct_ptr + idx * stride)
        if not (0x80200000 <= lp < 0x80300000):
            return None
        raw = R.read_memory(lp, 40)
        return raw.split(b"\0")[0].decode("latin1", "replace").strip()
    except RetroArchError:
        return None


OUT = []
def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    OUT.append(line)


def escape_to_menu(max_tries=25):
    log("\n== escaping attract mode ==")
    for i in range(max_tries):
        txt = " | ".join(see())
        s = snap()
        log(f"[{i}] OCR: {txt[:120]}")
        log(f"     state: menu_on={s['menu_on']} gs={s['game_state']} cur={s['cursor']} "
            f"psel={s['psel_init']} p1s={s['p1_state']} stack={[hex(x) for x in menu_stack_slots() if x and x!=0xffffffff]}")
        up = txt.upper()
        if s["menu_on"] and any(k in up for k in ("ARCADE", "VERSUS", "KONQUEST", "OPTIONS", "KRYPT")):
            log("  -> reached a menu")
            return True
        # if a demo match / cutscene: Start to break out; if 'press start': Start; else B then Start
        R.press("start"); time.sleep(0.5)
        R.press("b"); time.sleep(0.4)
        R.press("start"); time.sleep(1.2)
    return False


def walk_main_menu():
    log("\n== walking main menu (Down x12) ==")
    seen = {}
    for i in range(12):
        s = snap()
        slots = [x for x in menu_stack_slots() if x and x != 0xFFFFFFFF]
        struct_ptr = next((x for x in reversed(slots) if x in A.MENU_STRUCTS), slots[-1] if slots else None)
        lbl_mem = label_at(struct_ptr, s["cursor"] or 0)
        ocr = " | ".join(see())
        log(f"  step {i}: cursor={s['cursor']} struct={hex(struct_ptr) if struct_ptr else None} "
            f"label(mem)={lbl_mem!r}  active_msel={s['active_msel']}")
        log(f"           OCR: {ocr[:140]}")
        key = s["cursor"]
        if key in seen:
            log("  (cursor wrapped / repeated - stopping walk)")
            break
        seen[key] = (lbl_mem, ocr)
        R.press("down"); time.sleep(0.5)
    return seen


def into_charselect():
    log("\n== entering first menu item -> character select ==")
    # make sure we're at top
    R.tap_repeat("up", 10, gap=0.12)
    time.sleep(0.4)
    s = snap(); log(f"  at top: cursor={s['cursor']}")
    R.press("a"); time.sleep(2.5)          # confirm Arcade
    for i in range(6):
        s = snap(); ocr = " | ".join(see())
        log(f"  [{i}] psel_init={s['psel_init']} p1s={s['p1_state']} p1_char={s['p1_char']} "
            f"row={s['row']} col={s['col']} gs={s['game_state']}")
        log(f"       OCR: {ocr[:140]}")
        if s["psel_init"] or s["p1_state"]:
            break
        R.press("a"); time.sleep(1.5)


def walk_roster():
    log("\n== walking roster (Right x24) ==")
    mapping = {}
    for i in range(26):
        s = snap()
        ocr_lines = see()
        ocr = " | ".join(ocr_lines)
        cid = s["p1_char"]
        # first OCR line that looks like a name (all caps, letters/spaces)
        name = next((ln for ln in ocr_lines if ln.replace(" ", "").replace("'", "").replace("-", "").isalpha()
                     and ln.upper() == ln and 3 <= len(ln) <= 14), None)
        log(f"  i={i:2} p1_char={cid} row={s['row']} col={s['col']}  name?={name!r}   OCR: {ocr[:100]}")
        if cid is not None:
            mapping.setdefault(cid, name or ocr[:40])
        R.press("right"); time.sleep(0.45)
    log("\n  roster map (p1_char -> name):")
    for k in sorted(x for x in mapping if x is not None):
        log(f"    {k:3} : {mapping[k]}")
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--skip-escape", action="store_true")
    args = ap.parse_args()

    log("RetroArch:", R.version(), R.status())
    if not args.skip_escape:
        if not escape_to_menu():
            log("!! could not confirm a menu via OCR; continuing anyway")
    walk_main_menu()
    into_charselect()
    walk_roster()
    # back out
    R.tap_repeat("b", 8, gap=0.3)

    if args.save:
        import datetime, pathlib
        p = pathlib.Path(__file__).resolve().parent.parent / "research" / \
            f"calibration-{datetime.datetime.now():%Y%m%d-%H%M%S}.md"
        p.write_text("# MK:DA calibration run\n\n```\n" + "\n".join(OUT) + "\n```\n")
        log(f"\nsaved -> {p}")


if __name__ == "__main__":
    main()
