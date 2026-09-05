"""Reliable navigation helpers for MK:DA calibration — get the game to a known
screen using OCR feedback, one deliberate press at a time.

Not part of the shipped talking-menu daemon; only used to reach states during
address calibration.
"""

from __future__ import annotations

import time

from ra_client import RAClient
from see import see


def classify(lines) -> str:
    up = " ".join(lines).upper()
    if "QUIT MATCH" in up:
        return "quit-dialog"
    if ("ARCADE" in up and "VERSUS" in up and ("KONQUEST" in up or "KRYPT" in up)):
        return "mode-select"
    if "RESUME" in up or ("MOVES LIST" in up and "MAIN MENU" in up):
        return "pause"
    if "STATUS:" in up or "ALIGNMENT:" in up or "FIGHT STYLES:" in up:
        return "char-select"
    if "PRESS START" in up:
        return "title"
    if "DIFFICULTY:" in up and "TIME:" in up:
        return "in-match"
    if "FLAWLESS" in up or "WINS!" in up or "FINISH" in up or "VICTORY" in up:
        return "match-end"
    FIGHTERS = ("SCORPION", "SUB-ZERO", "SUBZERO", "KENSHI", "KANO", "SONYA", "CYRAX",
                "RAIDEN", "KUNG LAO", "JOHNNY CAGE", "KITANA", "QUAN CHI", "SHANG TSUNG",
                "REPTILE", "MAVADO", "NITARA", "LI MEI", "HSU HAO", "DRAHMIN", "FROST",
                "BO' RAI CHO", "BLAZE", "MOKAP", "MOLOCH", "JAX")
    STYLES = ("KARATE", "SNAKE", "CRANE", "JUDO", "TAE KWON DO", "HAPKIDO", "DRAGON",
              "MANTIS", "SHOTOKAN", "TANG SOO DO", "XING YI", "BAJI", "PI GUA", "KENPO")
    hits = sum(1 for f in FIGHTERS if f in up) + sum(1 for s in STYLES if s in up)
    if hits >= 2 or any(s in up for s in STYLES):
        return "in-match"
    if not up.strip():
        return "blank"
    return "unknown:" + up[:60]


def goto_mode_select(ra: RAClient, verbose=True, max_steps=40) -> bool:
    for step in range(max_steps):
        lines = see(ra)
        st = classify(lines)
        if verbose:
            print(f"  [{step:2}] {st:14} | {' | '.join(lines)[:100]}", flush=True)
        if st == "mode-select":
            return True
        if st == "quit-dialog":
            ra.press("a"); time.sleep(3.0)            # confirm YES
        elif st == "pause":
            # cursor to MAIN MENU (4th item) then confirm
            ra.tap_repeat("down", 4, gap=0.35)
            time.sleep(0.3)
            ra.press("a"); time.sleep(1.5)
        elif st == "char-select":
            ra.press("b"); time.sleep(1.2)
        elif st in ("in-match", "match-end"):
            ra.press("start"); time.sleep(1.5)       # open pause menu
        elif st == "title":
            ra.press("start"); time.sleep(2.0)
        elif st == "blank":
            time.sleep(1.5)
        else:
            ra.press("b"); time.sleep(1.0)
    return False


if __name__ == "__main__":
    ra = RAClient()
    ok = goto_mode_select(ra)
    print("REACHED MODE-SELECT" if ok else "FAILED to reach mode-select")
