"""Thin client for RetroArch's UDP interfaces.

Two separate UDP services:

  * Network Command Interface  (default port 55355, cfg: network_cmd_enable = "true")
      - VERSION, GET_STATUS, READ_CORE_MEMORY, WRITE_CORE_MEMORY, PAUSE_TOGGLE,
        FRAMEADVANCE, AI_SERVICE, MENU_TOGGLE, QUIT, ...
      - READ_CORE_MEMORY / WRITE_CORE_MEMORY / VERSION / GET_STATUS send a reply;
        most other commands are fire-and-forget (no ack).

  * Network Gamepad / "network_remote"  (default base port 55400, one port per player:
        p1 = 55400, p2 = 55401, ...   cfg: network_remote_enable = "true"
                                            network_remote_enable_user_p1 = "true")
      - level-triggered: RetroArch holds the last state it was told per button.
      - packet format is confirmed by the network-remote agent report; see press()/hold().

Verified 2026-09-05 against RetroArch 1.22.2 + dolphin_libretro on macOS:
    READ_CORE_MEMORY 80000000 16  ->  "READ_CORE_MEMORY 80000000 47 4d 4b 45 ..."
    addresses are raw GameCube virtual addresses (0x80000000 == start of MEM1),
    big-endian, no host-offset translation needed.
"""

from __future__ import annotations

import socket
import time

CMD_HOST = "127.0.0.1"
CMD_PORT = 55355
REMOTE_HOST = "127.0.0.1"
REMOTE_BASE_PORT = 55400

# RETRO_DEVICE_ID_JOYPAD_* -- the RetroPad button ids
BTN = {
    "b": 0, "y": 1, "select": 2, "start": 3,
    "up": 4, "down": 5, "left": 6, "right": 7,
    "a": 8, "x": 9, "l": 10, "r": 11,
    "l2": 12, "r2": 13, "l3": 14, "r3": 15,
}


class RetroArchError(RuntimeError):
    pass


class RAClient:
    def __init__(self, cmd_host=CMD_HOST, cmd_port=CMD_PORT,
                 remote_host=REMOTE_HOST, remote_base_port=REMOTE_BASE_PORT,
                 timeout=0.5):
        self.cmd_addr = (cmd_host, cmd_port)
        self.remote_host = remote_host
        self.remote_base_port = remote_base_port
        self.timeout = timeout
        self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmd_sock.settimeout(timeout)
        self._remote_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ---- network command interface -------------------------------------------

    def _cmd(self, text: str, expect_reply: bool, retries: int = 1,
             match_tokens: tuple = ()) -> str | None:
        """Send a command; if a reply is expected, read datagrams until one whose
        leading token matches the command we sent (RetroArch echoes the command
        name in READ_CORE_MEMORY / WRITE_CORE_MEMORY / GET_STATUS / VERSION
        replies). This demuxes replies on the shared UDP socket so a slow
        GET_STATUS answer can't be mistaken for a READ_CORE_MEMORY answer.

        `match_tokens` additionally pins reply tokens by position — e.g.
        (("1", "<addr>"),) requires the echoed address (token 1) to match, so a
        stale READ_CORE_MEMORY reply for a *different* address is also dropped."""
        want = text.split(" ", 1)[0]
        last_err = None
        for _ in range(retries + 1):
            # drain any datagrams left over from a previous, timed-out command
            self._cmd_sock.settimeout(0)
            try:
                while True:
                    self._cmd_sock.recvfrom(65535)
            except (BlockingIOError, socket.timeout, OSError):
                pass
            self._cmd_sock.sendto(text.encode("ascii"), self.cmd_addr)
            if not expect_reply:
                return None
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    self._cmd_sock.settimeout(max(0.05, deadline - time.monotonic()))
                    data, _ = self._cmd_sock.recvfrom(65535)
                except socket.timeout:
                    break
                reply = data.decode("ascii", errors="replace").strip()
                toks = reply.split()
                if not (toks and (toks[0] == want or want == "VERSION")):
                    last_err = f"stale reply {(toks[0] if toks else '')!r}"
                    continue
                if any(len(toks) <= i or toks[i].lower() != v.lower()
                       for i, v in match_tokens):
                    last_err = f"reply token mismatch {reply[:40]!r}"
                    continue
                return reply
        raise RetroArchError(
            f"no reply to {text!r} ({last_err or 'timeout'}; is RetroArch running and focused?)")

    def version(self) -> str:
        return self._cmd("VERSION", True)

    def status(self) -> dict:
        """-> {'state': 'PLAYING'|'PAUSED'|'CONTENTLESS', 'system':..., 'game':..., 'crc32':...}"""
        r = self._cmd("GET_STATUS", True)          # "GET_STATUS PLAYING gamecube,<name>,crc32=abcd1234"
        body = r.split(" ", 1)[1] if " " in r else r
        parts = body.split(" ", 1)
        state = parts[0]
        out = {"state": state, "system": None, "game": None, "crc32": None}
        if len(parts) > 1:
            fields = parts[1].split(",")
            if fields:
                out["system"] = fields[0]
            if len(fields) > 1:
                out["game"] = fields[1]
            for f in fields[2:]:
                if f.startswith("crc32="):
                    out["crc32"] = f[len("crc32="):]
        return out

    def is_playing(self) -> bool:
        try:
            return self.status().get("state") == "PLAYING"
        except RetroArchError:
            return False

    def read_memory(self, addr: int, length: int) -> bytes:
        """READ_CORE_MEMORY. addr = raw GameCube address; RetroArch parses the
        address as hex and the byte count as DECIMAL (`sscanf "%x %u"`)."""
        reply = self._cmd(f"READ_CORE_MEMORY {addr:x} {length:d}", True,
                          match_tokens=((1, f"{addr:x}"),))
        toks = reply.split()
        # "READ_CORE_MEMORY <addr> <b0> <b1> ..."  or  "... <addr> -1 <error>"
        if len(toks) >= 3 and toks[2] == "-1":
            raise RetroArchError(f"READ_CORE_MEMORY {addr:#x}: {' '.join(toks[3:]) or 'failed'}")
        try:
            return bytes(int(b, 16) for b in toks[2:])
        except ValueError as e:
            raise RetroArchError(f"bad READ_CORE_MEMORY reply: {reply!r}") from e

    def read_u8(self, addr: int) -> int:
        return self.read_memory(addr, 1)[0]

    def read_u16(self, addr: int) -> int:
        return int.from_bytes(self.read_memory(addr, 2), "big")   # GameCube is big-endian

    def read_u32(self, addr: int) -> int:
        return int.from_bytes(self.read_memory(addr, 4), "big")

    def write_memory(self, addr: int, data: bytes) -> None:
        payload = " ".join(f"{b:02x}" for b in data)
        reply = self._cmd(f"WRITE_CORE_MEMORY {addr:x} {payload}", True)
        if " -1 " in f" {reply} ":
            raise RetroArchError(f"WRITE_CORE_MEMORY {addr:#x}: {reply}")

    def ai_service(self) -> None:
        """Fire the AI-service (OCR->speech) pipeline once. No ack."""
        self._cmd("AI_SERVICE", False)

    def pause_toggle(self) -> None:
        self._cmd("PAUSE_TOGGLE", False)

    def frame_advance(self) -> None:
        self._cmd("FRAMEADVANCE", False)

    def quit(self) -> None:
        self._cmd("QUIT", False)

    # ---- network gamepad ----------------------------------------------------
    #
    # RetroArch's network-remote protocol (input/input_remote.c): one datagram per
    # input id, a packed struct in HOST byte order (little-endian on this Mac):
    #     int32 port; int32 device; int32 index; int32 id; uint16 state;   (+2 pad)
    # LEVEL-triggered: RetroArch applies the last state it was told per id, so a
    # "press" is state=1 -> hold a few frames -> state=0.
    #
    # device = RETRO_DEVICE_JOYPAD (1); id = RETRO_DEVICE_ID_JOYPAD_* (BTN table).
    # If the network-remote research agent reports a different layout, adjust
    # _remote_packet() / STRUCT_FMT to match.

    import struct as _struct
    _STRUCT_FMT = "<iiiiH2x"   # 20 bytes

    def _remote_addr(self, player: int):
        return (self.remote_host, self.remote_base_port + (player - 1))

    def _remote_send(self, id_: int, state: int, player=1, device=1, index=0) -> None:
        pkt = self._struct.pack(self._STRUCT_FMT, player - 1, device, index, id_, state & 0xFFFF)
        self._remote_sock.sendto(pkt, self._remote_addr(player))

    def set_button(self, button: str, down: bool, player=1) -> None:
        self._remote_send(BTN[button.lower()], 1 if down else 0, player=player)

    def set_state(self, buttons=(), player=1) -> None:
        """Set the full held-button set: presses listed ids, releases all others."""
        held = {BTN[b.lower()] for b in buttons}
        for name, i in BTN.items():
            self._remote_send(i, 1 if i in held else 0, player=player)

    def press(self, button: str, player=1, hold=0.12, release_wait=0.09) -> None:
        self.set_button(button, True, player=player)
        time.sleep(hold)
        self.set_button(button, False, player=player)
        time.sleep(release_wait)

    def release_all(self, player=1) -> None:
        for i in BTN.values():
            self._remote_send(i, 0, player=player)

    def tap_repeat(self, button: str, n: int, player=1, gap=0.20) -> None:
        for _ in range(n):
            self.press(button, player=player)
            time.sleep(gap)


if __name__ == "__main__":
    import sys
    ra = RAClient()
    print("VERSION:", ra.version())
    print("STATUS :", ra.status())
    if len(sys.argv) >= 3 and sys.argv[1] == "read":
        addr = int(sys.argv[2], 16)
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 16
        print(f"{addr:#x}: " + " ".join(f"{b:02x}" for b in ra.read_memory(addr, n)))
