#!/usr/bin/env python3
"""MK: Deadly Alliance (GameCube) talking-menu daemon.  Windows / macOS / Linux.

Polls the running game's RAM through RetroArch's UDP command interface and speaks
the highlighted menu item / hovered fighter as the player navigates. Speech goes
through whatever TTS the OS has (see speak.py). Nothing here writes to the game.

    python menu_reader.py             # run the daemon (waits for the game, then narrates)
    python menu_reader.py --probe     # print the raw state snapshot ~4x/s, no speech
    python menu_reader.py --once      # one snapshot, exit
    python menu_reader.py --descriptions   # speak the long mode blurbs

Env: MK_RA_HOST (default 127.0.0.1), MK_RA_PORT (default 55355),
     MK_VOICE, MK_RATE_WPM, MK_SPEAK_BACKEND  (see speak.py).

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

POLL_HZ = 20
SETTLE_S = 0.06           # wait for the cursor to stop before announcing
TARGET_RECHECK_S = 2.0    # how often to re-verify MK:DA is still the running game

# RetroArch's network command interface processes ~1 command per emulated frame
# (~16.7 ms), and READ_CORE_MEMORY replies are capped near 1 KB — so a poll must
# read in a few big blocks, not ~15 point reads. This block covers every .sdata
# /.sbss variable the hot path needs (0x8041bc90 MENU_ON .. 0x8041bf8c P1_POS).
VARS_BASE = 0x8041BC00
VARS_LEN = 960


_KEEP_CAPS = {"MK", "CPU", "TV", "AI"}


def prettify(label: str) -> str:
    """MK:DA menu labels are ALL-CAPS; title-case them for TTS but keep real
    acronyms ('MK HISTORY' -> 'MK History', not 'Mk History' which reads 'Mick')."""
    out = []
    for w in " ".join(label.split()).split(" "):
        out.append(w if w.upper() in _KEEP_CAPS else w.capitalize())
    return " ".join(out)


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
        self._ctx_candidate = None
        self._ctx_streak = 0
        self._roster_cache: dict[int, str] = {}
        self._menu_count_cache: dict[int, int] = {}     # menu_def -> item count (static)
        self._label_cache: dict[tuple, str] = {}        # (menu_def, cursor) -> label (static)
        self._target_ok = False
        self._target_checked = 0.0

    # ---- reading helpers --------------------------------------------------

    def _menu_item_count(self, menu_def: int) -> int:
        n = self._menu_count_cache.get(menu_def)
        if n is None:
            n = 0
            try:
                blob = self.ra.read_memory(menu_def, 24 * A.MENU_ITEM_STRIDE)
                for i in range(24):
                    lp = int.from_bytes(blob[i * A.MENU_ITEM_STRIDE:i * A.MENU_ITEM_STRIDE + 4], "big")
                    if not (0x80200000 <= lp < 0x80300000):
                        break
                    n += 1
            except RetroArchError:
                return 0
            self._menu_count_cache[menu_def] = n
        return n

    def _menu_label(self, menu_def: int, cursor: int) -> str:
        key = (menu_def, cursor)
        lbl = self._label_cache.get(key)
        if lbl is None:
            try:
                lp = self.ra.read_u32(menu_def + cursor * A.MENU_ITEM_STRIDE)
                lbl = read_cstring(self.ra, lp, 32)
            except RetroArchError:
                return ""
            self._label_cache[key] = lbl
        return lbl

    def _active_menu(self, menu_on: int, sp: int) -> dict | None:
        """menu_id from the nav stack -> record in main_menu_tbl -> menu_def + cursor.
        Two range reads; item count + label strings are cached (they never change)."""
        if not menu_on or sp < 1:
            return None
        try:
            stack = self.ra.read_memory(A.MENU_STACK, 40)
            tbl = self.ra.read_memory(A.MAIN_MENU_TBL, 5 * A.MENU_REC_STRIDE)
        except RetroArchError:
            return None
        i = sp - 1
        menu_id = int.from_bytes(stack[i * 4:i * 4 + 4], "big")
        if menu_id > 4:
            return None
        rec = menu_id * A.MENU_REC_STRIDE
        menu_def = int.from_bytes(tbl[rec:rec + 4], "big")
        cursor = int.from_bytes(tbl[rec + A.MENU_CURSOR_OFF:rec + A.MENU_CURSOR_OFF + 4], "big")
        if not (0x80200000 <= menu_def < 0x80300000):
            return None
        return {"menu_id": menu_id, "menu_def": menu_def, "cursor": cursor,
                "n": self._menu_item_count(menu_def)}

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

    def snapshot(self, full: bool = False) -> dict:
        """One 960-byte block read for all the hot .sdata vars, then up to two
        more reads to resolve the active menu. ~3 UDP round-trips (~50 ms) vs the
        ~15 (~250 ms) of a naive point-read snapshot. `full=True` adds the extra
        point reads used only by --probe."""
        ra = self.ra
        vb = ra.read_memory(VARS_BASE, VARS_LEN)

        def u(addr: int) -> int:
            o = addr - VARS_BASE
            return int.from_bytes(vb[o:o + 4], "big")

        s = {
            "menu_on": u(A.MENU_ON),
            "menu_stack_ptr": u(A.MENU_STACK_PTR),
            "game_state": u(A.GAME_STATE),
            "mode_of_play": u(A.MODE_OF_PLAY),
            "f_psel_init": u(A.F_PSEL_INIT),
            "p1_state": u(A.P1_STATE),
            "p2_state": u(A.P2_STATE),
            "p1_pos": u(A.P1_POS),
            "p2_pos": u(A.P2_POS),
            "practice_p1": u(A.PRACTICE_P1_INDEX),
            "p1_char": None,     # read lazily in _charselect_utterance (locked pick only)
            "p2_char": None,
        }
        s["menu"] = self._active_menu(s["menu_on"], s["menu_stack_ptr"])
        if full:
            s["active_msel_menu"] = ra.read_u32(A.ACTIVE_MSEL_MENU)
            s["pne_cursor"] = ra.read_u32(A.PNE_CURSOR)
            s["p1_char"] = ra.read_u32(A.P1_CHAR)
            s["p2_char"] = ra.read_u32(A.P2_CHAR)
        return s

    # ---- classify + narrate -------------------------------------------

    # game_state values seen on the title / attract screens, where there is no
    # interactive menu (verified live: gs=1 title & attract idle, gs=20 title).
    # The real main menu + submenus are gs=11; a real in-match pause menu is gs=5.
    _NON_MENU_STATES = (1, 20)

    def _classify(self, s: dict) -> str:
        if s["f_psel_init"] or s["p1_state"] or s["p2_state"]:
            return Context.CHARSELECT
        if s["menu"] is not None and s["game_state"] not in self._NON_MENU_STATES:
            return Context.MENU
        return Context.IDLE

    def _menu_utterance(self, s: dict):
        m = s["menu"]
        if m is None:
            return None
        mdef, cur, n = m["menu_def"], m["cursor"], m["n"]
        name, fallback = A.MENU_STRUCTS.get(mdef, (None, []))
        label = self._menu_label(mdef, cur) if 0 <= cur < max(n, 1) else ""
        if not label and 0 <= cur < len(fallback):
            label = fallback[cur]
        label = prettify(label) if label else f"item {cur + 1}"
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
        for pnum, st, pos, char_addr in ((1, s["p1_state"], s["p1_pos"], A.P1_CHAR),
                                         (2, s["p2_state"], s["p2_pos"], A.P2_CHAR)):
            if not st:
                continue
            chosen = A.CHAR_NONE
            if st >= 4:                       # locked in — one extra read, rare
                try:
                    chosen = self.ra.read_u32(char_addr)
                except RetroArchError:
                    pass
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
        raw_ctx = self._classify(s)
        now = time.monotonic()

        # debounce the context itself: a new non-idle context must hold for two
        # polls before we act on it, so a single transient frame (a screen
        # transition, a stale read) can't trigger a spurious announcement.
        if raw_ctx == self._ctx_candidate:
            self._ctx_streak += 1
        else:
            self._ctx_candidate = raw_ctx
            self._ctx_streak = 1
        if raw_ctx == Context.IDLE or self._ctx_streak >= 2:
            ctx = raw_ctx
        else:
            return

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

    def _target_ready(self) -> bool:
        """_is_target_game() with a short TTL — it costs 2 UDP reads and the answer
        rarely changes, so don't pay for it every poll."""
        now = time.monotonic()
        if now - self._target_checked >= TARGET_RECHECK_S:
            self._target_ok = self._is_target_game()
            self._target_checked = now
        return self._target_ok

    def run(self):
        period = 1.0 / POLL_HZ
        waiting_logged = False
        while True:
            try:
                if not self._target_ready():
                    if not waiting_logged:
                        print("waiting for MK: Deadly Alliance to be running...", flush=True)
                        waiting_logged = True
                    time.sleep(1.0)
                    continue
                waiting_logged = False
                self.narrate(self.snapshot())
            except RetroArchError as e:
                print(f"(retro) {e}", flush=True)
                self._target_checked = 0.0        # force a re-verify next loop
                time.sleep(0.5)
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
    return (f"menu_on={s['menu_on']} sp={s['menu_stack_ptr']} [{menu}] "
            f"active_msel={s.get('active_msel_menu')} | "
            f"psel_init={s['f_psel_init']} p1s={s['p1_state']} p2s={s['p2_state']} "
            f"p1c={s.get('p1_char')} p2c={s.get('p2_char')} p1pos={s['p1_pos']} p2pos={s['p2_pos']} "
            f"| gs={s['game_state']} mop={s['mode_of_play']} prac_p1={s['practice_p1']} pne={s.get('pne_cursor')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="dump raw state ~4x/s, no speech")
    ap.add_argument("--once", action="store_true", help="one snapshot then exit")
    ap.add_argument("--descriptions", action="store_true",
                    help="speak the long mode descriptions instead of just the name")
    ap.add_argument("--host", default=os.environ.get("MK_RA_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MK_RA_PORT", "55355")))
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
                print(_fmt(mr.snapshot(full=True)), flush=True)
            except RetroArchError as e:
                print(f"(retro) {e}", flush=True)
            if args.once:
                return
            time.sleep(0.25)

    print(f"mkda talking-menu daemon: watching RetroArch on {args.host}:{args.port}", flush=True)
    MenuReader(ra, announce_descriptions=args.descriptions).run()


if __name__ == "__main__":
    main()
