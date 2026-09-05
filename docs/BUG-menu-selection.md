# BUG: confirming a menu item restarts the intro instead of entering the mode

Status: **investigation only — no fix applied** (per request).
Date: 2026-09-05.

## Symptom (reporter)

> When the game starts, it reads the menu options. When I select one — say
> Arcade — it starts the entire opening cinematic all over and does not start
> that section of the game.

So: narration of the menu items sounds *correct*, but pressing confirm on a menu
item does **not** enter that mode — the intro/attract cinematic replays.

## Environment observed during this audit

- RetroArch 1.22.2 + `dolphin_libretro`, pid 20995, started today 13:46.
- **Content currently loaded is MK: _Deception_ (`GQNE5D`, crc `827bb6ed`), not
  Deadly Alliance.** So MK:DA could not be tested live. All MK:DA addresses read
  back 0 right now (wrong game). The findings below are from the code, the
  config, and the RetroArch source.
- `~/Library/Logs/mkda-menu-reader.log`: the `com.orlando.mkda-menu-reader`
  daemon is running but idle ("waiting for MK: Deadly Alliance to be running")
  because `_is_target_game()` rejects `GQNE5D`.
- UDP 55355 (command) **and** UDP 55400 (network-remote P1) are both open on pid
  20995 (`lsof -nP -iUDP`).

## Confirmed: the shipped daemon never presses buttons

`grep -nE 'press\(|set_button|set_state|release_all|tap_repeat|_remote_send|write_memory|WRITE_CORE' *.py`:

- `menu_reader.py` calls only `ra.status()`, `ra.version()`, `ra.read_memory()`,
  `ra.read_u8/u16/u32()` — all of which use the command port 55355 and are reads.
- `ra_client.py`'s `_remote_sock` is created in `__init__` (`ra_client.py:56`) but
  `_remote_send()` / `set_button()` / `press()` / `set_state()` / `release_all()`
  / `tap_repeat()` (`ra_client.py:172-198`) are **only** called from `tools/`
  (`nav.py`, `calibrate.py`, `verify.py`, `diffscan.py`).
- `write_memory()` (`ra_client.py:135`) is never called by the daemon.

The tool as designed is read-only. Any button input therefore comes from the
player's own controller, from RetroArch itself, or from a calibration script
that was run manually.

---

## Ranked candidate root causes

### 1. No attract-mode / title-screen guard in `_classify()` / `_active_menu()`  — MOST LIKELY

**Confidence: high** that this is a real defect and the best fit for the symptom;
medium that it is the *only* cause.

**Evidence**

- `_classify()` (`menu_reader.py:141-146`) decides the screen from **only**
  `f_psel_init`, `p1_state`, `p2_state`, and "is there a menu?":
  ```python
  def _classify(self, s: dict) -> str:
      if s["f_psel_init"] or s["p1_state"] or s["p2_state"]:
          return Context.CHARSELECT
      if s["menu"] is not None:
          return Context.MENU
      return Context.IDLE
  ```
- `_active_menu()` (`menu_reader.py:66-94`) returns a menu whenever
  `read_u32(A.MENU_ON)` (`0x8041bc90`) is non-zero and the nav stack resolves to
  a `menu_def` in `0x80200000..0x80300000`. Nothing else is checked.
- `game_state` (`0x8041be08`) **is** read every poll into the snapshot
  (`menu_reader.py:125`, `s["game_state"]`) and is printed by `--probe`
  (`menu_reader.py:289`), but **no classification or narration code ever reads
  it.**
- The project's own calibration notes,
  `docs/research/calibration-results.md:34-36`:
  > `game_state` (0x8041be08): 1/20 title & attract-idle, 2 attract pselect
  > demo, 5 attract match, 11 in a menu.
- `calibration-results.md:44-49` documents attract mode producing live-looking
  but non-interactive menu / character-select state, with the cursor read
  "stuck" ("a stale-read / stuck-cursor artifact of the attract-mode
  countdown", "the automated run lost the screen to the attract timer").

**Mechanism**

MK:DA's title screen ("PRESS START") and its attract-mode demo are drawn by the
same front-end menu engine as the interactive menu. It is very likely that
`MENU_ON` is already non-zero, and the nav stack already resolves to the
main-menu struct (`0x80230140`) with `cursor = 0`, **before the menu is
interactive** (i.e. while `game_state` is 1/20 = title/attract-idle, or 2/5 =
attract demo, rather than 11 = in a menu).

In that window the daemon announces "Arcade, 1 of 8". The player hears a correct
menu read-out and presses confirm — but the button goes to the title/attract
input handler, whose response to *any* button is "leave attract, replay the
logo/intro sequence, then show the real menu". Result: "it starts the entire
opening cinematic all over and does not start that section of the game" —
matches the report verbatim.

**Why it fits better than the latched-button theory:** the reporter can still
*hear the menu options* (implying navigation works and the physical pad is not
being overridden), and only the *confirm* misfires — exactly what a
"narrating-a-screen-that-isn't-live-yet" bug produces.

**Recommended fix (do not apply yet)**

- Gate `Context.MENU` on `game_state == 11` (the calibrated "in a menu" value),
  and gate `Context.CHARSELECT` to exclude the attract values (`2` attract
  pselect demo, `5` attract match). Concretely, add an interactive check to
  `_classify()` / `_active_menu()` that returns `None` / `IDLE` when
  `s["game_state"]` is not the live-menu / live-CSS value.
- First **verify on real hardware** what `game_state` actually is on each real
  interactive screen (main menu, Options, Kontent, pause, character select) —
  only `11 = in a menu` is recorded today, and the sub-menus / pause / CSS
  values are unknown. Do not ship a hard `== 11` gate until those are confirmed.
- Belt-and-braces: require the resolved `(menu_def, cursor)` to be **stable for
  ~2-3 polls** before the *first* announcement after a context change, so a
  single frame of transient/attract menu state can't trigger speech. The
  `SETTLE_S` logic (`menu_reader.py:216-224`) already does this for *cursor
  moves* but the context-entry announcement in `narrate()` (`menu_reader.py:195-202`)
  speaks immediately.

---

### 2. `network_remote` left enabled → latched-button hazard — POSSIBLE, WEAKER FIT

**Confidence: the hazard is real and present; low-to-medium that it caused this
specific report.**

**Evidence — config**

`~/Library/Application Support/RetroArch/config/retroarch.cfg`:
```
3130: network_cmd_enable = "true"
3131: network_cmd_port = "55355"
3133: network_remote_base_port = "55400"
3134: network_remote_enable = "true"
3135: network_remote_enable_user_p1 = "true"
3136+: network_remote_enable_user_p2..p16 = "false"
```
UDP 55400 is open on the live RetroArch process. `install/macos/install.sh`
only ever asserts `network_cmd_enable` (`install/macos/install.sh:25-29`); it
never touches `network_remote_enable`. `tools/README.md:18-26` documents that
`network_remote_enable` + `network_remote_enable_user_p1` were turned on for
calibration.

**Evidence — RetroArch 1.22.2 source** (`input/input_driver.c`):

- Remote socket is **non-blocking**: `input_remote_init_network()` →
  `socket_nonblock(handle->net_fd[user])` (`input_driver.c:1358`).
- Per-frame poll (`input_driver.c:6431-6478`):
  ```c
  ret = recvfrom(input_st->remote->net_fd[user], (char*)&msg, sizeof(msg), 0, NULL, NULL);
  if (ret == sizeof(msg))
     input_remote_parse_packet(&input_st->remote_st_ptr, &msg, user);
  else if ((ret != -1) || ((errno != EAGAIN) && (errno != ENOENT)))
  {
     input_state->buttons[user]   = 0;   /* clear */
     input_state->analog[0..3][user] = 0;
  }
  ```
  On an **idle** port `recvfrom` returns `-1` / `EAGAIN`, so the `else if` is
  false and **`buttons[user]` is left unchanged** — there is no per-frame reset.
- `input_remote_parse_packet()` (`input_driver.c:1407-1427`) sets/clears exactly
  one bit per datagram:
  ```c
  input_state->buttons[user] &= ~(1 << msg->id);
  if (msg->state) input_state->buttons[user] |= 1 << msg->id;
  ```
- `input_state_device()` (`input_driver.c:1456-1462`):
  ```c
  if (input_st->remote && INPUT_REMOTE_KEY_PRESSED(input_st, id, port))
     res |= 1;                 /* force the button pressed */
  else { /* ...process the local/physical bind... */ }
  ```
  (`INPUT_REMOTE_KEY_PRESSED` = `remote_st_ptr.buttons[port] & (1 << id)`,
  `input_driver.c:75`.)

**Consequences**

- An **all-zero** idle remote does **not** block the physical pad — every button
  falls through to the local bind in the `else`. This is consistent with "the
  menu still reads out / still navigates".
- But a **single bit** left at 1 (a `press()` that sent `state=1` and whose
  `state=0` never arrived — script killed mid-`press()` at `ra_client.py:185-189`,
  or UDP loss) is **held down forever**, on top of the physical pad, until a
  `state=0` for that id arrives, a malformed packet clears everything, or
  RetroArch restarts.
- Buttons the calibration scripts press most (so most likely to be the stuck
  one): `a` (RetroPad id 8, = confirm), `b` (id 0, = back), `down` (id 5),
  `up` (id 4), `right` (id 7), `start` (id 3). `nav.py` / `calibrate.py` /
  `verify.py` all end on `tap_repeat("b", …)` or leave `a` pressed while waiting
  for a screen transition.

**Why this is a weaker fit for the report**

- A cleanly latched `b` or `a` or a direction would break menu **navigation**,
  not just confirm — the reporter says the menu still reads out as they move.
- A latched `start` fits least badly (Start does little on the MK:DA main menu),
  but then confirm (`a`) would still work normally.
- The **current** RetroArch process (pid 20995) started at 13:46 today, *after*
  the calibration session; its `remote_st_ptr` is `calloc`-zeroed
  (`input_driver.c:1387`), so nothing is latched right now unless a script was
  run against this exact instance. At the time of the original report the user
  may well have been on the same instance used for calibration, where a latch
  was plausible.

**Recommended fix (do not apply yet)**

- With RetroArch **closed**, set in `retroarch.cfg`:
  `network_remote_enable = "false"` (and/or `network_remote_enable_user_p1 = "false"`).
  The shipped daemon never uses 55400 — only `tools/` do, and those can flip it
  back on for a calibration run.
- Make `install/macos/install.sh` assert `network_remote_enable` is `false` the
  same way it already asserts `network_cmd_enable` is `true`
  (`install/macos/install.sh:25-29`), and have the `tools/` scripts turn it on
  only for their own run and off again after.
- To clear a latch immediately without editing cfg: restart RetroArch, or send
  one `state=0` packet for every RetroPad id to 55400
  (`python3 -c "from ra_client import RAClient; RAClient().release_all()"`).

---

### 3. RetroArch input config / hotkeys / remaps — ESSENTIALLY CLEARED

**Confidence: high** that nothing here is the cause; one item worth a 30-second
check.

From `retroarch.cfg`:

| line | setting | assessment |
|---|---|---|
| 3047 | `menu_swap_ok_cancel_buttons = "true"` | Affects **only RetroArch's own RGUI**, never the game/core. Not a cause. |
| 2851-2853 | `input_remap_binds_enable = "true"`, `input_remapping_directory = ".../config/remaps"` | No remap file exists for `dolphin_libretro`. `config/remaps/` contains only `MAME/MAME.rmp` and `MAME 2003 (0.78)/MAME 2003 (0.78).rmp` (both set `input_playerN_btn_select/start` and enable turbo) — neither loads for MK:DA. Clear. |
| 1456-1608 | P1 keyboard binds | `a = "x"`, `b = "z"`, `x = "s"`, `y = "a"`, `start = "enter"`, `select = "rshift"`, dpad = arrow keys. All P1 gamepad `*_btn` = `"nul"` (autoconfig fills a connected pad at runtime). Nothing double-bound. |
| 250-253 | `input_enable_hotkey = "nul"` | Hotkeys need **no** modifier, so bare `p` (pause, line 377), `v` (AI service, line 181), `f1` (RGUI toggle, line 296) are always live. Only a problem if the player's *confirm* is one of those keys/buttons. |
| 181-184 | `input_ai_service = "v"`, `input_ai_service_btn = "15"` | Pressing `v` or RetroPad **R3** triggers the OCR AI-service. If the player's controller autoconfig maps a face/confirm button to RetroPad id 15, confirm would fire OCR instead of reaching the game. **Worth checking the active pad's autoconfig** in `~/Library/Application Support/RetroArch/autoconfig/`. Low probability. |
| 3187 | `pause_nonactive = "false"` | Correct — the game keeps running when RetroArch is backgrounded (the daemon needs this). Not a cause. |
| 1593-1596, 1746-1749 | `input_playerN_turbo = "nul"` | No turbo bound for P1/P2 in the main cfg. |

---

## Unrelated defects noticed (not the reported bug, but worth logging)

1. **Intermittent silence when RetroArch is unfocused / App-Napped.**
   `~/Library/Logs/mkda-menu-reader.log` is full of:
   ```
   (retro) bad READ_CORE_MEMORY reply: 'GET_STATUS PLAYING gamecube,Mortal Kombat - Deadly Alliance (USA) (Rev 1).nkit,crc32=97e61be9'
   (retro) no reply to 'READ_CORE_MEMORY 8041be08 4' (is RetroArch focused / not App-Napped?)
   ```
   `_is_target_game()` (`menu_reader.py:228-255`) calls `status()` then
   `read_memory(0x80000000, 6)` back-to-back on the shared socket. The `_cmd()`
   demux (`ra_client.py:60-85`) drops a reply whose leading token doesn't match,
   so a slow `GET_STATUS` answer arriving during the `READ_CORE_MEMORY` wait is
   discarded and the read then times out. Net effect is dropped narration when
   macOS App-Naps RetroArch (see README troubleshooting), not wrong input. A
   dedicated socket per call, or draining stale datagrams before each command,
   would harden it.

2. **Env-var prefix mismatch.** Repo `menu_reader.py:13-14,298-299` and
   `speak.py:49-52` read `MK_RA_HOST` / `MK_VOICE` / `MK_RATE_WPM` /
   `MK_SPEAK_BACKEND`, but the deployed copy, the README ("Environment
   variables" section) and the launchd plist comments all use the `MKDA_`
   prefix. Cosmetic today (the plist sets none), but a user following the README
   to set `MK_VOICE` would get no effect with the repo build.

3. **Sibling project has the same class-1 bug.**
   `~/Desktop/MK-Deception-accessibility/deception_reader.py:123-129`
   (`_classify`) keys off `menu_sub` range + `mode_of_play in (0, 8)` with no
   attract guard — same failure mode as #1 above. Fix both together.

---

## Test plan (once MK:DA `GMKE5D` is loaded)

1. **Map the screens.** From the repo dir run `python3 menu_reader.py --probe`.
   Record `menu_on`, `sp`, `gs=` (game_state) and whether `say` fires at each of:
   cold logos, title / "PRESS START" (do **not** press Start), attract demo
   (wait ~30 s for it to start), and the real menu after pressing Start.
   - Expect to see the daemon announce "Main menu" / "Arcade, 1 of 8" *before*
     Start is pressed if cause #1 is right.
2. **Confirm the game_state gate.** Verify `game_state == 11` on the real
   interactive main menu, and record its value on Options, Kontent, the pause
   menu, and character select. Verify title + attract report a *different*
   value (expected 1/20 and 2/5). If the interactive screens are cleanly
   separable, gating on those values fixes #1.
3. **Reproduce.** With `--probe` running and the daemon already announcing
   "Arcade, 1 of 8" on the title/attract screen, press confirm once. If the
   intro/attract restarts and the mode does not load → cause #1 confirmed.
4. **Rule #2 in or out.** Fresh RetroArch start, `lsof -nP -iUDP:55400` to
   confirm the port. Run
   `python3 -c "from ra_client import RAClient; RAClient().release_all()"`
   (sends `state=0` for all 16 ids) and retest confirm. If behaviour only
   improves after that, a latched remote button was involved. Then set
   `network_remote_enable = "false"`, restart RetroArch, retest.
5. **Check the AI-service button (cause #3).** `grep -R "input_ai_service_btn\|_btn_r3\|\"15\"" ~/Library/Application\ Support/RetroArch/autoconfig/<active-pad>.cfg` — make sure the player's confirm button is not RetroPad id 15.
6. **Regression after the #1 fix.** Walk the real main menu Up/Down — every item
   still announced with "N of M"; enter Arcade → character-select narration
   still works; pause menu still works.

---

## Resolution (2026-09-05)

Both fixes applied and pushed.

**Cause 2 (the actual bug) — network_remote latch.** Reproduced live: with
`network_remote_enable_user_p1 = "true"`, holding a `b` (back) button via UDP
55400 immediately closed the menu (`menu_on` → 0) and dropped the game to the
"PRESS START" title screen; the next button then replayed the intro — exactly the
report. Fix:
- `retroarch.cfg`: `network_remote_enable` and `network_remote_enable_user_p1`
  set to `"false"` (with RetroArch closed). Port 55400 no longer opens.
- All three installers now also turn `network_remote` off and re-check it on
  every run (same as they assert `network_cmd_enable` on).
- `tools/README.md` / `CONTRIBUTING.md`: the calibration scripts must flip it back
  off after a run.

**Cause 1 — phantom attract narration (hardening).**
- `menu_reader._classify()`: `_NON_MENU_STATES = (1, 20)` — MENU is not reported
  when `game_state` is a title/attract value. Verified live: real main menu +
  Options submenu are `game_state == 11`; title / attract-idle are `1`; a real
  in-match pause menu is `5` (still narrated).
- `menu_reader.narrate()`: a new non-idle context must hold for **2 consecutive
  polls** before the first announcement, so one transient frame can't trigger
  speech. Unit-tested (`_classify` returns IDLE for gs=1 with a stale menu;
  speaks for gs=11 held; silent for a 1-frame blip).
- `deception_reader` got the same 2-poll context debounce.
