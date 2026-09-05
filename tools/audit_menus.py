#!/usr/bin/env python3
"""Audit the MK:DA talking-menu daemon across every menu screen.

Measures, per screen:
  * MenuReader.snapshot() wall time (min / median / max over N samples)
  * READ_CORE_MEMORY round-trips per poll (snapshot + one narrate pass)
  * injected-keypress -> spoken-utterance latency (min / median / max over N trials)
  * correctness: spoken label vs OCR of the same screen; "item N" fallbacks;
    wrong "N of M" counts; silent / wrong-context screens
  * edge cases: holding Down (machine-gun vs settle), wrapping past the last item,
    the once-only context announcement on screen entry

It drives the game with RetroArch's network-remote (UDP 55400), so it needs, in
retroarch.cfg (with RetroArch closed):
    network_remote_enable          = "true"
    network_remote_enable_user_p1  = "true"
Turn both back to "false" and restart RetroArch when finished (see
docs/BUG-menu-selection.md — a stuck remote button is a known hazard).

It imports the daemon under test from the repo (the sys.path shim below), so it
measures whatever menu_reader.py / ra_client.py currently are — run it before and
after the snapshot rewrite to compare. Override with MK_DAEMON_DIR=<path> to point
at the deployed copy instead.

    python3 tools/audit_menus.py                 # full run, prints the table
    python3 tools/audit_menus.py --screens main,options
    python3 tools/audit_menus.py --trials 15 --samples 15
    python3 tools/audit_menus.py --no-ocr        # skip the OCR cross-check
    python3 tools/audit_menus.py --md            # emit a Markdown table

Safe to re-run. It always tries to leave the game on the main menu with no
buttons held.
"""

from __future__ import annotations

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

_daemon_dir = _os.environ.get("MK_DAEMON_DIR")
if _daemon_dir:
    _sys.path.insert(0, _daemon_dir)

import argparse
import statistics
import threading
import time

os_environ = _os.environ
os_environ.setdefault("MK_SPEAK_BACKEND", "log")   # never actually speak during the audit

from ra_client import RAClient, RetroArchError, BTN
import mkda_addrs as A
import menu_reader as MR
from menu_reader import MenuReader, Context

try:
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _sys.path.insert(0, _here)
    from see import see as _see
except Exception:
    _see = None


# ---------------------------------------------------------------------------
# instrumentation helpers
# ---------------------------------------------------------------------------

class CountingRA(RAClient):
    """RAClient that counts READ_CORE_MEMORY round-trips."""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.reads = 0

    def read_memory(self, addr, length):
        self.reads += 1
        return super().read_memory(addr, length)


class RecSpeaker:
    """Stand-in Speaker that timestamps every utterance instead of speaking."""
    def __init__(self):
        self.events = []            # list[(monotonic_ts, text)]
        self._lock = threading.Lock()

    def say(self, text, interrupt=True):
        text = " ".join((text or "").split())
        if not text:
            return
        with self._lock:
            self.events.append((time.monotonic(), text))

    def wait(self):
        pass

    def snapshot_events(self):
        with self._lock:
            return list(self.events)

    def clear(self):
        with self._lock:
            self.events.clear()


class Poller:
    """Runs the real MenuReader narrate() loop on a thread at the daemon's POLL_HZ.

    Has its OWN RAClient so it never shares a socket with the main thread's
    measurements. Can be paused so a direct snapshot()/reads-per-poll measurement
    runs with nothing else on the wire."""
    def __init__(self, speaker, host, port):
        self.ra = RAClient(cmd_host=host, cmd_port=port)
        self.mr = MenuReader(self.ra, speaker=speaker)
        self.speaker = speaker
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._idle = threading.Event()      # set while the loop is parked in pause
        self._thr = None
        self.last_snapshot_ms = None
        self.poll_count = 0

    def start(self):
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=3)

    def pause(self):
        self._pause.set()
        self._idle.wait(timeout=3)          # wait until the loop is actually parked

    def resume(self):
        self._pause.clear()
        self._idle.clear()

    def _run(self):
        period = 1.0 / MR.POLL_HZ
        while not self._stop.is_set():
            if self._pause.is_set():
                self._idle.set()
                self._stop.wait(0.05)
                continue
            t0 = time.monotonic()
            try:
                s = self.mr.snapshot()
                self.last_snapshot_ms = (time.monotonic() - t0) * 1000.0
                self.mr.narrate(s)
                self.poll_count += 1
            except RetroArchError:
                pass
            self._stop.wait(period)


# ---------------------------------------------------------------------------
# input: account for an A/B swap remap on dolphin-emu
# ---------------------------------------------------------------------------

def detect_button_polarity(ra, log):
    """A dolphin-emu core/game remap may swap RetroPad A(8) <-> B(0) (see
    docs/BUG-confirm-button.md). Figure out which id we must send for
    confirm / back by reading the remap files, then (if on a menu) verifying live."""
    confirm_id, back_id = BTN["a"], BTN["b"]          # default: A confirms, B backs
    remap_dirs = _os.path.expanduser(
        "~/Library/Application Support/RetroArch/config/remaps/dolphin-emu")
    swapped = False
    if _os.path.isdir(remap_dirs):
        for fn in _os.listdir(remap_dirs):
            if not fn.endswith(".rmp"):
                continue
            try:
                txt = open(_os.path.join(remap_dirs, fn)).read()
            except OSError:
                continue
            a = _rmp_val(txt, "input_player1_btn_a")
            b = _rmp_val(txt, "input_player1_btn_b")
            if a == "0" and b == "8":
                swapped = True
                log(f"  remap {fn}: A/B swapped (btn_a=0 btn_b=8)")
    if swapped:
        confirm_id, back_id = BTN["b"], BTN["a"]
    log(f"  using confirm id={confirm_id} back id={back_id} "
        f"(swap {'ON' if swapped else 'off'})")
    return confirm_id, back_id


def verify_polarity(ra, pad, log):
    """Live sanity check: from the main menu, tap 'confirm' on ARCADE. If we end up
    in a submenu / character-select, polarity is right. If the menu closed (we went
    back to attract), the remap does the opposite of what we assumed -> flip."""
    if not goto_main(ra, pad, log):
        log("  polarity check skipped (no main menu)")
        return
    pad.up(); pad.up(); time.sleep(0.3)
    before = active_menu_raw(ra)
    pad.confirm(); time.sleep(2.5)
    s = read_state(ra)
    after = active_menu_raw(ra)
    advanced = bool(s["f_psel"] or s["p1_state"]
                    or (after and before and after["menu_def"] != before["menu_def"])
                    or (after and after["menu_id"] != (before["menu_id"] if before else -1)))
    closed = (not s["menu_on"]) and (not s["f_psel"]) and (not s["p1_state"])
    if closed and not advanced:
        pad.confirm_id, pad.back_id = pad.back_id, pad.confirm_id
        log(f"  polarity FLIPPED -> confirm id={pad.confirm_id} back id={pad.back_id}")
    else:
        log(f"  polarity OK (advanced={advanced} closed={closed})")
    # return to main menu regardless
    for _ in range(4):
        pad.back(after=0.4)
    goto_main(ra, pad, log)


def _rmp_val(txt, key):
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith(key):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"')
    return None


class Pad:
    """Send RetroPad ids (already polarity-corrected) via network-remote."""
    def __init__(self, ra, confirm_id, back_id):
        self.ra = ra
        self.confirm_id = confirm_id
        self.back_id = back_id

    def _send(self, id_, state):
        self.ra._remote_send(id_, state)

    def tap_id(self, id_, hold=0.10, after=0.12):
        self._send(id_, 1)
        time.sleep(hold)
        self._send(id_, 0)
        time.sleep(after)

    def down(self, **kw):   self.tap_id(BTN["down"], **kw)
    def up(self, **kw):     self.tap_id(BTN["up"], **kw)
    def left(self, **kw):   self.tap_id(BTN["left"], **kw)
    def right(self, **kw):  self.tap_id(BTN["right"], **kw)
    def confirm(self, **kw): self.tap_id(self.confirm_id, **kw)
    def back(self, **kw):    self.tap_id(self.back_id, **kw)
    def start(self, **kw):  self.tap_id(BTN["start"], **kw)

    def press_down_edge(self):
        """Send only the button-down edge; caller releases. Returns the monotonic
        instant the down packet was sent."""
        t = time.monotonic()
        self._send(BTN["down"], 1)
        return t

    def release(self, id_=None):
        self._send(BTN["down"] if id_ is None else id_, 0)

    def release_all(self):
        for i in BTN.values():
            self._send(i, 0)
        time.sleep(0.05)


# ---------------------------------------------------------------------------
# screen model
# ---------------------------------------------------------------------------

# menu_def struct pointers -> (screen key, expected item labels from OCR / tables)
SCREENS = {
    "main":    dict(menu_def=A.MODE_SELECT_DEF, enter=None,
                    labels=["Arcade", "Versus", "Practice", "Konquest",
                            "The Krypt", "Player Profile", "Options", "Kontent"]),
    "options": dict(menu_def=0x802301ac, enter=("main", 6),
                    labels=["Game Options", "Sound Options",
                            "Controller Setup", "Screen Adjust"]),
    "kontent": dict(menu_def=0x802301e8, enter=("main", 7),
                    labels=["Unlocked", "Endings", "Development", "Prizes",
                            "Products", "Making Of Mk", "Mk History", "Adema"]),
    "pause":   dict(menu_def=0x802300e0, enter="match",
                    labels=["Continue", "Movelist / Profile",
                            "Player Select", "Main Menu"]),
    "css":     dict(menu_def=None, enter="css",
                    labels=None),
}


def norm(s):
    return " ".join((s or "").split()).upper().replace("/", " ").strip()


# ---------------------------------------------------------------------------
# navigation
# ---------------------------------------------------------------------------

def goto_main(ra, pad, log, tries=30):
    """Reach the interactive main menu. Uses OCR classify when available."""
    try:
        from nav import classify
    except Exception:
        classify = None
    for i in range(tries):
        try:
            s = read_state(ra)
        except RetroArchError:
            time.sleep(0.5); continue
        m = active_menu_raw(ra)
        if m and m["menu_def"] == A.MODE_SELECT_DEF and s["game_state"] not in MR.MenuReader._NON_MENU_STATES:
            log(f"  at main menu (gs={s['game_state']}) after {i} steps")
            pad.up(); pad.up()                      # cursor to the top
            time.sleep(0.4)
            return True
        lines = _see(ra) if _see else []
        st = classify(lines) if classify else "?"
        log(f"  [{i}] gs={s['game_state']} menu_on={s['menu_on']} cls={st} ocr={' | '.join(lines)[:70]}")
        if st == "char-select":
            pad.back(); time.sleep(1.2)
        elif st == "quit-dialog":
            pad.confirm(); time.sleep(3.0)
        elif st == "pause":
            for _ in range(4):
                pad.down(after=0.3)
            pad.confirm(); time.sleep(1.5)
        elif st in ("in-match", "match-end"):
            pad.start(); time.sleep(1.5)
        elif st == "title":
            pad.start(); time.sleep(2.5)
        else:
            pad.back(); time.sleep(1.0)
            pad.start(); time.sleep(1.5)
    log("  !! could not reach the main menu")
    return False


def read_state(ra):
    return dict(
        menu_on=ra.read_u32(A.MENU_ON),
        game_state=ra.read_u32(A.GAME_STATE),
        f_psel=ra.read_u32(A.F_PSEL_INIT),
        p1_state=ra.read_u32(A.P1_STATE),
    )


def active_menu_raw(ra):
    """Same resolution the daemon uses, without any settle / debounce."""
    try:
        if not ra.read_u32(A.MENU_ON):
            return None
        sp = ra.read_u32(A.MENU_STACK_PTR)
        if sp < 1:
            return None
        menu_id = ra.read_u32(A.MENU_STACK + (sp - 1) * 4)
        if menu_id > 8:
            return None
        rec = A.MAIN_MENU_TBL + menu_id * A.MENU_REC_STRIDE
        menu_def = ra.read_u32(rec)
        cursor = ra.read_u32(rec + A.MENU_CURSOR_OFF)
    except RetroArchError:
        return None
    if not (0x80200000 <= menu_def < 0x80300000):
        return None
    n = 0
    while n < 24:
        try:
            lp = ra.read_u32(menu_def + n * A.MENU_ITEM_STRIDE)
        except RetroArchError:
            break
        if not (0x80200000 <= lp < 0x80300000):
            break
        n += 1
    return dict(menu_id=menu_id, menu_def=menu_def, cursor=cursor, n=n)


def enter_submenu(ra, pad, log, child_key, index):
    want = SCREENS[child_key]["menu_def"]
    for attempt in range(2):
        if not goto_main(ra, pad, log):
            return False
        for _ in range(index):
            pad.down(after=0.28)
        time.sleep(0.3)
        pad.confirm()
        time.sleep(1.6)
        m = active_menu_raw(ra)
        got = m["menu_def"] if m else None
        log(f"  enter {child_key} (idx {index}) attempt {attempt}: "
            f"menu={_hx(got)} want={_hx(want)} cursor={m['cursor'] if m else '?'}")
        if got == want:
            return True
        # maybe confirm acted as back; flip polarity once and retry
        pad.confirm_id, pad.back_id = pad.back_id, pad.confirm_id
        log("  (flipped polarity, retrying)")
    return m is not None and m["menu_def"] == want


def _hx(v):
    return hex(v) if isinstance(v, int) else str(v)


def start_match(ra, pad, log):
    """Arcade -> character select -> pick P1 -> into a match. Best-effort."""
    if not goto_main(ra, pad, log):
        return False
    pad.up(); pad.up(); time.sleep(0.3)
    pad.confirm(); time.sleep(3.0)           # ARCADE
    # wait for CSS
    for _ in range(8):
        s = read_state(ra)
        if s["f_psel"] or s["p1_state"]:
            break
        pad.confirm(); time.sleep(1.5)
    else:
        log("  !! never reached character select"); return False
    log("  at character select")
    # lock a fighter: confirm a few times (char, style1, style2, weapon)
    for _ in range(6):
        pad.confirm(after=0.6)
    time.sleep(4.0)                          # stage load
    # confirm we're in a match / at pause
    for _ in range(6):
        lines = _see(ra) if _see else []
        up = " ".join(lines).upper()
        if any(k in up for k in ("DIFFICULTY:", "ROUND", "FIGHT")):
            log("  in match"); return True
        s = read_state(ra)
        if s["game_state"] not in MR.MenuReader._NON_MENU_STATES and not s["menu_on"] and not s["f_psel"]:
            log(f"  looks in-match (gs={s['game_state']})"); return True
        time.sleep(1.0)
    log("  ? match state unclear, continuing anyway")
    return True


def goto_css(ra, pad, log):
    if not goto_main(ra, pad, log):
        return False
    pad.up(); pad.up(); time.sleep(0.3)
    pad.confirm(); time.sleep(3.0)
    for _ in range(8):
        s = read_state(ra)
        if s["f_psel"] or s["p1_state"]:
            log("  at character select"); return True
        pad.confirm(); time.sleep(1.5)
    return False


# ---------------------------------------------------------------------------
# measurements
# ---------------------------------------------------------------------------

def measure_snapshot_ms(mr, samples):
    xs = []
    for _ in range(samples):
        t0 = time.monotonic()
        try:
            mr.snapshot()
        except RetroArchError:
            continue
        xs.append((time.monotonic() - t0) * 1000.0)
        time.sleep(0.05)
    return xs


def measure_reads_per_poll(ra_counter, mr):
    ra_counter.reads = 0
    try:
        s = mr.snapshot()
        mr.narrate(s)
    except RetroArchError:
        pass
    return ra_counter.reads


def measure_keypress_latency(ra, pad, poller, trials, log, hold=0.10):
    """Press Down; measure ms from the down-edge packet to the next new SPEAK event."""
    lat = []
    misses = 0
    for t in range(trials):
        poller.speaker.clear()
        # make sure the poller has a fresh 'last spoken' baseline
        time.sleep(0.35)
        base = len(poller.speaker.snapshot_events())
        t0 = pad.press_down_edge()
        time.sleep(hold)
        pad.release()
        deadline = t0 + 6.0
        got = None
        while time.monotonic() < deadline:
            evs = poller.speaker.snapshot_events()
            if len(evs) > base:
                got = evs[base][0]
                break
            time.sleep(0.005)
        if got is None:
            misses += 1
            log(f"    trial {t}: no utterance within 6s")
        else:
            dt = (got - t0) * 1000.0
            lat.append(dt)
            log(f"    trial {t}: {dt:.0f} ms  -> {poller.speaker.snapshot_events()[base][1]!r}")
        time.sleep(0.5)
    return lat, misses


def check_correctness(ra, pad, mr, screen_key, log, do_ocr=True):
    """Walk every item; compare the daemon's utterance to OCR + expectations."""
    issues = []
    spec = SCREENS[screen_key]
    m = active_menu_raw(ra)
    if not m:
        return ["screen not resolvable as a menu"]
    n = m["n"]
    expected = spec["labels"]
    if expected and n != len(expected):
        issues.append(f"item count {n}, expected {len(expected)}")
    # walk to the top first
    for _ in range(n + 2):
        pad.up(after=0.18)
    time.sleep(0.3)
    for i in range(n):
        m = active_menu_raw(ra)
        if not m:
            issues.append(f"item {i}: menu vanished mid-walk"); break
        cur = m["cursor"]
        u = mr._menu_utterance(dict(menu=m))
        spoken = u[1] if u else "(none)"
        label_only = spoken.split(",")[0].strip()
        ocr_txt = ""
        if do_ocr and _see:
            ocr_lines = _see(ra)
            ocr_txt = " | ".join(ocr_lines)
        hit = norm(label_only) in norm(ocr_txt) if ocr_txt else None
        exp = expected[i] if (expected and i < len(expected)) else None
        exp_ok = (norm(label_only) == norm(exp)) if exp else None
        flag = ""
        if label_only.lower().startswith("item "):
            issues.append(f"cursor {cur}: fallback '{label_only}'"); flag = " <FALLBACK>"
        if exp_ok is False:
            issues.append(f"cursor {cur}: spoke {label_only!r}, expected {exp!r}"); flag += " <MISMATCH>"
        if hit is False:
            issues.append(f"cursor {cur}: {label_only!r} not in OCR {ocr_txt[:60]!r}"); flag += " <NO-OCR-MATCH>"
        if u and f", {cur + 1} of {n}" not in u[1] and u[1] != f"item {cur+1}":
            issues.append(f"cursor {cur}: missing/na 'N of M' in {u[1]!r}")
        log(f"    [{i}] cur={cur} spoke={spoken!r} ocr~={ocr_txt[:50]!r}{flag}")
        pad.down(after=0.22)
    return issues


def check_edges(ra, pad, poller, screen_key, log):
    out = {}
    # --- hold Down for 1.5 s: machine-gun vs settle ---
    poller.speaker.clear()
    base = len(poller.speaker.snapshot_events())
    pad._send(BTN["down"], 1)
    time.sleep(1.5)
    pad._send(BTN["down"], 0)
    time.sleep(1.0)
    n_utt = len(poller.speaker.snapshot_events()) - base
    out["hold_down_utterances_1.5s"] = n_utt
    log(f"    hold Down 1.5s -> {n_utt} utterances "
        f"({[e[1] for e in poller.speaker.snapshot_events()[base:]]})")
    # --- wrap past the last item ---
    m = active_menu_raw(ra)
    if m:
        n = m["n"]
        for _ in range(n + 2):
            pad.up(after=0.18)
        time.sleep(0.3)
        for _ in range(n - 1):
            pad.down(after=0.22)
        time.sleep(0.3)
        before = active_menu_raw(ra)
        poller.speaker.clear()
        base = len(poller.speaker.snapshot_events())
        pad.down(after=0.4)
        time.sleep(1.5)
        after = active_menu_raw(ra)
        evs = [e[1] for e in poller.speaker.snapshot_events()[base:]]
        out["wrap"] = dict(from_cursor=before["cursor"] if before else None,
                           to_cursor=after["cursor"] if after else None,
                           spoke=evs)
        log(f"    wrap: cursor {before['cursor'] if before else '?'} -> "
            f"{after['cursor'] if after else '?'}  spoke={evs}")
    return out


def check_context_entry(ra, pad, poller, screen_key, log):
    """Leave the screen and re-enter; count how many times the context/name is announced."""
    spec = SCREENS[screen_key]
    name = None
    md = spec["menu_def"]
    if md in A.MENU_STRUCTS:
        name = A.MENU_STRUCTS[md][0]
    poller.speaker.clear()
    # leave
    if screen_key == "main":
        # dip into Options and back
        for _ in range(6):
            pad.down(after=0.22)
        pad.confirm(); time.sleep(1.2)
        base = len(poller.speaker.snapshot_events())
        pad.back(); time.sleep(2.0)
    else:
        pad.back(); time.sleep(1.5)
        base = len(poller.speaker.snapshot_events())
        parent, idx = spec["enter"]
        for _ in range(idx):
            pad.down(after=0.22)
        pad.confirm(); time.sleep(2.0)
    evs = [e[1] for e in poller.speaker.snapshot_events()[base:]]
    ctx_hits = sum(1 for e in evs if name and norm(name) in norm(e))
    log(f"    re-enter {screen_key}: announcements={evs}  (context-name x{ctx_hits})")
    return dict(events=evs, context_name_count=ctx_hits)


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def run_screen(key, ra, ra_counter, pad, poller, args, log):
    log(f"\n=== screen: {key} ===")
    spec = SCREENS[key]

    # -- navigate --
    if key == "main":
        if not goto_main(ra, pad, log):
            return dict(screen=key, error="could not reach main menu")
    elif key in ("options", "kontent"):
        parent, idx = spec["enter"]
        if not enter_submenu(ra, pad, log, key, idx):
            return dict(screen=key, error="could not enter submenu")
    elif key == "pause":
        if not start_match(ra, pad, log):
            return dict(screen=key, error="could not start a match")
        pad.start(); time.sleep(1.5)          # open pause menu
        m = active_menu_raw(ra)
        if not m or m["menu_def"] != spec["menu_def"]:
            log(f"  pause menu not resolved (got {_hx(m['menu_def']) if m else None})")
    elif key == "css":
        if not goto_css(ra, pad, log):
            return dict(screen=key, error="could not reach character select")

    time.sleep(0.5)
    res = dict(screen=key)
    # main-thread MenuReader (its own counting client) for every direct
    # snapshot()/_menu_utterance() call, so we never share the poller's socket
    probe_mr = MenuReader(ra_counter, speaker=RecSpeaker())

    # -- snapshot ms + reads/poll: pause the poller so only we are on the wire --
    poller.pause()
    try:
        snm = measure_snapshot_ms(probe_mr, args.samples)
        if snm:
            res["snapshot_ms"] = dict(min=round(min(snm)), med=round(statistics.median(snm)),
                                      max=round(max(snm)), n=len(snm))
        res["reads_per_poll"] = measure_reads_per_poll(ra_counter, probe_mr)
    finally:
        poller.resume()

    # -- keypress latency (menus only; CSS uses left/right not down) --
    if key != "css":
        lat, misses = measure_keypress_latency(ra, pad, poller, args.trials, log)
    else:
        lat, misses = _css_latency(ra, pad, poller, args.trials, log)
    if lat:
        res["latency_ms"] = dict(min=round(min(lat)), med=round(statistics.median(lat)),
                                 max=round(max(lat)), n=len(lat), misses=misses)
    else:
        res["latency_ms"] = dict(misses=misses, note="no utterances captured")

    # -- correctness -- (poller paused: we call _menu_utterance directly here)
    poller.pause()
    try:
        if key == "css":
            res["correctness"] = check_css_correctness(ra, pad, probe_mr, log, args.ocr)
        else:
            res["correctness"] = check_correctness(ra, pad, probe_mr, key, log, args.ocr)
    finally:
        poller.resume()

    # -- edges --
    if key != "css":
        res["edges"] = check_edges(ra, pad, poller, key, log)
        try:
            res["context_entry"] = check_context_entry(ra, pad, poller, key, log)
        except Exception as e:
            res["context_entry"] = dict(error=repr(e))

    pad.release_all()
    return res


def _css_latency(ra, pad, poller, trials, log):
    lat, misses = [], 0
    for t in range(trials):
        poller.speaker.clear()
        time.sleep(0.35)
        base = len(poller.speaker.snapshot_events())
        t0 = time.monotonic()
        pad._send(BTN["right"], 1); time.sleep(0.10); pad._send(BTN["right"], 0)
        deadline = t0 + 6.0
        got = None
        while time.monotonic() < deadline:
            evs = poller.speaker.snapshot_events()
            if len(evs) > base:
                got = evs[base][0]; break
            time.sleep(0.005)
        if got is None:
            misses += 1
        else:
            lat.append((got - t0) * 1000.0)
            log(f"    css trial {t}: {(got-t0)*1000:.0f} ms -> {poller.speaker.snapshot_events()[base][1]!r}")
        time.sleep(0.5)
    return lat, misses


def check_css_correctness(ra, pad, mr, log, do_ocr=True):
    issues = []
    seen = []
    for i in range(24):
        try:
            pos = ra.read_u32(A.P1_POS)
        except RetroArchError:
            break
        u = mr._charselect_utterance(dict(p1_state=ra.read_u32(A.P1_STATE),
                                          p2_state=ra.read_u32(A.P2_STATE),
                                          p1_pos=pos, p2_pos=ra.read_u32(A.P2_POS),
                                          p1_char=ra.read_u32(A.P1_CHAR),
                                          p2_char=ra.read_u32(A.P2_CHAR)))
        spoken = u[1] if u else "(none)"
        ocr_txt = ""
        if do_ocr and _see:
            ocr_txt = " | ".join(_see(ra))
        name = spoken.split(":")[-1].strip() if ":" in spoken else spoken
        ok = norm(name) in norm(ocr_txt) if ocr_txt else None
        if ok is False:
            issues.append(f"pos {pos}: spoke {name!r} not in OCR {ocr_txt[:60]!r}")
        log(f"    css [{i}] p1_pos={pos} spoke={spoken!r} ocr~={ocr_txt[:50]!r}")
        seen.append((pos, name))
        pad.right(after=0.4)
    return issues or ["ok"]


# ---------------------------------------------------------------------------

def fmt_table(results, md=False):
    cols = ["screen", "snapshot ms (min/med/max)", "keypress->speech ms (med/max)",
            "reads/poll", "correctness issues"]
    rows = []
    for r in results:
        if r.get("error"):
            rows.append([r["screen"], "-", "-", "-", f"NAV FAIL: {r['error']}"])
            continue
        sm = r.get("snapshot_ms", {})
        sm_s = f"{sm.get('min','?')}/{sm.get('med','?')}/{sm.get('max','?')}" if sm else "?"
        lm = r.get("latency_ms", {})
        lm_s = (f"{lm.get('med','?')}/{lm.get('max','?')}"
                + (f" ({lm['misses']} miss)" if lm.get("misses") else "")) if lm else "?"
        iss = r.get("correctness", [])
        iss = [x for x in iss if x != "ok"]
        rows.append([r["screen"], sm_s, lm_s, str(r.get("reads_per_poll", "?")),
                     f"{len(iss)}: " + ("; ".join(iss)[:80] if iss else "none")])
    if md:
        out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
        out += ["| " + " | ".join(row) + " |" for row in rows]
        return "\n".join(out)
    widths = [max(len(cols[i]), *(len(row[i]) for row in rows)) for i in range(len(cols))]
    line = lambda cells: "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))
    return "\n".join([line(cols), line(["-" * w for w in widths])] + [line(r) for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screens", default="main,options,kontent,pause,css")
    ap.add_argument("--trials", type=int, default=10)
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--no-ocr", dest="ocr", action="store_false")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--host", default=_os.environ.get("MK_RA_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(_os.environ.get("MK_RA_PORT", "55355")))
    args = ap.parse_args()

    def log(*a):
        print(*a, flush=True)

    log(f"daemon under test: menu_reader from {MR.__file__}")
    log(f"POLL_HZ={MR.POLL_HZ}  SETTLE_S={MR.SETTLE_S}")

    ra_counter = CountingRA(cmd_host=args.host, cmd_port=args.port)
    try:
        log("RetroArch:", ra_counter.version(), ra_counter.status())
    except RetroArchError as e:
        log(f"cannot reach RetroArch: {e}")
        _sys.exit(1)
    try:
        disc = ra_counter.read_memory(0x80000000, 6)
    except RetroArchError:
        disc = b"?"
    log(f"disc id: {disc!r}")
    if disc != b"GMKE5D":
        log("WARNING: not the USA MK:DA disc — addresses may be wrong")

    # network-remote reachability
    try:
        ra_counter._remote_send(BTN["down"], 0)
    except Exception as e:
        log(f"network-remote send failed: {e}")

    confirm_id, back_id = detect_button_polarity(ra_counter, log)
    pad = Pad(ra_counter, confirm_id, back_id)
    pad.release_all()
    verify_polarity(ra_counter, pad, log)

    speaker = RecSpeaker()
    poller = Poller(speaker, args.host, args.port)
    poller.start()
    log("poller started\n")

    results = []
    try:
        for key in args.screens.split(","):
            key = key.strip()
            if key not in SCREENS:
                log(f"unknown screen {key!r}, skipping"); continue
            try:
                results.append(run_screen(key, ra_counter, ra_counter, pad, poller, args, log))
            except Exception as e:
                import traceback
                log(f"screen {key} raised: {e}\n{traceback.format_exc()}")
                results.append(dict(screen=key, error=repr(e)))
            # try to get back to a safe place for the next screen
            pad.release_all()
            for _ in range(3):
                pad.back(after=0.4)
    finally:
        poller.stop()
        pad.release_all()
        # leave the game on the main menu
        goto_main(ra_counter, pad, log)
        pad.release_all()

    log("\n" + "=" * 70)
    log(fmt_table(results, md=args.md))
    log("=" * 70)
    log("\nreminder: set network_remote_enable + network_remote_enable_user_p1 "
        'back to "false" (RetroArch closed) and restart RetroArch.')

    # machine-readable dump
    import json
    log("\nJSON:\n" + json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
