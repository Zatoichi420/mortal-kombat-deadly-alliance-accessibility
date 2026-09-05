# Dolphin / GameCube screen-reader accessibility — modding landscape

Scope: MK:DA has NO existing accessibility mod. GMKE5D = NTSC-U GameCube (Nov 2002).
Active RE effort for this game family: cScarletter/MK-3D-Era-Decompilation
(https://github.com/cScarletter/MK-3D-Era-Decompilation). TCRF documents leftover debug
material + unused text: https://tcrf.net/Mortal_Kombat:_Deadly_Alliance_(PlayStation_2,_Xbox,_GameCube)

## 1. Dolphin scripting / memory access

### Official Dolphin (master, 2026)
- NO built-in Lua/Python scripting API. Still.
- MemoryWatcher (built in; macOS/Linux via Unix domain sockets, not Windows). Watches a
  user-supplied address list, streams every change to a socket at
  `~/.dolphin-emu/MemoryWatcher/MemoryWatcher`, polls every ~2 ms. Config:
  `MemoryWatcher/Locations.txt`. Used by SmashBot/Project-M tooling.
  Source: Source/Core/Core/MemoryWatcher.cpp / .h
- `dolphin-tool` CLI bundled in Dolphin.app — convert/extract ISO/RVZ/WIA/GCZ/WBFS, dump
  disc filesystem.
- Native Gecko / Action Replay engine + On-Frame RAM "Patches" tab — no external loader.

### Community scripting forks

| Fork | Lang | API | macOS ARM? |
|---|---|---|---|
| Felk/dolphin "Python Scripting Preview 4" (Dec 2025) https://github.com/Felk/dolphin | Python 3 | `from dolphin import memory / event`; `await event.frameadvance()`; memory-breakpoint callbacks (addr, value, is_write) | NO prebuilt. Only Windows x86-64 Python externals bundled. Building on macOS ARM = supply your own ARM Python externals. Non-trivial. |
| got4n/dolphin-pycore | Python | same | same limitation |
| SwareJonge/Dolphin-Lua-Core | Lua | Tools -> Execute Script; RAM r/w, frame hooks | Windows only; core stuck ~Dolphin 5.0 (old). TASLabz/dolphin-lua-core marked obsolete. |
| TwitchPlaysPokemon/dolphinWatch | TCP | socket memory API | unmaintained, old core |
| dmang-dev/mcp-dolphin | MCP over Felk fork | memory r/w, controller, savestate | inherits Windows-only |

Bottom line: no out-of-the-box scripted Dolphin on Apple Silicon in 2026. In-emulator route
on this Mac = MemoryWatcher (already in the Mac build) or external hook.

### Dolphin Memory Engine (aldelaro5) — the RE tool
GUI RAM scanner/editor/viewer for a running Dolphin. Latest release 2026.06.25. Ships a
UNIVERSAL macOS binary (Apple Silicon + Intel) since 2026.05.06.
https://github.com/aldelaro5/Dolphin-memory-engine/releases
Use it to FIND addresses (screen ID, cursor index, string-table pointer). No automation/export.

### py-dolphin-memory-engine — external live read/write from Python
https://github.com/randovania/py-dolphin-memory-engine  /  PyPI `dolphin-memory-engine`
Hooks a running Dolphin process, reads/writes emulated RAM from Python. Prebuilt wheels for
Windows, Linux, macOS ARM64 + x86_64 (Py 3.9-3.13). On macOS REQUIRES a custom code
signature (codesign + debugger entitlement, same dance as Dolphin Memory Engine repo) so it
can attach to Dolphin. This is the main Mac friction point. Used in production by Randovania
for live Metroid Prime multiworld on Dolphin — exact "external tool polls Dolphin RAM
continuously and reacts" pattern. (PyPI long-description says "macOS not supported" but the
wheels + Randovania README contradict it — treat as supported-with-codesigning.)

### libmelee — proof the pattern works on a GameCube game
https://github.com/altf4/libmelee — external Python reads frame-by-frame live game state
from Slippi-Dolphin over a socket, injects controller input, fast enough for real-time AI.
Melee is a GameCube title. Direct prior art.

### Speaking from a watcher on macOS
- `/usr/bin/say` (what RetroArch's narrator uses on macOS)
- pyobjc -> AVSpeechSynthesizer / NSSpeechSynthesizer
- POST text to the existing local TTS server on port 4404 (one voice pipeline for everything)

## 2. Prior-art console screen-reader mods

| Project | Technique | Notes |
|---|---|---|
| OoT/MM "Practice ROM" / gz (glankk) | ROM hack / in-game trainer overlay | NOT a TTS/screen-reader mod. OoT blind-playability = audio cues + RetroArch OCR. |
| Metroid Prime narration | built into JP/PAL retail (toggle); Remastered re-exposed it | Randovania reads menu/inventory state via py-dolphin-memory-engine RAM hooks |
| RetroArch AI Service / Narrator | screen OCR -> speak via OS TTS | macOS backend = `say`. Works with dolphin_libretro. |
| AccessMods org (Phoenix Wright Trilogy, DDLC+, Unity a11y lib) | in-process hook (BepInEx/MelonLoader for Unity). On UI focus change, grab label string, push to screen reader via Tolk/UniversalSpeech/SAPI | all PC titles; the PATTERN (hook focus event -> resolve label -> speak) is what to replicate |
| Skullgirls | integrated Tolk | game passes each focused UI element label to the running screen reader |

General "cursor -> label -> speech" recipe, two forms for an emulated console game:
1. In-process hook (mod code inside the game): intercept menu/redraw routine, read cursor
   index + game's string table, format, speak. Highest fidelity. Needs Gecko/ASM injection
   or DOL patch.
2. External RAM watch (tool outside): watch `currentScreenID`, `menuCursorIndex`,
   maybe `pointerToActiveStringTable`. Either read the string out of emulated RAM, or index
   into a hand-authored label table per screen. Speak on change, with debounce.

### TTS abstraction landscape
- Tolk — Windows only (NVDA/JAWS/SAPI). https://github.com/dkager/tolk
- AccessKit — cross-platform UI tree -> OS a11y APIs. https://accesskit.dev — overkill here.
- speech-dispatcher/libspeechd — Linux only.
- CrossSpeak — C# unified wrapper (Tolk/libspeechd/libspeak-mac). https://github.com/khanshoaib3/CrossSpeak
- On macOS for a single-user tool: just `say` / AVSpeechSynthesizer / the :4404 server. No
  abstraction layer needed.

## 3. ISO / DOL patching for GameCube

### Extract & rebuild the disc (macOS ARM)
- nkit2iso (DonMikone) — Go CLI, brew-installable, converts .nkit.iso -> bit-exact plain
  ISO, CRC-verified. BEST first step for the nkit source. https://github.com/DonMikone/nkit2iso
- Original NKit — Windows/.NET only (Wine/mono).
- `dolphin-tool` (in Dolphin.app) — convert ISO<->RVZ<->GCZ<->WIA, verify, extract filesystem.
- Wiimms ISO Tools (`wit`) — macOS builds; `wit EXTRACT` / `wit COPY`.
- GCFT (GameCube File Tools) by LagoLunatic — cross-platform GUI to browse/extract/replace
  files in a GCM/ISO incl. main.dol.

### Extract main.dol & disassemble PowerPC
- decomp-toolkit (`dtk`, encounter/Luke Street) — Rust, cross-platform, current standard.
  Splits DOL + REL, emits an ELF for Ghidra. Full Gekko/Broadway paired-singles support.
  https://github.com/encounter/decomp-toolkit
- Ghidra — import DOL via GameCube/DOL loader, or import the dtk ELF. Language
  `PowerPC:BE:32:Gekko_Broadway:default`.
- Supporting: ppcdis, dol2asm, m2c (PPC->C), devkitPPC. MKDA-specific:
  https://github.com/cScarletter/MK-3D-Era-Decompilation

### Injecting custom PowerPC into a running game
- Gecko `C2` codetype = "insert instructions" (branch from injection point to codehandler
  free space, run PPC, return). `C0` = standalone PPC subroutine. Code handler at 0x80001800.
  Refs: https://github.com/NicholasMoser/Naruto-GNT-Modding/blob/main/general/docs/guides/gecko_codetype_documentation.md
  tutorial https://github.com/AlexanderHarrison/HOW-TO-WRITE-GECKO-CODES
  assembler https://github.com/pyorot/gecko-compiler
  DOL injector https://github.com/AndrewHanSolo/GamecubeCodeInjector
- "Write current menu string to a fixed RAM address": very feasible. Small injected routine
  hooked into menu-draw / cursor-update code computes the pointer to the highlighted label
  and memcpy's the string (or stores pointer + incrementing "changed" counter) into an
  unused scratch region (low MEM1, padding after code handler, spare global). External
  reader polls that fixed address, speaks on counter change. Exact strings, zero OCR error.
- Deliver via game INI (`GMKE5D.ini`) `[Gecko]` / `[ActionReplay]` / `[OnFrame]` sections,
  editable in Dolphin GUI. No external loader, no disc rebuild for iteration. Bake into
  main.dol + rebuild ISO only to "ship".
- Riivolution / GCLoader: Wii-only / physical-hardware. Not relevant to Dolphin GC. The
  Gecko/AR/On-Frame INI mechanism IS the Dolphin equivalent.

## 4. Path of least resistance — 3 approaches, in order to pursue

### A. Immediate — RetroArch AI Service (screen OCR) on dolphin_libretro
Effort ~0 (already set up on this Mac, V/R3 key). Failure modes: OCR latency (~0.5-2 s,
manual keypress not auto-on-move), OCR errors on stylized fonts, no semantic structure
(can't tell highlighted item, can't say "3 of 7"), can't see off-screen list entries.
Good stopgap + for in-match / story text. Weak for menus.

### B. THE REAL SOLUTION — external RAM watcher + hand-built label map + TTS
Effort: moderate. A few evenings with Dolphin Memory Engine to map menu state, then a small
polling script. Tools (macOS ARM):
- Dolphin Memory Engine universal build (find addresses)
- py-dolphin-memory-engine (live reader; macOS ARM wheels, needs codesign step) OR Dolphin's
  built-in MemoryWatcher socket (config-only, avoids codesign) OR RetroArch READ_CORE_MEMORY
- speech via say / AVSpeechSynthesizer / port 4404
Prior art to copy structurally: libmelee, Randovania's Dolphin backend.
Failure modes: must RE the menu-state addresses; labels mostly prerendered textures so
hand-write label lists per screen; pointers move on menu-module load (may need pointer
chains); version/region-specific (fine, one disc); debounce held D-pad; py-DME codesign.

### C. Highest ceiling — Gecko/ASM injection publishes active string, thin external reader
Effort: highest (PPC RE in Ghidra). Payoff: exact strings + correct semantics everywhere
incl. scrolling lists / dynamic text. Tools: nkit2iso -> ISO; dtk + Ghidra
(PowerPC:BE:32:Gekko_Broadway); gecko-compiler / GamecubeCodeInjector; deliver via
GMKE5D.ini [Gecko]; external reader as in B. MK-3D-Era-Decompilation + TCRF as head starts.
Failure modes: the RE is the whole project; wrong hook crashes; need genuinely-unused
scratch address; slow iterate loop; bake into main.dol for real hardware.

Suggested: A now for usable access; B as the daily driver; promote individual stubborn
screens to C only where A and B both prove too fragile. All three feed the same TTS sink.

## Sources
- Dolphin MemoryWatcher: Source/Core/Core/MemoryWatcher.cpp ; https://github.com/altf4/SmashBot/issues/23
- Felk Python Dolphin: https://github.com/Felk/dolphin ; https://tasvideos.org/Forum/Topics/22105
- Dolphin Memory Engine: https://github.com/aldelaro5/Dolphin-memory-engine/releases
- py-dolphin-memory-engine: https://github.com/randovania/py-dolphin-memory-engine
- libmelee: https://github.com/altf4/libmelee ; https://libmelee.readthedocs.io/
- RetroArch AI Service: https://docs.libretro.com/guides/ai-service/
- AccessMods: https://github.com/AccessMods ; Tolk: https://github.com/dkager/tolk
- nkit2iso: https://github.com/DonMikone/nkit2iso
- decomp-toolkit: https://github.com/encounter/decomp-toolkit
- Gecko codes: https://github.com/AlexanderHarrison/HOW-TO-WRITE-GECKO-CODES
- MKDA: https://github.com/cScarletter/MK-3D-Era-Decompilation ; https://tcrf.net/Mortal_Kombat:_Deadly_Alliance_(PlayStation_2,_Xbox,_GameCube)
