#!/usr/bin/env python3
"""Build the single-file `mkda-reader` binary with PyInstaller.

    pip install pyinstaller
    python packaging/build.py

Output: dist/mkda-reader  (or .exe on Windows).

The daemon is pure standard library, so this is a plain one-file build with no
data files, no hooks, and no external packages. CI runs this same command on
Windows / macOS / Linux runners - see .github/workflows/release.yml.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "mkda-reader"


def main() -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--name", NAME,
        "--noconfirm",
        "--clean",
        # autostart is imported lazily inside a function; name it explicitly.
        "--hidden-import", "autostart",
        "--paths", str(ROOT),
        str(ROOT / "menu_reader.py"),
    ]
    print(" ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
