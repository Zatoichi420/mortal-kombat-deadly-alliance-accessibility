"""Ask an OCR helper to read the current RetroArch frame and return the text.

Calibration aid (macOS-oriented). Uses the AI_SERVICE network command to make
RetroArch capture + POST the frame to a local OCR server, then reads the text the
server drops at a file. Requires that server (an Apple-Vision OCR wrapper is in
docs/research/retroarch-memory-interface.md) with a patch to write last_ocr.txt.

    export MKDA_LAST_OCR=/path/to/last_ocr.txt     # default: ./last_ocr.txt
"""

from __future__ import annotations

import os
import time

from ra_client import RAClient

LAST_OCR = os.environ.get(
    "MKDA_LAST_OCR",
    os.path.expanduser("~/Library/Application Support/RetroArch/ai-speech-server/last_ocr.txt")
    if os.path.isdir(os.path.expanduser("~/Library/Application Support/RetroArch"))
    else "last_ocr.txt")


def see(ra: RAClient | None = None, settle: float = 1.8) -> list[str]:
    ra = ra or RAClient()
    try:
        old = open(LAST_OCR).read()
    except OSError:
        old = None
    ra.ai_service()
    for _ in range(int(settle / 0.2) + 1):
        time.sleep(0.2)
        try:
            new = open(LAST_OCR).read()
        except OSError:
            continue
        if new != old:
            return [ln for ln in new.splitlines() if ln.strip()]
    try:
        return [ln for ln in open(LAST_OCR).read().splitlines() if ln.strip()]
    except OSError:
        return []


if __name__ == "__main__":
    for ln in see():
        print(ln)
