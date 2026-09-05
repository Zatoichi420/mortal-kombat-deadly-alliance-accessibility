#!/usr/bin/env python3
"""End-to-end test of the daemon's MENU narration against a live menu walk.
Navigates to mode-select, runs the MenuReader narrate() loop in-process while
pressing Down, prints every utterance it would speak.
"""

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import os, time
os.environ["MK_SPEAK_BACKEND"] = "log"
from ra_client import RAClient
from nav import goto_mode_select
from menu_reader import MenuReader

r = RAClient()
print("nav to mode-select...", flush=True)
goto_mode_select(r, verbose=False)
mr = MenuReader(r)
r.tap_repeat("up", 9, gap=0.12)
time.sleep(0.4)

for step in range(11):
    for _ in range(3):                 # poll a few times so settle logic fires
        mr.narrate(mr.snapshot())
        time.sleep(0.12)
    r.press("down")
    time.sleep(0.5)

print("\n-- now walk into Options submenu --", flush=True)
r.tap_repeat("up", 9, gap=0.12); time.sleep(0.3)
r.tap_repeat("down", 6, gap=0.25)      # OPTIONS is index 6
time.sleep(0.3)
r.press("a"); time.sleep(1.5)
for step in range(5):
    for _ in range(3):
        mr.narrate(mr.snapshot()); time.sleep(0.12)
    r.press("down"); time.sleep(0.5)
r.tap_repeat("b", 4, gap=0.3)
