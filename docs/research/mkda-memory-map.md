# MK: Deadly Alliance — reverse-engineering / memory-map intel

## 0. Platform / ID reference

| Platform | ID | Notes |
|---|---|---|
| GameCube USA | **GMKE5D** (our target). Exe `DOL-GMKE5D`. Internal version 0.223 | EU=GMKP5D; German=GMKD5D ("54A"), v0.243G |
| PS2 USA | SLUS-20423 (`SLUS_204.23`), build 2002-10-18, rev 1.03 | PAL=SLES-50717 |
| Xbox USA | default.xbe, v0.223 | |
| GBA USA | AGB-AXDE-USA | different 2D codebase, not useful |

## 1. Cheat codes as a RAM map

### 1a. PS2 (SLUS-20423) — DECRYPTED raw codes
From PS2-Home user Kooler186 (https://www.ps2-home.com/forum/viewtopic.php?t=3466), converted
from CodeBreaker v10 with Omniconvert. Prefix 2=32-bit write, 1=16-bit, 0=8-bit, D=16-bit
equal-to conditional. Literal EE main-RAM addresses.

In-match / fight state (active "match" struct near 0x0040Axxx):
| Address | Size | Meaning |
|---|---|---|
| 0x0040A394 | float | P1 health (1.0 = full) |
| 0x0040A390 | float | P2 health |
| 0x0040A396 | u16 | P1 health compare word (gate: `D040A396 00003F80`) |
| 0x0040A392 | u16 | P2 health compare word |
| 0x0040A38C | u32 | P1 round wins |
| 0x0040A388 | u32 | P2 round wins |
| 0x0040AF10 | u32 | Arcade-mode battle index (0x0A = final) — a mode/progress counter |
| 0x0040A210 | flag | "minigame after only 1 match" |
| 0x0040AE54 / 0x0040AE50 | float | Test Your Might threshold P1 / P2 |
| 0x00323AD0 | float | invisible-fighters toggle (3FE00000) |
| 0x00323B40 | u32 | shadow-fighters toggle |

Unlock bitfields (menu-visible state):
| Address | Meaning |
|---|---|
| 0x00409024 | Unlock-all-characters bitmask (FFFFFFFF) — character-select reads this |
| 0x00527654 | Unlock-all-outfits bitmask |

"Currently loaded profile" block (contiguous ~0x00550Exx-0x00551xxx):
| Address | Meaning |
|---|---|
| 0x00550F08-0x00550F5C (21 words) | costume/arena/koncept/extra unlock bitmasks |
| 0x00551040 | "have all character endings" bitmask |
| 0x00550E90 / E94 / E98 / E9C / EA0 / EA4 | Koin counts: platinum/onyx/sapphire/jade/ruby/gold (0x270F = 9999) |

Per-character config table (reveals roster struct stride): "1-button special / fatality"
enables from 0x003AECCC (Blaze) through 0x003AF69C (Shang Tsung), one contiguous block per
character, ~0x80-0xB0 bytes apart. Internal roster order:
Blaze, Mokap, Kitana, Sonya, Kung Lao, Cyrax, Raiden, Nitara, Johnny Cage, Jax, Scorpion,
Quan Chi, Sub-Zero, Kenshi, Drahmin, Li Mei, Bo' Rai Cho, Frost, Mavado, Hsu Hao, Kano,
Reptile, Shang Tsung.

Code patches (instruction addrs in 0x001xxxxx-0x0026xxxx text seg): 0x0026BBF0 (infinite
koin usage), 0x0014E8B4 (no fatality time), 0x00424FA8/0x00425DD4 (impale P1/P2).
Mastercode hook 0x00115A74.

### 1b. GameCube (GMKE5D / GMKD5D) — raw codes
Addresses = 0x80000000 + offset. Source: Ralf@gc-forever
(http://www.gc-forever.com/forums/viewtopic.php?t=2542) + TCRF.

| Raw code | Address | Meaning |
|---|---|---|
| `044186A0 00000008` | 0x804186A0 | **P1 selected character slot** (write 8 = Moloch). P2 variant exists. |
| `004184EB 00000016` (USA) | 0x804184EB (u8) | **Selected stage/arena ID** (USA build) |
| `04418194 000000xx` (German) | 0x80418194 (u8) | Stage ID on German build |
| `00419983 00000001` | 0x80419983 (u8) | debug: hitbox display flag |
| `00419987 00000001` | 0x80419987 (u8) | debug: hitbox hide flag |
| `...04419998 00000001` | 0x80419998 | **debug tick-display flag** (TCRF "Show Ticks") |
| `0406442C 41820018` | 0x8006442C | patch: show game version on Options screen |
| `0409C294 / 0409C2B4 / 04090B44 / 04090ADC` | 0x8009xxxx | "hit from anywhere" instruction patches |
| `040D29E0 ...` (8 lines) | 0x800D29E0+ | unlock 7 cut Konquest training missions |

GameCube stage-ID table (0x80418194 German / analogous byte USA):
00 Acid Bath, 01 Wu Shi Academy, 02 House of Pekara, 03 Dragonfly, 04 Drum Arena,
05 Quan Chi Fortress, 06 Lin Kuei Temple, 07 Kuatan Palace, 09 Lost Tomb, 0A Portal,
0B Lung Hai Temple, 0C Palace Grounds, 0D Shang Tsung's Palace, 0E Lava Shrine,
0F Sarna Ruins, 10 Nethership, 11 Moloch's Lair, 0x16 unused Studio.

**KEY TAKEAWAY: GameCube match-setup struct lives in the 0x80418000-0x80419000 page.**
Stage ID ~0x804184EB, P1 char 0x804186A0, debug flags 0x8041998x. The menu / character-
select cursor is very likely in this same page.

"Show Ticks" (0x80419998) behavior: value ~0 while in a menu, jumps to ~200,000 in a fight.
=> ready-made menu-vs-fight discriminator (or find the real screen-state enum the same way).

Encrypted AR codes on almarsguides.com / etherealgames.com / cheathappens.com ("All
Characters", "Always Test", "Arcade-Final Stage", "Camera Zooms Out") — decrypt via
GameHacking.org GC converter or paste directly into Dolphin (it accepts encrypted AR).
Several will point into the same struct.

## 2. Existing RE projects / tools / TCRF

### Decompilation / RE
- github.com/cScarletter/MK-3D-Era-Decompilation — DA/Deception/Armageddon, all platforms.
  Ghidra-based, started 2024, maintainer active. Holds a Deception disc-content map,
  extracted models, and 2 notes files: "General game notes" (full menu tree) and
  "Interesting finds". No RAM map yet.
- github.com/ermaccer/MK-Deception-Decompilation

### Tools (all by ermaccer, the MK 3D-era modding authority)
| Repo | Purpose |
|---|---|
| ermaccer/SSFExplorer | build/extract .ssf archives + texture export; extracts MKDA.pak from PS2 games |
| ermaccer/MortalKombat.PAKTool | extract/create MKDA.PAK |
| ermaccer/MortalKombat.Tools | paktool, ssfx, toceditor (TOC tables), texconv |
| ermaccer/mkoasm | view/extract/DECOMPILE .MKO (.cmo) game-logic scripts. MKDA: view/extract/decompile OK, compile PS2-only |

### The Cutting Room Floor
https://tcrf.net/Mortal_Kombat:_Deadly_Alliance_(PlayStation_2,_Xbox,_GameCube)
- No player-facing debug MENU on retail consoles — just individual displays (version,
  ticks, collision boxes), all via AR codes above.
- Internal names table (strings in the exe + asset filenames):
  blind=Kenshi, canvastraining=Wu Shi Academy, CoffinTomb/koffin=The Krypt,
  churchruins=House of Pekara, drunk/drunkenfighter/fatman=Bo' Rai Cho,
  icegirl/subzerette=Frost, icepalace=Lin Kuei Temple, Journey=Konquest, khan=Hsu Hao,
  seabeast=Lung Hai Temple, templeruins=Sarna Ruins, torch=Blaze, vamp_f=Nitara, vortex=Portal.
- MK5BANKS.MMB (Xbox build) lists sound banks incl. character banks c_scorpion.msb etc.,
  `announcr_names.msb` (announcer speaking the roster names), `shell.msb` (front-end/menu audio).
- Engine = RenderWare 3.x (confirmed by embedded $Id: renderware $ CVS strings, "Core built
  at Sep 2 2002"). Shared across DA -> Deception -> Armageddon -> MK vs DC.
- Unused: studio/senateofeldergods/arttool arenas, 7 cut Konquest missions, locked-icon
  graphics for default-unlocked characters.
- NO documented memory layout on TCRF beyond the individual AR codes.

### Community
- mksecrets.net forum f=65 "MK: DA | Deception | Armageddon Modding" — mostly texture/skin/
  model swaps. "Debug menu?" thread f=93&t=45620. "MKDA Xbox/PS Glyphs" Dolphin thread t=49441.
- TRMK forums.

## 3. Engine structure

- Rendering: RenderWare 3.x.
- Game logic / UI: the .MKO (.cmo) script system. **MKDA = first MKO version: FUNCTIONS
  ONLY, NO VARIABLES, "heavily dependent on executable functions for almost everything."**
  So in MKDA most menu/roster logic is hard-compiled in the DOL, not scripts — helps us
  (one binary, stable addresses). Deception moved character/stage tables into scripts; MKDA
  keeps them in the executable.
- Front-end: a separate NTGUI module (Midway "NT GUI" menu system). On PS2 it's NTGUI.ELF;
  on GC linked into the DOL or a .rel. Menu screens, cursor logic, and menu label strings
  likely live here / in the main exe. shell.msb = front-end sound set.
- Archives: .ssf (Midway SSF archive, nestable), packed into MKDA.PAK. .dff = RenderWare
  models, .pss/.PSS = video (.thp on GC). TOC tables in the exe map names -> PAK offsets.
- No UI-description/markup format — menu layout is code + textured art, NOT data-driven.

## 4. Emulation specifics

Dolphin (GMKE5D): wiki says "no reported problems, does not need non-default settings",
Perfect rating, playable since Dolphin 3.0. Dolphin accepts encrypted AR codes AND Gecko
codes directly (INI [ARCodes]/[Gecko] or in-GUI), has built-in Cheat Search + RAM Watch +
debugger. PRIMARY tool for finding the cursor address on the GC version.

PCSX2 (SLUS-20423): NTSC-U pnach key `19 6C E6 B5 58 CC 0D C2 95 62 10 33 F7 71 2C 18 E1 A1
E2 FA`. Widescreen patch in github.com/PS2-Widescreen/OPL-Widescreen-Cheats (`SLUS_204.23`).
Can attach Cheat Engine to pcsx2.exe.

## 5. Disc file system (what holds menu text & fighter names)

GameCube GMKE5D disc, typical layout (mirrors PS2/Deception):
| File | Contents |
|---|---|
| GMKE5D.dol (main exe) | ALL menu/cursor/roster logic for MKDA (scripts thin). Fighter name strings, menu label strings, internal-name table, stage table MOST LIKELY here. |
| NTGUI module | Midway front-end/menu system (separate .ELF on PS2; linked or .rel on GC) |
| MKDA.PAK | master archive; extract w/ ermaccer/MortalKombat.PAKTool or SSFExplorer |
| art/...*.ssf | per-screen/arena archives. Menu backgrounds + many menu labels are PRERENDERED TEXTURES here, not live text. attract.ssf, krypt_art.ssf, studio.ssf, <arena>.ssf |
| sound (SNDSGC/.msb) | announcr_names.msb (spoken roster names), c_<char>.msb, shell.msb (menu SFX) |
| .dff | RenderWare models |
| .pss/.thp | FMV |

Text-extraction path: `strings` / hex editor on the DOL + any NTGUI/.rel; `mkoasm -m mkda`
decompile the .mko files to see which menu actions are scripted.

## 6. Assessment — finding "current menu selection index" by hand

**EASY-to-MODERATE. An afternoon for the raw cursor value. Mapping it to a talking menu is
the bigger job.**

Why easy:
1. Menu cursor = tiny integer (0..N) that changes exactly +/-1 on D-pad up/down. Most
   tractable cheat-search pattern: "unknown value" -> Down -> "increased by 1" -> Up ->
   "decreased by 1". 3-4 iterations isolates it. Dolphin Cheat Search + Cheat-Engine-on-
   PCSX2 do this natively. NO anti-cheat, NO memory encryption, NO ASLR (fixed RAM map,
   single exe, thin scripting).
2. Strong anchors: GC selections cluster in 0x80418000-0x80419000 (0x804186A0 P1 char,
   ~0x804184EB stage, 0x8041998x debug). PS2 match-setup 0x00409000-0x0040B000.
3. Character-select IDs follow known internal roster order (Moloch=8 on GC / the
   0x003AECCC... table order on PS2).
4. "Show Ticks" (0 in menus, ~200k in fights) = ready state discriminator to find a
   "current screen/mode" enum with the same technique.

Why moderate not trivial:
- Need SEVERAL related values: main-menu cursor, submenu cursor(s), CSS P1 cursor, CSS P2
  cursor, "which screen is active" enum.
- CSS may store cursor as a single grid index OR separate row/column; two players; "hovered"
  vs "locked-in" distinction — the HOVERED index is what a talking menu reads, may differ
  from the confirmed-character byte at 0x804186A0.
- Menu labels are mostly PRERENDERED TEXTURES not strings — the tool can't read "ARCADE" /
  "KONQUEST" from RAM near the cursor. Build a static index->label table per screen (menu
  tree content + order is in TCRF and the decomp repo's "General game notes").
- Region/revision differences: lock to GMKE5D.
- Values may sit in a heap/GUI object whose base pointer moves between screen loads. MKDA
  front end is static enough that a flat address usually holds; be ready for a pointer
  chain (Cheat Engine pointer-scan) if not.
- Konquest ("Journey") is 3D free-roam, not a menu — out of scope.

Recommended path:
1. Work on Dolphin/GMKE5D first (best debugger + RAM watch, perfect compat).
2. Cheat-search: main-menu cursor (+/-1), each submenu, CSS P1/P2 hover indices, screen-
   state enum.
3. Cross-check candidates against the 0x80418xxx struct; watch live in RAM Watch while navigating.
4. Hand-author index->label maps from the menu tree + internal-names table.
5. Fighter names: `strings` the DOL for the roster, or reuse announcr_names / internal-name
   ordering, keyed to the CSS index.
6. mkoasm-decompile the .mko + a Ghidra pass on the DOL only if a value won't hold still.
   Coordinate with cScarletter's decomp + ermaccer.

## Link index
- https://github.com/cScarletter/MK-3D-Era-Decompilation
- https://github.com/ermaccer/mkoasm , /SSFExplorer , /MortalKombat.PAKTool , /MortalKombat.Tools
- https://tcrf.net/Mortal_Kombat:_Deadly_Alliance_(PlayStation_2,_Xbox,_GameCube)
- https://gamehacking.org/game/54646 (GC USA) , /game/104313 (PS2 NTSC-U)
- http://www.gc-forever.com/forums/viewtopic.php?t=2542 (GC raw codes)
- https://www.ps2-home.com/forum/viewtopic.php?t=3466 (PS2 decrypted codes)
- https://almarsguides.com/retro/walkthroughs/gamecube/games/mortalkombatdeadlyalliance/actionreplay/us/
- https://wiki.dolphin-emu.org/index.php?title=Mortal_Kombat:_Deadly_Alliance
- https://www.mksecrets.net/forums/eng/viewforum.php?f=65
