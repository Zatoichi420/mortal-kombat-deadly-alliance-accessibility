# RetroArch "talking menu" narration for GameCube (dolphin_libretro) — research

## Executive summary

OCR-free architecture is feasible and recommended. `dolphin_libretro` DOES implement the
libretro memory interface: it exposes GameCube MEM1 as `RETRO_MEMORY_SYSTEM_RAM` and via
`RETRO_ENVIRONMENT_SET_MEMORY_MAPS` at guest address `0x80000000`. An external Python
process can poll RetroArch's UDP network-command port for a menu-cursor RAM address and
speak the value on change, bypassing the AI Service and OCR entirely.

## 1. RetroArch network control / command interface

Enable in `retroarch.cfg`:
- `network_cmd_enable = "true"`
- `network_cmd_port = "55355"` (default UDP port)

Plain-text over UDP, one command per datagram:
```
echo -n "READ_CORE_MEMORY 80000000 4" | nc -u -w1 127.0.0.1 55355
```
Docs: https://docs.libretro.com/development/retroarch/network-control-interface/

### Memory commands

| Command | Address space | Notes |
|---|---|---|
| `READ_CORE_MEMORY <addr hex> <numbytes hex>` | System memory map (from SET_MEMORY_MAPS) | PREFERRED |
| `WRITE_CORE_MEMORY <addr hex> <byte> <byte>...` | System memory map | disables cheevos hardcore |
| `READ_CORE_RAM <addr hex> <numbytes hex>` | rcheevos flat space | historically buggy — AVOID |
| `WRITE_CORE_RAM <addr hex> <byte>...` | rcheevos flat space | AVOID |

Response strings (verbatim from libretro docs):
- `READ_CORE_MEMORY` success: `READ_CORE_MEMORY <address> <byte1> <byte2> ...` (space-separated hex)
- `READ_CORE_MEMORY` failure: `READ_CORE_MEMORY <address> -1 <error message>`
  errors: `no memory map defined`, `no descriptor for address`, `no data for descriptor`
- `WRITE_CORE_MEMORY` success: `WRITE_CORE_MEMORY <address> <bytes written>`

Other useful: `VERSION`, `GET_STATUS` (-> `GET_STATUS PLAYING gc,<basename>,crc32=...` or `PAUSED`),
`PAUSE_TOGGLE`, `FRAMEADVANCE`, `SHOW_MSG`, `SAVE_STATE`, `LOAD_STATE`, `FAST_FORWARD`, `RESET`, `QUIT`.

### dolphin_libretro implements the memory interface — CONFIRMED

From core source `Source/Core/DolphinLibretro/Main.cpp` (https://github.com/libretro/dolphin):
- `retro_get_memory_data()` / `retro_get_memory_size()` return real RAM ptr/size for
  `RETRO_MEMORY_SYSTEM_RAM` (`Memory::GetRAM()` / `GetRamSizeReal()`).
- `RETRO_ENVIRONMENT_SET_MEMORY_MAPS` (called in `retro_run`) registers:
  - MEM1 (GameCube main RAM): guest address 0x80000000, size = GetRamSizeReal() (0x1800000 = 24 MB), big-endian, system RAM
  - MEM2 (Wii only): guest address 0x90000000
- Corroborated by RetroAchievements Dolphin work: "Memory addressing now uses MEM1 at 0x8- and MEM2 at 0x9-"
  (dolphin-emu/dolphin PR #12949).

### Address mapping

Pass the native GameCube virtual address. To read GC 0x80xxxxxx send `READ_CORE_MEMORY 80xxxxxx <n>`.
Host offset into RAM buffer = addr - 0x80000000. GC is big-endian and the region is flagged
big-endian, so multi-byte integers return big-endian order (1-byte cursor index is order-independent).

### Known bugs / caveats

1. `READ_CORE_RAM`/`WRITE_CORE_RAM` broke after PR #15912 (issue #16392), fixed in #16396. Use
   `READ_CORE_MEMORY` and sidestep it.
2. Non-contiguous descriptor bug (#13664) — does NOT apply; Dolphin MEM1 is one contiguous 24 MB block.
3. UDP datagram loss on loopback under load — build retry logic into the poller.
4. Memory map registered from `retro_run` — only exists once content is running. Before a game
   boots you get `no memory map defined`.
5. mcp-retroarch (https://github.com/dmang-dev/mcp-retroarch) verified READ_CORE_MEMORY on mGBA,
   Mesen, snes9x, Genesis Plus GX, Mupen64Plus-Next etc. — did NOT test Dolphin. Field-verify.
6. Dolphin core resynced to modern Dolphin ~Oct 2025.

## 2. AI Service automation

### Automatic / polling mode — exists

If the SERVER'S response includes `"auto": "auto"`, RetroArch enters automatic mode: user
presses the AI hotkey once, then RetroArch keeps sending requests on a timer until hotkey
pressed again / menu opened. `"auto": "continue"` keeps polling. `ai_service_poll_delay`
sets the minimum interval. So the port-4404 server could flip RetroArch into hands-free
narration by returning `{"auto":"auto", ...}`.

### Config vars

`ai_service_enable`, `ai_service_url`, `ai_service_mode` (0 Image / 1 Speech / 2 Narrator /
3 Text / combos), `ai_service_source_lang`, `ai_service_target_lang`, `ai_service_pause`,
`ai_service_poll_delay`.

### HTTP contract

- POST to `ai_service_url`
- URL query params: `source_lang`, `target_lang`, `output` (comma-separated: `sound`, `text`, `image`)
- JSON body: `image` (base64 frame), `format` ("png"/"bmp"), `coords` [x,y,w,h],
  `viewport` [w,h], `label` (content id), `state` ({paused, retropad input})
- Response JSON: `image` (b64), `sound` (b64 audio — WAV here), `text` (string),
  `text_position` (1 bottom / 2 top), `press` (retropad buttons to inject), `auto`, `error`

## 3. Built-in accessibility (`accessibility_enable`)

- `accessibility_enable = "true"` + `accessibility_narrator_speech_speed` (1-10).
- Narrates ONLY the RetroArch UI (menu items, dialogs, text entry, position-in-list). On
  macOS shells out to `say`.
- Does NOT read core/game content on its own. Only path from game content to narrator is the
  AI Service in Narrator/Speech mode.

## 4. Cheevos / cheat-search / Lua

- NO Lua or scripting for cores (issue #6454 unimplemented). `libretro_script` is a 3rd-party
  experiment, not in stock builds.
- Cheat Search (Quick Menu -> Cheats -> Start/Continue Search): search by bit-size/value,
  narrow over scans. Only "watch" feature = controller rumble when a found address changes.
  No callback / text output / export. Usable to DISCOVER the cursor address in-place, not as
  a narration source.
- rcheevos memory access only reachable externally via the buggy `READ_CORE_RAM`.
- Best address-finding tool: standalone Dolphin + Dolphin Memory Engine
  (https://github.com/aldelaro5/Dolphin-memory-engine, universal macOS binary since 2026.05.06).

## 5. Recommended architecture — external process polls UDP -> POST to TTS

1. Python opens UDP socket to 127.0.0.1:55355.
2. Every ~100-150 ms send `READ_CORE_MEMORY <cursor_addr> <n>` (1 retry on timeout).
3. Parse hex bytes, track last-known value.
4. On change: index -> label string.
   - Static table: index -> name map per game/menu (simplest, fully reliable).
   - Dynamic: read a second address (pointer to highlighted entry's name string in MEM1),
     then READ_CORE_MEMORY that string (ASCII/Shift-JIS, NUL-terminated).
5. POST string to http://localhost:4404/ or call `say` directly. Optionally `SHOW_MSG` for a caption.
6. Gate on `GET_STATUS` (only narrate when PLAYING) and a menu-state address.

Beats OCR: deterministic (exact names, no OCR errors on stylized fonts), sub-ms latency,
low CPU, leaves V/R3 free for OCR fallback on non-menu screens (dialogue, cutscenes).

Costs: per-game reverse engineering unavoidable (few hours per game with Dolphin Memory
Engine). Address differs by revision/region. Validate reads (printable ASCII, sane length)
before speaking. Handle `no memory map defined` at startup.

## Ranked recommendations

1. PRIMARY: external Python UDP poller -> existing TTS server, `READ_CORE_MEMORY` at
   0x80000000+offset. Per-game index->label table.
2. Keep AI Service / OCR on V/R3 as fallback for free-form on-screen text.
3. Optionally let the TTS server itself do the RAM reads + return `{"auto":"auto"}`.
4. Use standalone Dolphin + Dolphin Memory Engine to discover addresses.
5. DO NOT pursue: Lua (doesn't exist), READ_CORE_RAM/rcheevos (buggy), accessibility_enable
   for game content (UI only).

## Key sources
- https://docs.libretro.com/development/retroarch/network-control-interface/
- https://github.com/libretro/dolphin — Source/Core/DolphinLibretro/Main.cpp
- https://docs.libretro.com/guides/ai-service/
- https://docs.libretro.com/guides/retroarch-accessibility-guide/
- https://github.com/libretro/RetroArch/issues/16392 (READ_CORE_RAM broken)
- https://github.com/dmang-dev/mcp-retroarch (reference Python impl of memory r/w over UDP)
- https://github.com/aldelaro5/Dolphin-memory-engine
