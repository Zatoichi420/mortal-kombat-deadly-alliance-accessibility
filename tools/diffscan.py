#!/usr/bin/env python3
"""Automated 'what address changes when I press this button' scan.

Snapshots a RAM region, injects presses, re-snapshots, and reports addresses
whose value changed in a way consistent with a menu cursor (small int, moves
by +/-1, returns when you go back).

    python3 diffscan.py cursor   # press Down x1 repeatedly on a vertical menu
    python3 diffscan.py roster   # press Right repeatedly (character select strip)
    python3 diffscan.py raw 0x8041a000 0x8000 down 6   # generic

Scans .sdata+.sbss by default (0x8041a000..0x80421000) plus a slice of .bss.
"""

from __future__ import annotations

import sys
import time

from ra_client import RAClient

RA = RAClient()

# regions to watch (addr, length) — small-data + a chunk of .bss around the menu vars
REGIONS = [
    (0x8041A000, 0x7000),     # .sdata / .sbss / .sdata2
    (0x803BD000, 0x2000),     # around menu_stack / practice lists
    (0x803E3000, 0x2000),     # around *_menu_sel_items / current_page_data
]


def grab():
    out = {}
    for base, length in REGIONS:
        step = 0x400
        for off in range(0, length, step):
            n = min(step, length - off)
            try:
                out[base + off] = RA.read_memory(base + off, n)
            except Exception:
                pass
    return out


def flat(snap):
    b = {}
    for base, chunk in snap.items():
        for i in range(0, len(chunk) - 3, 4):
            b[base + i] = int.from_bytes(chunk[i:i + 4], "big")
    return b


def scan(press_button, n_steps, back_button):
    print(f"baseline snapshot...", flush=True)
    seq = [flat(grab())]
    for k in range(n_steps):
        RA.press(press_button)
        time.sleep(0.5)
        seq.append(flat(grab()))
        print(f"  press {k+1}/{n_steps}", flush=True)
    # candidates: addresses that changed monotonically-ish and stay small
    addrs = set(seq[0])
    cands = []
    for a in addrs:
        vals = [s.get(a) for s in seq]
        if any(v is None for v in vals):
            continue
        if len(set(vals)) < 2:
            continue
        if all(0 <= v < 64 for v in vals):
            deltas = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
            score = sum(1 for d in deltas if d in (1, -1, 0))
            cands.append((score, a, vals))
    cands.sort(reverse=True)
    print(f"\n== top changing small-int addresses after {n_steps}x {press_button} ==")
    for score, a, vals in cands[:15]:
        print(f"  {a:#010x}  score={score}/{n_steps}  values={vals}")

    if back_button and cands:
        print(f"\nnow pressing {back_button} x{n_steps} to check reversal...", flush=True)
        for _ in range(n_steps):
            RA.press(back_button)
            time.sleep(0.5)
        after = flat(grab())
        print("  address        was->now (should return toward baseline)")
        for score, a, vals in cands[:10]:
            print(f"  {a:#010x}  {vals[-1]} -> {after.get(a)}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "cursor"
    if mode == "cursor":
        scan("down", 7, "up")
    elif mode == "roster":
        scan("right", 12, "left")
    elif mode == "raw":
        base = int(sys.argv[2], 16); length = int(sys.argv[3], 16)
        btn = sys.argv[4]; n = int(sys.argv[5])
        REGIONS.clear(); REGIONS.append((base, length))
        scan(btn, n, None)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
