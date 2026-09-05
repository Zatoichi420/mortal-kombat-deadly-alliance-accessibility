# Calibration

The addresses in `mkda_addrs.py` are for the **USA disc, `GMKE5D`**. They do not
depend on your OS, your RetroArch build, your ROM filename, or the dump format
(ISO / RVZ / NKit) — only on the game build. If you use that disc, the menu
narration should work out of the box.

Two situations need a check:

## 1. Confirming the character-select address (do this once, ~1 minute)

The menu narration is fully verified. The character-select hover address
(`P1_POS` / `P2_POS`) is derived from the game's own code and matched a live test,
but the automated confirmation was cut short by the game's attract-mode timer, so
please sanity-check it on your first real play:

1. Start MK:DA, go **Arcade → character select**.
2. In a terminal: `python menu_reader.py --probe`
3. Move the roster cursor left/right and watch the `p1pos=` field.
   - It should count with the highlighted portrait, and the daemon should speak
     the right fighter name. If so — **done**.
   - If `p1pos` doesn't move but another field does (`p1c`, `row`, `col`), or the
     spoken name is offset from the portrait: edit `P1_POS` / `P2_POS` (and, if
     the order is wrong, `ROSTER_FALLBACK`) in `mkda_addrs.py`, then restart the
     daemon (`launchctl kickstart -k …` / `systemctl --user restart …` /
     `Restart-ScheduledTask …`).

## 2. A different region / revision (PAL, German, Japan)

PAL (`GMKP5D`), German (`GMKD5D`) and JP (`GMKJ5D`) builds have the same *layout*
but shifted addresses. The daemon detects these and prints a warning. To retarget:

1. Get that disc's `mk5gc_release.elf` (it's a loose file in the disc's root):
   `python tools/gc_extract.py "<your dump>" extract mk5gc_release.elf ./out`
   (works on NKit ISOs; for RVZ, convert to ISO first with Dolphin/`dolphin-tool`).
2. Re-derive the symbols:
   `pip install pyelftools capstone`
   then the snippet in [research/elf-symbols.md](research/elf-symbols.md) prints
   every named variable + address. The names are identical across regions —
   `cursor_position`, `menu_stack`, `main_menu_tbl`, `char_data_tbl`, `p1_pos`, …
3. Put the new addresses in `mkda_addrs.py`. The *mechanism* (menu_stack →
   main_menu_tbl record → menu_def + cursor) is the same; only the numbers move.

## 3. Verifying end to end

- `python menu_reader.py --once` — one snapshot; confirms it can reach RetroArch.
- `python menu_reader.py --probe` — live snapshot ~4×/s; watch fields change as
  you navigate.
- `MK_SPEAK_BACKEND=log python menu_reader.py` — prints every phrase it would
  speak instead of speaking, so you can check wording/timing.

## What was and wasn't verified live (build of 2026-09-05)

| thing | status |
|---|---|
| main menu / Options / Kontent / pause menu narration + "N of M" | **verified live, end to end with speech** |
| screen classification (`menu_on`, `f_psel_initialized`) | verified |
| character-select hover = `p1_pos` → `char_data_tbl` | high confidence (from disassembly + partial live), confirm per §1 |
| Practice / Krypt sub-screens, profile name-entry keyboard | not yet wired — falls through to the OCR key |
