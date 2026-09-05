"""Cross-platform interruptible speech for the talking-menu daemon.

Backends, chosen automatically by OS (override with env MK_SPEAK_BACKEND):

  macOS   : `say`                         (kill previous process to interrupt)
  Linux   : `spd-say` (speech-dispatcher) preferred, else `espeak`/`espeak-ng`
  Windows : PowerShell System.Speech      (kill previous process to interrupt)
  any     : `log`  -> just print "SPEAK: ..."  (used by tests)

Env:
  MK_SPEAK_BACKEND  say | spd-say | espeak | powershell | log | auto (default)
  MK_VOICE          backend-specific voice name
  MK_RATE_WPM       integer words-per-minute (mapped per backend)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading


def _which(*names):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _detect_backend() -> str:
    sysname = platform.system()
    if sysname == "Darwin":
        return "say"
    if sysname == "Windows":
        return "powershell"
    # Linux / other
    if _which("spd-say"):
        return "spd-say"
    if _which("espeak-ng", "espeak"):
        return "espeak"
    return "log"


class Speaker:
    def __init__(self, voice: str | None = None, rate_wpm: int | None = None):
        self.voice = voice or os.environ.get("MK_VOICE") or None
        rw = os.environ.get("MK_RATE_WPM")
        self.rate_wpm = rate_wpm or (int(rw) if rw else None)
        self.backend = os.environ.get("MK_SPEAK_BACKEND", "auto")
        if self.backend == "auto":
            self.backend = _detect_backend()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # -- command construction per backend --------------------------------

    def _cmd(self, text: str):
        b = self.backend
        if b == "say":
            c = ["say"]
            if self.voice:
                c += ["-v", self.voice]
            if self.rate_wpm:
                c += ["-r", str(self.rate_wpm)]
            return c + [text]
        if b == "spd-say":
            # -C cancels whatever spd is currently speaking (built-in interrupt)
            c = ["spd-say", "-C", "-w"]
            if self.voice:
                c += ["-y", self.voice]
            if self.rate_wpm:
                # spd-say rate is -100..100; ~175 wpm is 0
                c += ["-r", str(max(-100, min(100, round((self.rate_wpm - 175) / 1.75))))]
            return c + [text]
        if b == "espeak":
            exe = _which("espeak-ng", "espeak") or "espeak"
            c = [exe]
            if self.voice:
                c += ["-v", self.voice]
            if self.rate_wpm:
                c += ["-s", str(self.rate_wpm)]
            return c + [text]
        if b == "powershell":
            rate = ""
            if self.rate_wpm:
                # SAPI rate is -10..10; ~200 wpm is 0
                r = max(-10, min(10, round((self.rate_wpm - 200) / 20)))
                rate = f"$s.Rate={r};"
            voice = f"$s.SelectVoice('{self.voice}');" if self.voice else ""
            ps = ("Add-Type -AssemblyName System.Speech;"
                  "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  f"{voice}{rate}$s.Speak([Console]::In.ReadToEnd())")
            exe = _which("pwsh", "powershell") or "powershell"
            return [exe, "-NoProfile", "-Command", ps]
        return None

    # -- API ----------------------------------------------------------

    def say(self, text: str, interrupt: bool = True) -> None:
        text = " ".join((text or "").split())
        if not text:
            return
        if self.backend == "log":
            print(f"SPEAK: {text}", flush=True)
            return
        cmd = self._cmd(text)
        if cmd is None:
            print(f"SPEAK: {text}", flush=True)
            return
        with self._lock:
            if interrupt and self._proc and self._proc.poll() is None:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            stdin = subprocess.PIPE if self.backend == "powershell" else subprocess.DEVNULL
            try:
                self._proc = subprocess.Popen(
                    cmd, stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if self.backend == "powershell":
                    self._proc.stdin.write(text.encode("utf-8", "replace"))
                    self._proc.stdin.close()
            except FileNotFoundError:
                print(f"SPEAK: {text}", flush=True)

    def wait(self) -> None:
        with self._lock:
            p = self._proc
        if p:
            try:
                p.wait()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    s = Speaker()
    print(f"backend: {s.backend}")
    s.say(" ".join(sys.argv[1:]) or "talking menu test, one two three")
    s.wait()
