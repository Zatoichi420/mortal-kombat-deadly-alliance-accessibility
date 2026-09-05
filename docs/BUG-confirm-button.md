# BUG: the natural "confirm" button (physical A / Cross) backs out and replays the intro

Status: **investigation + options only — no config or code changed** (per request).
Date: 2026-09-05.

## Summary

On the MK: Deadly Alliance main menu (GameCube, RetroArch `dolphin_libretro`):

| the user presses | RetroPad id it autoconfigs to | GameCube button the core sends | what the game does |
|---|---|---|---|
| physical **A** (Xbox) / **Cross** (PS) — the bottom face button | RetroPad **B** (id 0) | GameCube **B** | **Back / Cancel** → drops to attract, intro cinematic replays ← the bug |
| physical **B** (Xbox) / **Circle** (PS) — the right face button | RetroPad **A** (id 8) | GameCube **A** | **Confirm** → starts Arcade |
| **Start** | RetroPad Start (id 3) | GameCube Start | **Confirm** → starts Arcade |

This was confirmed live by injected input. It is **not** the same defect as
[`BUG-menu-selection.md`](BUG-menu-selection.md) (that was a stuck `network_remote`
button + phantom attract narration, both since fixed). This one is a pure
button-identity mismatch: the button the user reaches for as "confirm" is wired,
correctly and by design, to GameCube **B**, which is the menu's Back action.

The user is totally blind, navigates by ear, thinks "A = confirm", and also plays
the fighting game itself (where GameCube A/B/X/Y are the four attack buttons), so
any fix has to be weighed against the in-match controls.

---

## 1. Confirm the mechanism

### 1.1 What the libretro Dolphin core actually maps

Source: `libretro/dolphin`, `Source/Core/DolphinLibretro/Input.cpp`
(<https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Input.cpp>).

**Step 1 — the core registers RetroPad inputs by their RetroPad letter/name**
(`Device::Device`, `case RETRO_DEVICE_JOYPAD:`, lines ~396–412):

```cpp
AddButton(RETRO_DEVICE_ID_JOYPAD_B, "B");       // id 0  -> input named "B"
AddButton(RETRO_DEVICE_ID_JOYPAD_Y, "Y");       // id 1  -> "Y"
AddButton(RETRO_DEVICE_ID_JOYPAD_SELECT, "Select");
AddButton(RETRO_DEVICE_ID_JOYPAD_START, "Start"); // id 3
AddButton(RETRO_DEVICE_ID_JOYPAD_UP, "Up");     // id 4
AddButton(RETRO_DEVICE_ID_JOYPAD_DOWN, "Down"); // id 5
AddButton(RETRO_DEVICE_ID_JOYPAD_LEFT, "Left"); // id 6
AddButton(RETRO_DEVICE_ID_JOYPAD_RIGHT, "Right"); // id 7
AddButton(RETRO_DEVICE_ID_JOYPAD_A, "A");       // id 8  -> "A"
AddButton(RETRO_DEVICE_ID_JOYPAD_X, "X");       // id 9  -> "X"
AddButton(RETRO_DEVICE_ID_JOYPAD_L, "L");       // id 10
AddButton(RETRO_DEVICE_ID_JOYPAD_R, "R");       // id 11
AddButton(RETRO_DEVICE_ID_JOYPAD_L2, "L2");     // id 12
AddButton(RETRO_DEVICE_ID_JOYPAD_R2, "R2");     // id 13
AddButton(RETRO_DEVICE_ID_JOYPAD_L3, "L3");     // id 14
AddButton(RETRO_DEVICE_ID_JOYPAD_R3, "R3");     // id 15
```

The analog device (`case RETRO_DEVICE_ANALOG:`, lines ~415–426) adds
`X0±/Y0±` (RetroPad left stick), `X1±/Y1±` (right stick), and
`Trigger0+ / Trigger1+` (the analog values behind RetroPad **L2 / R2**).

**Step 2 — the core binds the emulated GameCube pad to those named inputs**
(`UpdateGCMappings`, lines ~1367–1417). The GameCube "Buttons" control group in
Dolphin is ordered `A, B, X, Y, Z, Start` = indices 0–5:

```cpp
gcPad->SetDefaultDevice(devJoypad);              // bare tokens below resolve on the RetroPad joypad device
...
gcButtons->SetControlExpression(0, "A");         // GC A     <- RetroPad "A"     = id 8
gcButtons->SetControlExpression(1, "B");         // GC B     <- RetroPad "B"     = id 0
gcButtons->SetControlExpression(2, "X");         // GC X     <- RetroPad "X"     = id 9
gcButtons->SetControlExpression(3, "Y");         // GC Y     <- RetroPad "Y"     = id 1
gcButtons->SetControlExpression(4, "R");         // GC Z     <- RetroPad "R"     = id 11  (right shoulder!)
gcButtons->SetControlExpression(5, "Start");     // GC Start <- RetroPad "Start" = id 3
gcMainStick->SetControlExpression(0..3, `<devAnalog>:Y0-/Y0+/X0-/X0+`);  // GC analog stick <- RetroPad LEFT stick
gcCStick  ->SetControlExpression(0..3, `<devAnalog>:Y1-/Y1+/X1-/X1+`);   // GC C-stick     <- RetroPad RIGHT stick
gcDPad    ->SetControlExpression(0..3, "Up"/"Down"/"Left"/"Right");      // GC D-Pad       <- RetroPad d-pad ids 4/5/6/7
gcTriggers->SetControlExpression(0, `<devAnalog>:Trigger0+`|(L2&!`...Trigger0+`)); // GC L (full) <- left trigger / RetroPad L2 (id 12)
gcTriggers->SetControlExpression(1, `<devAnalog>:Trigger1+`|(R2&!`...Trigger1+`)); // GC R (full) <- right trigger / RetroPad R2 (id 13)
gcTriggers->SetControlExpression(2, `<devAnalog>:Trigger0+`|L3);   // GC L (soft) <- left trigger / RetroPad L3 (id 14)
gcTriggers->SetControlExpression(3, `<devAnalog>:Trigger1+`|R3);   // GC R (soft) <- right trigger / RetroPad R3 (id 15)
gcTriforce->SetControlExpression(0, "L");        // Triforce "Test" only  <- RetroPad "L" = id 10  (no GC-pad function)
gcTriforce->SetControlExpression(2, "Select");   // Triforce "Coin" only  <- RetroPad "Select" = id 2
```

**Exact RetroPad id → GameCube control, for `dolphin_libretro` (default, RETRO_DEVICE_JOYPAD):**

| RetroPad id | RetroArch "Controls" label (from `descGC`, Input.cpp ~116–141) | GameCube control |
|---|---|---|
| **A (8)** | "A" | **GameCube A**  ✅ (matches the question) |
| **B (0)** | "B" | **GameCube B**  ✅ (matches the question) |
| **X (9)** | "X" | **GameCube X** |
| **Y (1)** | "Y" | **GameCube Y** |
| **R (11)** | "Z" | **GameCube Z** (throw) — this is the *right shoulder* button |
| **L2 (12)** | "L" | **GameCube L** trigger, full press (or the analog left trigger) |
| **R2 (13)** | "R" | **GameCube R** trigger, full press (or the analog right trigger) |
| L3 (14) | "L-Analog" | GameCube L trigger, soft press |
| R3 (15) | "R-Analog" | GameCube R trigger, soft press — **also RetroArch's AI-service hotkey, `input_ai_service_btn = "15"`** |
| Start (3) | "Start" | GameCube Start |
| L (10) | "Triforce - Test" | nothing on a normal GameCube pad |
| Select (2) | "Triforce - Coin" | nothing on a normal GameCube pad |
| d-pad 4/5/6/7 | Up/Down/Left/Right | GameCube D-Pad |
| left stick | — | GameCube analog stick |
| right stick | — | GameCube C-stick |

So `A(8)→GC A` and `B(0)→GC B` are confirmed from source. The core preserves the
**RetroPad letter identity** of the four face buttons; it does not look at where
the buttons physically sit.

### 1.2 Why the user's pad turns "physical A / Cross" into GameCube B

The Xbox Wireless Controller / DualSense autoconfigs
(`~/Library/Application Support/RetroArch/autoconfig/mfi/`) follow RetroArch's
**Nintendo / SNES-layout RetroPad convention**: RetroPad "A" is the *right* face
button, RetroPad "B" is the *bottom* face button.

```
input_b_btn = "0"   input_b_btn_label = "A/Cross"      # physical bottom button -> RetroPad B (id 0)
input_a_btn = "8"   input_a_btn_label = "B/Circle"     # physical right  button -> RetroPad A (id 8)
input_y_btn = "1"   input_y_btn_label = "X/Square"     # physical left   button -> RetroPad Y (id 1)
input_x_btn = "9"   input_x_btn_label = "Y/Triangle"   # physical top    button -> RetroPad X (id 9)
input_r_btn = "11"  input_r_btn_label = "R1"           # physical R1     -> RetroPad R (id 11) -> GC Z
input_l2_axis = "+4"                                   # left trigger    -> RetroPad L2 -> GC L
input_r2_axis = "+5"                                   # right trigger   -> RetroPad R2 -> GC R
input_r3_btn = "15"                                    # right stick click -> RetroPad R3 -> AI service
```

Chain for the button the user presses to "confirm":

```
physical A / Cross (bottom)  ->  RetroPad B (id 0)  ->  core binds GC B <- "B"  ->  GameCube B  ->  MK:DA menu "Back/Cancel"
```

On the MK:DA main menu, GameCube B on the top-level "mode" menu walks *back past
the top of the stack*, which returns the front-end to attract mode; attract then
starts the logo/intro sequence again. Verbatim match for the report
("it starts the entire opening cinematic all over").

`retroarch.cfg` state that matters here: every `input_player1_*_btn` is `"nul"`
(the autoconfig fills them at runtime), `input_joypad_driver = "mfi"`,
`input_remap_binds_enable = "true"`, `menu_swap_ok_cancel_buttons = "true"`
(RGUI only — see §2f), `input_ai_service_btn = "15"`. No remap file exists for
`dolphin_libretro` — `config/remaps/` holds only `MAME/` and `MAME 2003 (0.78)/`.

### 1.3 Standalone Dolphin vs the libretro core — why the default differs

- **Standalone Dolphin**: when you let it auto-populate a GameCube controller
  from a detected SDL/XInput pad (or use its bundled default profile), it binds
  the emulated pad to the host pad **by physical position** — GC A ← the South /
  bottom button (Xbox **A**, PS **Cross**), GC B ← East, GC X ← West, GC Y ←
  North, GC Z ← a shoulder/trigger, GC Start ← Start. So in standalone, pressing
  Xbox **A** presses GameCube **A**, and menus "just work" for someone expecting
  A = confirm. (Dolphin wiki / RetroBat "Dolphin controller mapping".)
- **`dolphin_libretro`**: binds the emulated pad to the **abstract RetroPad**
  (`gcButtons->SetControlExpression(0, "A")` → RetroPad input *named* "A" = id 8),
  and RetroArch's autoconfig layer has already mapped the host pad to the RetroPad
  by the **SNES face-button convention** (bottom = "B" = id 0, right = "A" = id 8).

Net effect: the physical bottom "confirm-shaped" button is **GameCube A** in
standalone Dolphin but **GameCube B** in the libretro core. The core is not
buggy — it is faithfully preserving RetroPad letter identity — but that identity
is the *opposite* of the physical layout a lapsed-Xbox / PlayStation player's
thumb expects, and MK:DA (like most GC games) puts Back on B.

Citations: core source as above; `library_name = "dolphin-emu"` from
`Source/Core/DolphinLibretro/Main.cpp:162`
(<https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Main.cpp>);
libretro Dolphin docs <https://docs.libretro.com/library/dolphin/>.

---

## 2. Every fix, with pros/cons for THIS user

### (a) Tell the user which button to press — no config change

**What to tell them, per pad:**

- **Both pads (simplest, unambiguous):** *"On the MK:DA menus, press **Start** to
  choose an item."* RetroPad Start (id 3) → GameCube Start confirms every MK:DA
  menu (tested). Start does nothing harmful anywhere on those menus. One rule,
  both controllers, nothing to remember about face buttons.
- **Xbox Wireless Controller:** confirm = **B** (the right face button) or
  **Start/Menu**; **A** (bottom) is *Back*.
- **DualSense:** confirm = **Circle** (right face button) or **Options/Start**;
  **Cross** (bottom) is *Back*.
- In the fight, nothing changes: the four attack buttons stay where they are.

**Pros:** zero risk; nothing to install; never breaks; never needs redoing after
a pad reconnect or a RetroArch update; costs nothing in the fight.
**Cons:** fights 20+ years of "the bottom button is OK" muscle memory every
session; the user *reported* this as a bug, so "just retrain your thumb" is a
weak answer on its own. Best paired with (e).

### (b) A core remap that swaps RetroPad A(8) ↔ B(0)

**Where the file goes.** The core's `library_name` is `dolphin-emu`
(`Main.cpp:162`), and RetroArch names remap folders/files after `library_name`
(same as the existing `config/remaps/MAME/MAME.rmp`). `input_remapping_directory`
is `config/remaps`. So the **core remap** is:

```
~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/dolphin-emu.rmp
```

**Exact `.rmp` contents** (swap only, Player 1):

```
input_libretro_device_p1 = "1"
input_player1_analog_dpad_mode = "0"
input_player1_btn_a = "0"
input_player1_btn_b = "8"
```

**Key semantics** (verified in `libretro/RetroArch`,
`configuration.c` → `input_remapping_load_file`, and the runtime loop in
`input/input_driver.c` ~7626–7690,
<https://github.com/libretro/RetroArch/blob/master/configuration.c>):

- The `.rmp` keys are `input_player<N>_btn_<name>` where `<name>` ∈
  `b y select start up down left right a x l r l2 r2 l3 r3` (the `key_strings`
  table in `input_remapping_load_file`). The index of `<name>` in that table is
  the **physical RetroPad id** whose behaviour you are overriding
  (`a` = index 8, `b` = index 0, …). `input_libretro_device_p1` is a *separate*
  key and is **not** how you swap face buttons.
- The **value** is the RetroPad id to *emit* when that physical button is pressed.
- Runtime: `for j in 0..15: remap = input_remap_ids[port][j];
  if physical_button[j] pressed and j != remap and remap != UNMAPPED:
  set output bit remap` — i.e. `input_player1_btn_b = "8"` means "physical id 0
  now emits id 8", `input_player1_btn_a = "0"` means "physical id 8 now emits
  id 0". The originals are cleared, so it is a true swap, not an overlay.
- Requires `input_remap_binds_enable = "true"` (already set). Loads on next
  content load / core restart; no full RetroArch restart needed.

**Result in menus:** physical A / Cross → id 8 → GameCube A → **confirm**;
physical B / Circle → id 0 → GameCube B → Back. This also lines the core's menus
up with the user's existing `menu_swap_ok_cancel_buttons = "true"` (bottom = OK
in RGUI).

**Effect on in-match fight controls** (the important trade-off):

| face button | GC attack **now** | GC attack **after A↔B swap** |
|---|---|---|
| physical A / Cross (bottom) | GC **B** | GC **A** |
| physical B / Circle (right) | GC **A** | GC **B** |
| physical X / Square (left)  | GC **Y** (unchanged) | GC **Y** |
| physical Y / Triangle (top) | GC **X** (unchanged) | GC **X** |
| R1 → GC Z (throw), triggers → GC L/R (style / block) | unchanged | unchanged |

So the swap permanently trades which of the two lower/right face buttons throws
GC-A vs GC-B attacks. Block (right trigger), throw (R1) and change-style (left
trigger) are untouched. It is a symmetric relearn of two of four attack buttons —
**acceptable only if the user actively wants it.** For a player who fights by feel
and has already built muscle memory on the current layout, this is a poor trade
for a menu that is used ~15 seconds per session.

If the user *does* adopt the swap and wants the face buttons to also read as a
"real GameCube face layout" (physical letters matching GC letters), add:

```
input_player1_btn_x = "1"
input_player1_btn_y = "9"
```

(physical Y/Triangle → RetroPad Y → GC Y; physical X/Square → RetroPad X → GC X).
This is *more* relearning and the GameCube's face cluster (Y on top, big A
centre-bottom, B left, X right) never matched an Xbox/PS diamond anyway — advise
against unless asked.

For 2-player local versus, repeat the two lines with `input_player2_`.

**Pros:** the bottom button confirms, matching the user's instinct and the RGUI
setting; one file; survives pad reconnect and RetroArch updates (lives in
`config/remaps/`, not pad-keyed); shippable by the accessibility project.
**Cons:** changes the fight controls for **every** GameCube/Wii game run through
this core, not just MK:DA; needs the user to relearn two attack buttons; invisible
once set (a future confused debugging session won't expect it).

### (c) A content (game-specific) remap — MK:DA only

Yes, `dolphin_libretro` supports per-content remaps — remaps are a **frontend**
feature (RetroArch), core-agnostic, and this core sets `input_descriptors =
"true"` so the Controls menu is fully populated. Precedence (most specific wins),
from `config_load_remap` in `configuration.c`:

1. **game** remap: `config/remaps/dolphin-emu/<content-filename-without-extension>.rmp`
2. **content-directory** remap: `config/remaps/dolphin-emu/<containing-folder-name>.rmp`
3. **core** remap: `config/remaps/dolphin-emu/dolphin-emu.rmp`
4. core input binds (no file)

So the MK:DA-only fix is the **same four lines as (b)** but saved as the game's
name, e.g.:

```
~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/Mortal Kombat - Deadly Alliance (USA) (Rev 1).rmp
```

The exact basename must match the content file RetroArch loads (it strips only
the final extension — `Foo.nkit` → `Foo`, `Foo.rvz` → `Foo`). Because that name
depends on the user's own dump, the robust way to create it is **in RetroArch**:
set the two binds in Quick Menu → Controls, then Quick Menu → Controls → Manage
Remap Files → **Save Game Remap File** (it writes the correctly-named file
itself, as a longer but equivalent enumeration of every bind).

**Pros:** all of (b)'s menu benefit; the fight-control change is confined to
MK:DA, so every other GameCube game the user ever runs is untouched; cleanly
scoped to exactly what the accessibility project is about.
**Cons:** still relearns two MK:DA attack buttons; filename fragility unless
generated in-app; a project installer can't reliably pre-place it without knowing
the user's ROM filename (mitigate: installer places the **core** remap, or prints
the "Save Game Remap File" steps).

### (d) Edit the pad autoconfig (`input_a_btn` / `input_b_btn`)

Swap the two lines in
`~/Library/Application Support/RetroArch/autoconfig/mfi/Xbox Wireless Controller.cfg`
(and the DualSense file):

```
input_b_btn = "8"      # was "0"
input_a_btn = "0"      # was "8"
```

**Pros:** the bottom button becomes RetroPad A everywhere.
**Cons — worse than a remap on every axis:**
- Affects **every core and the RetroArch menu itself**, not just Dolphin — it
  changes confirm/cancel in RGUI, in every emulator, in the OCR-tool workflow.
- Directly fights the user's `menu_swap_ok_cancel_buttons = "true"` (that setting
  assumes the standard RetroPad layout).
- RetroArch ships autoconfig-profile updates via the Online Updater; an update
  can **overwrite** the edited file, silently reverting the fix.
- Keyed to the exact device name string — a firmware/OS change that renames the
  pad, or a different controller, silently gets the stock mapping.
- The blind user cannot easily notice "my edit got reverted".

Not recommended.

### (e) Have the talking-menu daemon speak a one-time hint

The daemon already speaks the menu name on entry
(`menu_reader.py:219-220`, `A.MENU_STRUCTS[menu_def][0]` → "Main menu"), and
post the `BUG-menu-selection.md` fix it only does so when the menu is genuinely
interactive (`game_state == 11`) and has been stable for two polls. Adding a
corrective hint the first time the main menu appears in a session is a
**reasonable and low-cost addition**:

> "Main menu. Press Start to choose an item. The bottom face button goes back."

Sketch (not applied) — in `MenuReader.__init__` add `self._said_confirm_hint =
False`; in `narrate()` where the menu name is spoken:

```python
elif ctx == Context.MENU and s["menu"] and s["menu"]["menu_def"] in A.MENU_STRUCTS:
    name = A.MENU_STRUCTS[s["menu"]["menu_def"]][0]
    if s["menu"]["menu_def"] == A.MODE_SELECT_DEF and not self._said_confirm_hint:
        name += ". Press Start to choose an item. The bottom face button goes back."
        self._said_confirm_hint = True
    self.say.say(name)
```

**Pros:** zero risk to the fight controls; no RetroArch config; survives pad
reconnects and RetroArch updates; entirely within the accessibility project's
scope (code + README line); teaches the one rule that works on every pad ("Start
selects"); the daemon is the natural place to communicate this to a blind user
since it is already the thing narrating the menu.
**Cons:** advisory only — the daemon is deliberately read-only (it does **not**
use `network_remote`; the installers now force that off), so it cannot *fix* the
input, only tell the user; the user still has to act against habit; the hint is
noise for anyone who already knows.

### (f) A core-level OK/cancel swap — does one exist?

**No.** `menu_swap_ok_cancel_buttons` (config) / "Menu Swap OK & Cancel Buttons"
(a.k.a. the idea behind `input_menu_swap_ok_cancel`) affects **only RetroArch's
own menu driver** — RGUI, XMB, Ozone, MaterialUI. Verified: it never touches
`libretro_input_binds` or the remap tables; the core only ever receives raw
RetroPad button ids via `input_state_cb`, and RetroArch has **no concept of
"confirm" for content**. There is no per-core or per-content OK/cancel swap. The
only frontend mechanism that changes what the *core* sees is the input remap
subsystem (options b/c). (libretro docs, Overrides & Remaps:
<https://docs.libretro.com/guides/overrides/>; input & controls glossary:
<https://docs.libretro.com/guides/input-and-controls/>.)

---

## 3. Recommendation

**Primary fix: (e) + (a) — spoken hint from the daemon, plus a README button table.**

Rationale for a blind player who navigates by ear and fights by feel:

- The menu is touched for seconds per session; the fight is the whole game. A
  remap (b/c) fixes the menu but **permanently moves two of four attack buttons**,
  which is the wrong thing to disturb for a by-feel fighter who already has
  muscle memory.
- "Press **Start** to select" is one rule, works on the Xbox pad and the
  DualSense identically, is already tested, and collides with nothing on the
  MK:DA menus.
- The daemon is already narrating the menu, already knows when the menu is live,
  and is read-only by design — a spoken hint is the exact shape of help it can
  give. Nothing to install, nothing to re-do after a pad reconnect or a
  RetroArch update, zero effect on the fight.
- It is squarely in the accessibility project's scope: a ~6-line code change plus
  a README line.

**Fallback: (c) — a MK:DA-only game remap that swaps RetroPad A(8) ↔ B(0)**, for
the user *if they decide* they'd rather have the bottom button confirm and accept
relearning GC-A/GC-B attacks. Game-scoped (not core-scoped) so no other GameCube
game is affected. Ship it as: (1) the four-line file below, or (2) instructions
to generate it via RetroArch's "Save Game Remap File", plus a README section and
an opt-in `--swap-ab` step in the installers. It survives pad reconnects and
RetroArch updates (lives in `config/remaps/`, not pad-keyed); its only cost is
the deliberate relearn and the fact that it's invisible once set.

Do **not** use (d) (autoconfig edit): global blast radius, fights the user's RGUI
setting, and RetroArch's Online Updater can silently revert it.

---

## 4. Exact files for the recommended fix — ready to apply, NOT applied

### 4.1 Primary — daemon hint (`menu_reader.py`)

Two edits, no new files:

**a. `MenuReader.__init__`** (around line 57, with the other instance state) — add:

```python
        self._said_confirm_hint = False
```

**b. `MenuReader.narrate`** (lines 219–220) — replace:

```python
            elif ctx == Context.MENU and s["menu"] and s["menu"]["menu_def"] in A.MENU_STRUCTS:
                self.say.say(A.MENU_STRUCTS[s["menu"]["menu_def"]][0])
```

with:

```python
            elif ctx == Context.MENU and s["menu"] and s["menu"]["menu_def"] in A.MENU_STRUCTS:
                name = A.MENU_STRUCTS[s["menu"]["menu_def"]][0]
                if s["menu"]["menu_def"] == A.MODE_SELECT_DEF and not self._said_confirm_hint:
                    name += (". Press Start to choose an item. "
                             "The bottom face button goes back.")
                    self._said_confirm_hint = True
                self.say.say(name)
```

**c. `README.md`** — add to the "Play" section / a new "Controls" note:

> **Choosing a menu item:** press **Start**. On the menus, the bottom face button
> (Xbox **A** / PlayStation **Cross**) is wired to GameCube **B**, which is
> *Back* — pressing it on the main menu drops you to the attract screen and
> replays the intro. Use **Start**, or the *right* face button (Xbox **B** /
> PlayStation **Circle**), to confirm. In a fight the four attack buttons are
> unaffected.

### 4.2 Fallback — MK:DA-only remap

Create (do **not** create yet):

```
~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/<MK:DA content filename without extension>.rmp
```

Contents:

```
input_libretro_device_p1 = "1"
input_player1_analog_dpad_mode = "0"
input_player1_btn_a = "0"
input_player1_btn_b = "8"
```

(Add `input_player2_btn_a = "0"` / `input_player2_btn_b = "8"` and
`input_player2_analog_dpad_mode = "0"` if 2-player local versus is wanted.)

The `config/remaps/dolphin-emu/` directory does not exist yet and must be
created. If the exact content filename is uncertain, instead set those two binds
in Quick Menu → Controls and use **Save Game Remap File**, which writes the
correctly-named file automatically.

A **core-wide** version (affects all GameCube/Wii games in this core) would be
the identical contents at
`~/Library/Application Support/RetroArch/config/remaps/dolphin-emu/dolphin-emu.rmp`.

Prerequisite already satisfied: `input_remap_binds_enable = "true"` in
`retroarch.cfg`.

---

## Sources

- libretro/dolphin — RetroPad→GameCube input mapping:
  `Source/Core/DolphinLibretro/Input.cpp`
  <https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Input.cpp>
  (input descriptors ~L116–141; `RETRO_DEVICE_JOYPAD` inputs ~L396–412;
  `UpdateGCMappings` GameCube pad binding ~L1367–1417)
- libretro/dolphin — core `library_name`:
  `Source/Core/DolphinLibretro/Main.cpp:162`
  <https://github.com/libretro/dolphin/blob/master/Source/Core/DolphinLibretro/Main.cpp>
- libretro/RetroArch — remap file format & precedence:
  `configuration.c` → `input_remapping_load_file` (`key_strings` table) and
  `config_load_remap` (game / content-dir / core precedence)
  <https://github.com/libretro/RetroArch/blob/master/configuration.c>
- libretro/RetroArch — remap runtime (swap semantics):
  `input/input_driver.c`, gamepad-remapping loop (~L7626–7690)
  <https://github.com/libretro/RetroArch/blob/master/input/input_driver.c>
- libretro docs — Overrides & Remaps (game/folder/core `.rmp` hierarchy):
  <https://docs.libretro.com/guides/overrides/>
- libretro docs — Input and Controls (menu swap OK/cancel is a menu-driver
  setting only): <https://docs.libretro.com/guides/input-and-controls/>
- libretro docs — Dolphin core: <https://docs.libretro.com/library/dolphin/>
- Dolphin standalone default GC controller mapping (position-based):
  RetroBat wiki "Dolphin controller mapping"
  <https://wiki.retrobat.org/controllers/specific_mapping/dolphin-controller-mapping>
- Local: `~/Library/Application Support/RetroArch/autoconfig/mfi/Xbox Wireless Controller.cfg`,
  `DualSense Wireless Controller.cfg`; `.../config/remaps/MAME/MAME.rmp`;
  `.../info/dolphin_libretro.info`; `.../config/retroarch.cfg`;
  repo `menu_reader.py`, `mkda_addrs.py`, `docs/BUG-menu-selection.md`.
