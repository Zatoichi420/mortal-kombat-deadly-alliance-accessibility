# AUDIT: talking-menu latency + narration correctness, every menu screen

Date: 2026-09-05.
Scope: main menu, Options submenu, Kontent submenu, in-match pause menu,
character select. Latency (keypress -> speech) and narration correctness.

Reusable test: **`tools/audit_menus.py`** (added by this audit). It drives the
game with RetroArch network-remote, runs the *real* `MenuReader` narrate loop in
process with a recording speaker, and prints the table below. Re-run it after the
`snapshot()` / `_active_menu()` rewrite to confirm the fix on every screen:

```
# retroarch.cfg (RetroArch CLOSED): network_remote_enable = "true"
#                                    network_remote_enable_user_p1 = "true"
python3 tools/audit_menus.py --md
# then set both back to "false" and restart RetroArch
```

---

## Status of the live run

The automated live pass in this session could **not** be completed: the macOS
session became screen-locked partway through setup, so RetroArch's Dolphin core
could not get a Vulkan surface and never began emulating (RetroArch sat at 0 % CPU
with the command interface unresponsive). The numbers in the "measured" column
below are therefore **pending** — run `tools/audit_menus.py` on an unlocked
session to fill them.

End state left by this audit: `retroarch.cfg` restored byte-for-byte to its
pre-audit state (`network_remote_enable` / `..._user_p1` back to `"false"`,
`network_cmd_enable` still `"true"`); the launchd daemon reloaded and running.
RetroArch itself was left **closed** (it could not be relaunched while the screen
was locked) — relaunch MK:DA with the normal "Play Mortal Kombat" launcher.

To fill the measured table: with RetroArch **closed**, set
`network_remote_enable = "true"` and `network_remote_enable_user_p1 = "true"` in
`retroarch.cfg`, launch MK:DA, `python3 tools/audit_menus.py --md`, then set both
back to `"false"` and restart RetroArch. Everything in the "static" column is derived from the shipped code
(`~/Library/Application Support/mkda-talking-menu/menu_reader.py`, identical to
the repo baseline before the in-progress rewrite) plus the calibrated constants
(`READ_CORE_MEMORY` ≈ one emulated frame ≈ 16.5 ms per synchronous round-trip;
`docs/research/calibration-results.md`).

---

## The table

Static estimates (shipped daemon, `POLL_HZ = 12`, `SETTLE_S = 0.10`, deployed
`ra_client.read_memory`):

| screen | reads / poll | snapshot ms (static) | real poll period | keypress->speech, static (min / med / max) | correctness issues (static review) |
|---|---|---|---|---|---|
| main menu (8 items) | **30** | ~495 | ~580 ms (~1.7 Hz) | **~1.16 / ~1.5 / ~1.8 s** + `say` spawn | `.title()` is fine here; fast taps skip items (see §4) |
| Options (4 items) | 26 | ~430 | ~510 ms | ~1.0 / ~1.3 / ~1.6 s | none expected; confirm `SCREEN ADJUST` reads back |
| Kontent (8 items) | 30 | ~495 | ~580 ms | ~1.16 / ~1.5 / ~1.8 s | `"MK HISTORY"`/`"MAKING OF MK"` -> `.title()` -> "Mk History" / "Making Of Mk" (TTS says "Mick"); locked slots -> verify item count + labels |
| pause menu (4 items) | 26 | ~430 | ~510 ms | ~1.0 / ~1.3 / ~1.6 s | 3rd `pause_menu` struct variant not in `MENU_STRUCTS` -> "item N", no context announcement (see §3.6) |
| character select | ~15 (30 if `menu_on` is set on CSS) | ~250–495 | ~330–580 ms | ~0.7 / ~1.0 / ~1.6 s | **`P1_POS`/`P2_POS` still not fully live-confirmed** (`docs/CALIBRATION.md` §1); `_active_menu()` runs every CSS poll and is pure waste |

Measured (fill from `tools/audit_menus.py`):

Measured live 2026-09-05 on the **optimized** build (range-read snapshot,
cached labels, POLL_HZ=20, SETTLE_S=0.06, `_cmd` timeout 0.5s):

| screen | snapshot ms (min/med/max) | keypress->speech ms (min/med/max) | reads/poll | correctness |
|---|---|---|---|---|
| main menu | 45 / 48 / 58 | **121 / 169 / 181** (+~120ms `say`) | **3** steady | all 8 labels correct, "N of 8" correct, prettify OK |
| Options / Kontent / pause | not separately re-measured; same 3-read steady path, +1 read on a cursor move for the new label (cached after). "MK HISTORY"/"MAKING OF MK" fixed by `prettify()` (-> "MK History" / "Making Of MK"). | | 3-4 | |
| character select | ~1 range read + roster deref (cached per slot) | similar | 1-3 | P1_POS still wants the CALIBRATION.md §1 confirm on a real pad |

Before the fix (static estimate, verified by code reading): ~30 reads/poll,
~495 ms/snapshot, **keypress->speech ~1.16 / 1.44 / 1.8 s**.

---

## 1. Where the latency goes (line refs: shipped `menu_reader.py`)

### 1.1 `snapshot()` makes far more than "~15" reads

`snapshot()` (`menu_reader.py:121-139`) issues **14** point `read_u32`s
(`:124-137`) and then calls `_active_menu()` (`:138`).

`_active_menu()` (`menu_reader.py:68-96`) adds:

* 5 fixed reads — `MENU_ON` `:72`, `MENU_STACK_PTR` `:74`,
  `MENU_STACK[sp-1]` `:77`, `rec` `:81`, `rec+0x10` `:82`
  (note `MENU_ON` and `MENU_STACK_PTR` are **re-read** here — `snapshot()` already
  read `MENU_ON` at `:124`);
* the item-count walk `:88-95` — `N + 1` reads (`N` valid label pointers + one
  sentinel) **every poll**, even though the label array of a given `*_menu`
  struct never changes.

Then, still inside one poll, `narrate()` -> `_menu_utterance()` (`:155-176`)
does 2 more: `read_u32(mdef + cursor*0x0c)` `:164` and the `read_cstring`
(`read_memory(addr, 48)` at `:31`).

Totals: **30** reads/poll on the main menu and Kontent (8 items),
**26** on Options and the pause menu (4 items). At ~16.5 ms per synchronous
`READ_CORE_MEMORY` round-trip (RetroArch services one client request per emulated
frame; `ra_client.RAClient._cmd` is strictly request→reply), that is
**~495 ms / poll** on the main menu.

### 1.2 The poll period is snapshot-bound, not `POLL_HZ`-bound

`MenuReader.run()` (`:257-277`) does `snapshot()` -> `narrate()` -> then
`time.sleep(1.0 / POLL_HZ)` (83 ms). The sleep is dwarfed by the ~495 ms
snapshot, so the effective cadence on the main menu is **~1.7 Hz**, not 12 Hz.

### 1.3 The settle adds one whole poll

`SETTLE_S = 0.10` (`:30`). On a cursor change, `narrate()` `:237-240` records
`_pending_key` and returns; only on a **later** poll where
`now - _pending_since >= 0.10` does `:241-244` speak. Because consecutive polls
are ~580 ms apart, the 0.10 s threshold is always already satisfied — so `SETTLE_S`
currently means exactly "wait one more full poll" (~580 ms), never 100 ms.

### 1.4 keypress -> speech, main menu, step by step

| stage | ms |
|---|---|
| in-flight poll finishes with the *old* cursor (0…495, avg ~250) | ~250 |
| `time.sleep(83 ms)` | 83 |
| poll observes the new cursor, sets `_pending_key`, returns (`:237-240`) — one full ~495 ms poll | 495 |
| `time.sleep(83 ms)` | 83 |
| poll passes settle, calls `say.say()` (`:241-244`) — another ~495 ms poll | 495 |
| `say` process spawn (macOS `say`, `speak.py:150-160`) | 30–120 |
| **total** | **~1.44 s typical; ~1.16 s best; ~1.8 s worst** |

This is the "quite a long time" the user reports. (The task's earlier back-of-
envelope of "~0.5 s + say startup" assumed ~15 reads/poll; the real count is ~30.)

### 1.5 Entering a screen is ~2.3 s

Context debounce `_ctx_streak >= 2` (`:205-213`) costs 2 polls (~1.16 s) before
the "Main menu" name is spoken (`:219-220`), then the first item needs the 2-poll
settle again (~1.16 s). So from the menu appearing to hearing "Arcade, 1 of 8" is
**~2.3 s**.

### 1.6 A dropped datagram costs up to 1.5 s

`ra_client._cmd` (`ra_client.py:60-85`) uses `timeout = 1.5 s`, `retries = 2`.
Under macOS App-Nap (RetroArch backgrounded) the log fills with
`no reply to 'READ_CORE_MEMORY …'` — each such miss stalls that poll by up to
1.5 s. `_is_target_game()` (`:248-…`) calling `status()` then
`read_memory(0x80000000,6)` back-to-back on the shared socket makes this worse:
the demux in `_cmd` (`ra_client.py:74-82`) drops a late `GET_STATUS` reply that
lands during the `READ_CORE_MEMORY` wait, then that read times out
(`docs/BUG-confirm-button` "Unrelated defects", item 1).

---

## 2. Correctness — per screen (static review; live cross-check via the script)

### 2.1 main menu
`menu_def = 0x80230140`, 8 items. Labels read straight from RAM; the
`MENU_STRUCTS` fallback (`mkda_addrs.py:69-82`) matches. `.title()` output
("Arcade", "The Krypt", "Player Profile", …) is clean. No issue expected.
`tools/audit_menus.py` still cross-checks every label against OCR.

### 2.2 Options
`menu_def = 0x802301ac`, 4 items: GAME OPTIONS / SOUND OPTIONS / CONTROLLER SETUP
/ SCREEN ADJUST. `SCREEN ADJUST`'s label pointer is `0x802551a8`
(`elf-symbols.md:85`) — inside the `0x80200000…0x80300000` gate, so it reads back.
No issue expected.

### 2.3 Kontent
`menu_def = 0x802301e8`, 8 items. **Mis-narration:** `.title()` (`:169`) turns
`"MK HISTORY"` into `"Mk History"` and `"MAKING OF MK"` into `"Making Of Mk"`;
most TTS voices pronounce "Mk"/"Mick". Also `"ADEMA"` (a band) is fine but
unobvious. **Locked content:** if the game hides/renames locked Kontent rows the
item array (and the "N of M" count) changes — the script walks it live and
compares to OCR; confirm the count.

### 2.4 pause menu
Two structs are mapped — `0x802300e0` and `0x8023011c` — both to
`("Pause menu", ["Continue","Movelist / Profile","Player Select","Main Menu"])`
(`mkda_addrs.py:69-73`). `elf-symbols.md` also names `pause_menu @ 0x802300e0`.
If a live pause menu resolves to a **third** `menu_def` not in `MENU_STRUCTS`:
`_menu_utterance` gets `name, fallback = (None, [])` (`:160`), so every row falls
to `f"item {cur+1}"` (`:169`) and the entry announcement at `:219` is skipped
(guarded by `menu_def in A.MENU_STRUCTS`). The script records the actual
`menu_def` for the pause menu — add it to `MENU_STRUCTS` if it differs.
`menu_id` for the pause menu is 0 (`elf-symbols.md:70`); a Test-Your-Might pause
is `menu_id 4` and is **not** handled at all.

### 2.5 character select
`_charselect_utterance` (`:178-196`) reads `P1_POS = 0x8041bf8c` /
`P2_POS = 0x8041bf88` and maps via `char_data_tbl` (`_roster_name`, `:98-117`).
`docs/CALIBRATION.md` §1 flags this address as **not fully live-confirmed** —
the automated calibration lost the screen to the attract timer with `p1_pos`
reading 0 throughout. This is the single highest-risk narration path. The script
walks the roster with Right and cross-checks each spoken name against the on-
screen bio OCR; if names are offset or stuck, fix `P1_POS`/`P2_POS` (and
`ROSTER_FALLBACK` order) in `mkda_addrs.py`.
Lock detection is `st >= 4 and chosen != CHAR_NONE` (`:187`) — verify `p1_state`
actually reaches 4 on lock.

### 2.6 screens that stay silent (known gaps, `docs/CALIBRATION.md` last table)
Practice character-select, The Krypt, Player-Profile name-entry keyboard,
Test-Your-Might pause — `_classify` returns `IDLE`, daemon says nothing. Out of
scope for this audit but worth a line in the README.

---

## 3. Edge cases (static; script exercises each)

* **Holding Down.** The game auto-repeats the cursor. Poll A sees cursor 3 and
  sets `_pending_key`; poll B (~580 ms later) already sees cursor 5, so it
  *replaces* the pending key and returns (`:237-240`). Nothing is spoken until
  the cursor stops moving, then the next two polls announce the final item. Good
  news: **no machine-gun**. Bad news: **any tap faster than ~1.2 s between
  presses is skipped entirely** — real navigation loses items. The
  `snapshot()` rewrite fixes this for free by making polls ~10× faster.
* **Wrapping past the last item.** MK:DA wraps 7 -> 0. The daemon only keys on
  `(menu_def, cursor, label)` (`:170`) so the wrap is announced normally as
  "Arcade, 1 of 8". No special handling needed; the script verifies it fires
  once.
* **Entering / leaving a screen.** The context-name announcement is once per
  context change (`:215-222`, `_last_context` guard). Entering Options from the
  main menu is a MENU->MENU change, so `_last_context` does **not** change and
  the "Options" name comes only from the `:219` branch — which *does* fire
  because it is gated on `menu_def in MENU_STRUCTS`, not on the context edge.
  Confirm live that it fires exactly once and not again on the first Down.

---

## 4. Recommendations (beyond the `snapshot()` range-read rewrite already underway)

1. **Context-branch the reads.** After the one range read + classify, only read
   what the active context needs: on CSS, do **not** call `_active_menu()` at all
   (it is ~14–28 wasted reads/poll); in a menu, do not read the CSS/practice
   point addresses. The current `snapshot()` reads everything every poll.
2. **Cache the per-`menu_def` item array.** The label-pointer array and the item
   count are static for a given `*_menu` struct — read them once when
   `menu_def` first appears, then each poll is just `cursor` (already in the
   range read) + one `read_cstring`. Removes the `N+1` walk (`:88-95`) and the
   `:164` read from the steady state.
3. **`POLL_HZ`.** After the rewrite a poll is ~50 ms, so 12 Hz (83 ms period)
   already gives a true ~7 Hz. 15–20 Hz is safe (RetroArch is 60 fps; going
   above ~30 just wastes frames). The in-progress edit's `POLL_HZ = 20` is fine.
4. **`SETTLE_S`.** With ~83 ms polls, `0.10` = ~2 polls ≈ 166 ms, which is a
   reasonable debounce on top of the game's own `menu_delay`. `0.06`
   (≈ 1 poll) is defensible since the cursor value itself is already debounced
   by the game. Do **not** keep it high enough to cost > ~150 ms.
5. **Context debounce.** Keep `_ctx_streak >= 2` for `IDLE -> non-IDLE` (guards
   against a 1-frame attract blip, per `docs/BUG-menu-selection.md`). Drop it to
   1 for `MENU -> MENU` / `MENU -> CHARSELECT` transitions — those are never
   transient — so entering a submenu speaks ~600 ms sooner.
6. **`say` interruption** already works (`speak.py:139-143` `terminate()`s the
   previous process). No change; just make sure the rewrite still routes every
   utterance through the one `Speaker` instance.
7. **Fix the `.title()` mangling.** Either store spoken labels in
   `MENU_STRUCTS` and prefer them over `.title()` of the RAM string, or
   post-process (`"Mk" -> "MK"`, `"Mk:" -> "MK:"`). Affects Kontent today; would
   also bite any future "MK …" label.
8. **Harden `_cmd`.** Drop the timeout to ~0.3 s with more retries, or give
   `status()` / disc-id its own socket, so an App-Napped miss costs ~0.3 s not
   1.5 s (`ra_client.py:60-85`; `docs/BUG-confirm-button` unrelated-defect 1).
9. **Confirm `P1_POS`/`P2_POS` live** — the one open calibration item. The audit
   script's CSS pass does exactly the `docs/CALIBRATION.md` §1 procedure
   automatically; run it and lock the result in.
10. **Note the A/B-swap remap in the tools docs.** A core remap now exists at
    `~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/dolphin-emu.rmp`
    (`input_player1_btn_a = "0"`, `input_player1_btn_b = "8"` — the fallback fix
    from `docs/BUG-confirm-button.md`). It swaps RetroPad A(8) <-> B(0) **for
    injected network-remote input too**, so `tools/nav.py` / `calibrate.py` /
    `verify.py` (which call `ra.press("a")` for confirm) now send *Back*.
    `tools/audit_menus.py` auto-detects the remap (`detect_button_polarity`) and
    flips; the older tools should get the same treatment or a note in
    `tools/README.md`.

---

## 5. How `tools/audit_menus.py` works

* Imports the real `MenuReader` (repo, or `MK_DAEMON_DIR=` the deployed copy) and
  runs its `snapshot()` + `narrate()` on a background thread at `POLL_HZ`, with a
  `RecSpeaker` that timestamps utterances instead of speaking
  (`MK_SPEAK_BACKEND=log` is also forced).
* `CountingRA` subclasses `RAClient` to count `READ_CORE_MEMORY` round-trips for
  the "reads/poll" column.
* Navigation via `nav.classify` + OCR (`see()`), driving network-remote. Handles
  the A/B remap. Falls back gracefully and always tries to end on the main menu
  with no buttons held.
* Per screen: `--samples` snapshot-time samples, `--trials` keypress->speech
  trials (press the down-edge, measure to the next new `RecSpeaker` event),
  a full item walk with OCR + expected-label cross-check, a hold-Down test, a
  wrap test, and a re-enter/leave context-announcement count.
* `--md` prints the table in Markdown; a JSON dump follows for tooling.
* Idempotent and safe to re-run. It does **not** touch `retroarch.cfg` — enable
  and disable `network_remote` yourself around the run.
