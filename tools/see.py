"""Ask the :4404 server to OCR the current RetroArch frame and return the text.

Uses the AI_SERVICE network command to make RetroArch capture + POST the frame,
then reads the text the server drops at last_ocr.txt. Lets a headless script
'see' which screen the game is on.
"""

from __future__ import annotations

import time

from ra_client import RAClient

LAST_OCR = ("/Users/orlandojohnson/Library/Application Support/"
            "RetroArch/ai-speech-server/last_ocr.txt")


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
