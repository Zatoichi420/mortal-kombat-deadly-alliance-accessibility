# Contributing

Thanks for helping make this game playable without sight. Contributions of every
size are welcome — a typo fix, a tested set of addresses for the PAL disc, a new
screen wired up, or just a report that it did or didn't work on your setup.

This is a small project maintained in spare time. Please be patient with review,
and be kind in issues and PRs — see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Things that would genuinely help

| Area | What's needed |
|---|---|
| **Testing on Windows / Linux** | The daemon and installers are written for all three OSes but only macOS is verified. A "it works" or a bug report from Windows/Linux is valuable. |
| **Character-select confirmation** | The `P1_POS` / `P2_POS` addresses need a 60-second live check — see [docs/CALIBRATION.md](docs/CALIBRATION.md) §1. |
| **Other regions** | Addresses for PAL (`GMKP5D`), German (`GMKD5D`), Japan (`GMKJ5D`). The method is in [docs/CALIBRATION.md](docs/CALIBRATION.md) §2 — it's reading a symbol table, not guessing. |
| **More screens** | Practice sub-menus, the Krypt grid, the profile name-entry keyboard, in-match round/health callouts. The menu mechanism in [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) covers the standard menus; these screens use different variables. |
| **Speech backends** | Better interruption on Linux, a `pyttsx3` path, NVDA/Tolk on Windows for people who already run a screen reader. |
| **Other GameCube games** | The whole approach (`ra_client.py` + a per-game `*_addrs.py`) generalises. A sibling repo or a `games/` folder — open an issue to discuss. |

## Development setup

You need RetroArch + the Dolphin core + a legally-obtained MK:DA **USA** disc
(any dump format). See the setup steps in the [README](README.md#setup).

```bash
git clone https://github.com/Zatoichi420/mortal-kombat-deadly-alliance-accessibility
cd mortal-kombat-deadly-alliance-accessibility

# run the daemon straight from the checkout (no install needed for dev)
python menu_reader.py --probe        # live state, no speech
python menu_reader.py                # with speech

# print what it would say, without speaking:
MK_SPEAK_BACKEND=log python menu_reader.py
```

The reverse-engineering / calibration helpers in `tools/` need
`pip install pyelftools capstone` and, for `nav.py`/`calibrate.py`/`verify.py`,
`network_remote_enable = "true"` in `retroarch.cfg`. See [tools/README.md](tools/README.md).

There are no build steps and no dependencies for the daemon itself — it's plain
Python 3.8+ stdlib.

## How the code is organised

- `menu_reader.py` — the daemon: classify the screen, resolve the label, speak on change.
- `ra_client.py` — RetroArch UDP client. Pure sockets, no game knowledge.
- `mkda_addrs.py` — **all** game-specific numbers: addresses, the menu label
  tables, the roster. If you're retargeting a region, this is the only file that changes.
- `speak.py` — cross-platform TTS.
- `tools/` — how the addresses were found (documented, reproducible).
- `docs/` — how it works, calibration, and the raw research.

Keep game-specific constants in `mkda_addrs.py`, host-specific behaviour in
`speak.py` / `install/`, and generic RetroArch plumbing in `ra_client.py`.

## Style

- Match the surrounding code. It's plain Python, `from __future__ import annotations`,
  standard library only in the daemon.
- No new runtime dependencies for `menu_reader.py` / `ra_client.py` / `speak.py`
  without discussing it first.
- Comment *why*, and cite the source when you add an address — a symbol name, a
  disassembly line, or "verified live pressing Down on screen X". Every number in
  `mkda_addrs.py` should be traceable.

## Submitting changes

1. Fork, branch off `main`.
2. Make the change. Test it against a running game if it touches the daemon —
   say what you tested in the PR ("navigated the main menu and Options submenu,
   heard the right labels" / "ran `--probe` on the PAL disc").
3. Open a PR. Fill in the template. Small, focused PRs merge faster.
4. New addresses: include how you verified them, and ideally a short
   `--probe` transcript.

By contributing you agree your work is licensed under the project's
[MIT License](LICENSE).

## Reporting bugs / asking for a screen

Use the issue templates. For a bug, the daemon log
(`~/Library/Logs/mkda-menu-reader.log` / `journalctl --user -u mkda-menu-reader` /
`%LOCALAPPDATA%\mkda-talking-menu\menu_reader.log`) and a `--probe` snippet from
the screen where it went wrong are the most useful things you can attach.

## A note on scope and the game

This project ships **no game code or assets** and never will. It reads values from
memory at runtime. Please don't attach ROMs, disc images, or extracted game files
to issues or PRs — they'll be removed. See the legal note in the [README](README.md#legal).
