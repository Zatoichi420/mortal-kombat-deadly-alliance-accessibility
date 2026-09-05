#!/usr/bin/env python3
"""MK: Deadly Alliance (GameCube) talking-menu daemon.  Windows / macOS / Linux.

Polls the running game's RAM through RetroArch's UDP command interface and speaks
the highlighted menu item / hovered fighter as the player navigates. Speech goes
through whatever TTS the OS has (see speak.py). Nothing here writes to the game.

    python menu_reader.py             # run the daemon (waits for the game, then narrates)
    python menu_reader.py --probe     # print the raw state snapshot ~4x/s, no speech
    python menu_reader.py --once      # one snapshot, exit
    python menu_reader.py --descriptions   # speak the long mode blurbs

Env: MKDA_RA_HOST (default 127.0.0.1), MKDA_RA_PORT (default 55355),
     MKDA_VOICE, MKDA_RATE_WPM, MKDA_SPEAK_BACKEND  (see speak.py).

Requires in retroarch.cfg (same on every OS):  network_cmd_enable = "true"
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from ra_client import RAClient, RetroArchError
import mkda_addrs as A
from speak import Speaker

POLL_HZ = 12
SETTLE_S = 0.10           # wait for the cursor to stop before announcing


def read_cstring(ra: RAClient, addr: int, maxlen: int = 48) -> str:
    if not (0x80003000 <= addr < 0x81800000):
        return ""
    raw = ra.read_memory(addr, maxlen)
    nul = raw.find(b"\0")
    if nul >= 0:
        raw = raw[:nul]
    return raw.decode("latin1", "replace").strip()


class Context:
    IDLE = "idle"
    MENU = "menu"
    CHARSELECT = "charselect"
    PRACTICE_SELECT = "practice-select"
    NAME_ENTRY = "name-entry"


class MenuReader:
    def __init__(self, ra: RAClient, speaker: Speaker | None = None,
                 announce_descriptions: bool = False):
        self.ra = ra
        self.say = speaker or Speaker()
        self.announce_descriptions = announce_descriptions
        self._last_spoken_key = None
        self._pending_key = None
        self._pending_since = 0.0
        self._last_context = None
        self._roster_cache: dict[int, str] = {}

    # ---- reading helpers --------------------------------------------------

    def _active_menu(self) -> dict | None:
        """Resolve the currently-displayed menu via the verified mechanism:
        menu_id from the nav stack -> record in main_menu_tbl -> menu_def + cursor."""
        try:
            if not self.ra.read_u32(A.MENU_ON):
                return None
            sp = self.ra.read_u32(A.MENU_STACK_PTR)
            if sp < 1:
                return None
            menu_id = self.ra.read_u32(A.MENU_STACK + (sp - 1) * 4)
            if menu_id > 8:
                return None
            rec = A.MAIN_MENU_TBL + menu_id * A.MENU_REC_STRIDE
            menu_def = self.ra.read_u32(rec)
            cursor = self.ra.read_u32(rec + A.MENU_CURSOR_OFF)
        except RetroArchError:
            return None
        if not (0x80200000 <= menu_def < 0x80300000):
            return None
        n = 0
        while n < 24:
            try:
                lp = self.ra.read_u32(menu_def + n * A.MENU_ITEM_STRIDE)
            except RetroArchError:
                break
            if not (0x80200000 <= lp < 0x80300000):
                break
            n += 1
        return {"menu_id": menu_id, "menu_def": menu_def, "cursor": cursor, "n": n}

    def _roster_name(self, cid: int) -> str:
        if cid in self._roster_cache:
            return self._roster_cache[cid]
        name = ""
        if A.ROSTER_FROM_MEMORY and 0 <= cid < 40:
            try:
                bio = self.ra.read_u32(A.CHAR_DATA_TBL + cid * A.CHAR_DATA_STRIDE + A.CHAR_DATA_BIO_OFF)
                namep = self.ra.read_u32(bio)
                name = read_cstring(self.ra, namep, 24).title()
            except RetroArchError:
                name = ""
        if not name:
            if cid in A.ROSTER_EXTRA:
                name = A.ROSTER_EXTRA[cid]
            elif 0 <= cid < len(A.ROSTER_FALLBACK):
                name = A.ROSTER_FALLBACK[cid]
            else:
                name = f"character {cid}"
        self._roster_cache[cid] = name
        return name

    # ---- snapshot -------------------------------------------------------

    def snapshot(self) -> dict:
        ra = self.ra
        s = {}
        s["menu_on"] = ra.read_u32(A.MENU_ON)
        s["menu_stack_ptr"] = ra.read_u32(A.MENU_STACK_PTR)
        s["active_msel_menu"] = ra.read_u32(A.ACTIVE_MSEL_MENU)
        s["game_state"] = ra.read_u32(A.GAME_STATE)
        s["mode_of_play"] = ra.read_u32(A.MODE_OF_PLAY)
        s["f_psel_init"] = ra.read_u32(A.F_PSEL_INIT)
        s["p1_state"] = ra.read_u32(A.P1_STATE)
        s["p2_state"] = ra.read_u32(A.P2_STATE)
        s["p1_char"] = ra.read_u32(A.P1_CHAR)
        s["p2_char"] = ra.read_u32(A.P2_CHAR)
        s["p1_pos"] = ra.read_u32(A.P1_POS)
        s["p2_pos"] = ra.read_u32(A.P2_POS)
        s["practice_p1"] = ra.read_u32(A.PRACTICE_P1_INDEX)
        s["pne_cursor"] = ra.read_u32(A.PNE_CURSOR)
        s["menu"] = self._active_menu()
        return s

    # ---- classify + narrate -------------------------------------------

    def _classify(self, s: dict) -> str:
        if s["f_psel_init"] or s["p1_state"] or s["p2_state"]:
            return Context.CHARSELECT
        if s["menu"] is not None:
            return Context.MENU
        return Context.IDLE

    def _menu_utterance(self, s: dict):
        m = s["menu"]
        if m is None:
            return None
        mdef, cur, n = m["menu_def"], m["cursor"], m["n"]
        name, fallback = A.MENU_STRUCTS.get(mdef, (None, []))
        label = ""
        if 0 <= cur < max(n, 1):
            try:
                label = read_cstring(self.ra, self.ra.read_u32(mdef + cur * A.MENU_ITEM_STRIDE), 32)
            except RetroArchError:
                pass
        if not label and 0 <= cur < len(fallback):
            label = fallback[cur]
        label = " ".join(label.split()).title() if label else f"item {cur + 1}"
        key = ("menu", mdef, cur, label)
        text = label
        if n:
            text += f", {cur + 1} of {n}"
        if self.announce_descriptions and mdef == A.MODE_SELECT_DEF and 0 <= cur < len(A.MODE_DESCRIPTIONS):
            text = A.MODE_DESCRIPTIONS[cur]
        return key, text, name or "Menu"

    def _charselect_utterance(self, s: dict):
        """Announce each active player's hovered fighter; when they lock a pick,
        say 'Player N chose X'."""
        parts, key_bits = [], ["cs"]
        players = ((1, s["p1_state"], s["p1_pos"], s["p1_char"]),
                   (2, s["p2_state"], s["p2_pos"], s["p2_char"]))
        for pnum, st, pos, chosen in players:
            if not st:
                continue
            locked = st >= 4 and chosen != A.CHAR_NONE
            if locked:
                parts.append(f"Player {pnum} chose {self._roster_name(chosen)}")
                key_bits.append((pnum, "locked", chosen))
            else:
                parts.append(f"Player {pnum}: {self._roster_name(pos)}")
                key_bits.append((pnum, "hover", pos))
        if not parts:
            return None
        return tuple(key_bits), " . ".join(parts), "Character select"

    def narrate(self, s: dict):
        ctx = self._classify(s)
        now = time.monotonic()

        if ctx != self._last_context:
            self._last_context = ctx
            if ctx == Context.CHARSELECT:
                self.say.say("Character select")
            elif ctx == Context.MENU and s["menu"] and s["menu"]["menu_def"] in A.MENU_STRUCTS:
                self.say.say(A.MENU_STRUCTS[s["menu"]["menu_def"]][0])
            self._last_spoken_key = None
            self._pending_key = None

        if ctx == Context.MENU:
            u = self._menu_utterance(s)
        elif ctx == Context.CHARSELECT:
            u = self._charselect_utterance(s)
        else:
            u = None

        if u is None:
            return
        key, text, _menu_name = u
        if key == self._last_spoken_key:
            return
        # settle: only speak once the selection has held briefly
        if key != self._pending_key:
            self._pending_key = key
            self._pending_since = now
            return
        if now - self._pending_since >= SETTLE_S:
            self.say.say(text)
            self._last_spoken_key = key
            self._pending_key = None

    # ---- loop --------------------------------------------------------

    def _is_target_game(self) -> bool:
        """True only when MK:DA (USA, GMKE5D) is actually running. The disc-ID
        read is filename/dump/OS independent; the status strings are a fast
        pre-filter."""
        try:
            st = self.ra.status()
        except RetroArchError:
            return False
        if st.get("state") != "PLAYING":
            return False
        sysname = (st.get("system") or "").lower()
        if sysname and "gc" not in sysname and "gamecube" not in sysname and "cube" not in sysname:
            return False
        try:
            disc_id = self.ra.read_memory(0x80000000, 6)
        except RetroArchError:
            return False
        if disc_id == b"GMKE5D":
            self._region_warned = getattr(self, "_region_warned", False)
            return True
        if disc_id in (b"GMKP5D", b"GMKD5D", b"GMKJ5D"):
            if not getattr(self, "_region_warned", False):
                print(f"note: this looks like a non-USA build ({disc_id.decode('latin1')}); "
                      "the RAM addresses are for the USA disc (GMKE5D) and may be wrong.",
                      flush=True)
                self._region_warned = True
            return True
        return False

    def run(self):
        period = 1.0 / POLL_HZ
        waiting_logged = False
        while True:
            try:
                if not self._is_target_game():
                    if not waiting_logged:
                        print("waiting for MK: Deadly Alliance to be running...", flush=True)
                        waiting_logged = True
                    time.sleep(1.5)
                    continue
                waiting_logged = False
                s = self.snapshot()
                self.narrate(s)
            except RetroArchError as e:
                print(f"(retro) {e}", flush=True)
                time.sleep(0.7)
            except KeyboardInterrupt:
                return
            time.sleep(period)


def _fmt(s: dict) -> str:
    m = s.get("menu")
    if m:
        nm = A.MENU_STRUCTS.get(m["menu_def"], (hex(m["menu_def"]),))[0]
        menu = f"{nm} id={m['menu_id']} cur={m['cursor']}/{m['n']}"
    else:
        menu = "-"
    return (f"menu_on={s['menu_on']} sp={s['menu_stack_ptr']} [{menu}] active_msel={s['active_msel_menu']} | "
            f"psel_init={s['f_psel_init']} p1s={s['p1_state']} p2s={s['p2_state']} "
            f"p1c={s['p1_char']} p2c={s['p2_char']} p1pos={s['p1_pos']} p2pos={s['p2_pos']} "
            f"| gs={s['game_state']} mop={s['mode_of_play']} prac_p1={s['practice_p1']} pne={s['pne_cursor']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="dump raw state ~4x/s, no speech")
    ap.add_argument("--once", action="store_true", help="one snapshot then exit")
    ap.add_argument("--descriptions", action="store_true",
                    help="speak the long mode descriptions instead of just the name")
    ap.add_argument("--host", default=os.environ.get("MKDA_RA_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MKDA_RA_PORT", "55355")))
    args = ap.parse_args()

    ra = RAClient(cmd_host=args.host, cmd_port=args.port)

    if args.once or args.probe:
        try:
            print("RetroArch:", ra.version(), ra.status(), flush=True)
        except RetroArchError as e:
            print(f"cannot reach RetroArch on {args.host}:{args.port}: {e}", file=sys.stderr)
            print("is the game running, and is network_cmd_enable set to true?", file=sys.stderr)
            sys.exit(1)
        mr = MenuReader(ra)
        while True:
            try:
                print(_fmt(mr.snapshot()), flush=True)
            except RetroArchError as e:
                print(f"(retro) {e}", flush=True)
            if args.once:
                return
            time.sleep(0.25)

    print(f"mkda talking-menu daemon: watching RetroArch on {args.host}:{args.port}", flush=True)
    MenuReader(ra, announce_descriptions=args.descriptions).run()


if __name__ == "__main__":
    main()
