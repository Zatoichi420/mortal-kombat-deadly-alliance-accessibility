"""Minimal GameCube disc (GCM / .iso / .nkit.iso) reader.

Enough to pull main.dol and walk the FST so we can extract the files that hold
menu text and fighter names. NKit *ISO* images keep the real header / DOL / FST /
file data intact (only junk padding is scrubbed), so plain offset reads work.

Usage:
    python3 gc_extract.py <disc.iso> info
    python3 gc_extract.py <disc.iso> dol   <out_dir>
    python3 gc_extract.py <disc.iso> list
    python3 gc_extract.py <disc.iso> extract <name-substring> <out_dir>
    python3 gc_extract.py <disc.iso> extract-all <out_dir>
"""

from __future__ import annotations

import os
import struct
import sys


def u32(b, off):
    return struct.unpack_from(">I", b, off)[0]


class GCDisc:
    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
        hdr = self._read(0, 0x0440)
        self.game_id = hdr[0:6].decode("latin1")
        self.title = hdr[0x20:0x60].split(b"\0")[0].decode("latin1", "replace")
        self.dol_off = u32(hdr, 0x0420)
        self.fst_off = u32(hdr, 0x0424)
        self.fst_size = u32(hdr, 0x0428)
        self._load_fst()

    def _read(self, off, size):
        self.f.seek(off)
        return self.f.read(size)

    # ---- DOL --------------------------------------------------------------
    def dol_size(self):
        h = self._read(self.dol_off, 0x100)
        end = 0
        # 7 text + 11 data sections: offsets 0x00.., sizes 0x90..
        for i in range(18):
            sec_off = u32(h, 0x00 + i * 4)
            sec_size = u32(h, 0x90 + i * 4)
            if sec_off:
                end = max(end, sec_off + sec_size)
        return end

    def extract_dol(self, out_dir):
        size = self.dol_size()
        data = self._read(self.dol_off, size)
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "main.dol")
        with open(p, "wb") as o:
            o.write(data)
        return p, size

    # ---- FST ------------------------------------------------------------
    def _load_fst(self):
        fst = self._read(self.fst_off, self.fst_size)
        self.fst = fst
        n_entries = u32(fst, 0x08)
        str_table = 12 * n_entries
        self.entries = []  # (path, offset, size, is_dir)

        def name_at(rel):
            end = fst.index(b"\0", str_table + rel)
            return fst[str_table + rel:end].decode("latin1", "replace")

        stack = [("", n_entries)]  # (path_prefix, index_at_which_this_dir_ends)
        i = 1
        while i < n_entries:
            e = fst[i * 12:(i + 1) * 12]
            is_dir = e[0] == 1
            name_off = u32(b"\0" + e[1:4], 0) & 0xFFFFFF
            arg1 = u32(e, 4)
            arg2 = u32(e, 8)
            while stack and i >= stack[-1][1]:
                stack.pop()
            prefix = stack[-1][0] if stack else ""
            nm = name_at(name_off)
            if is_dir:
                path = f"{prefix}{nm}/"
                self.entries.append((path, 0, 0, True))
                stack.append((path, arg2))
            else:
                path = f"{prefix}{nm}"
                self.entries.append((path, arg1, arg2, False))
            i += 1

    def files(self):
        return [(p, o, s) for (p, o, s, d) in self.entries if not d]

    def extract(self, path, offset, size, out_dir):
        data = self._read(offset, size)
        dest = os.path.join(out_dir, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as o:
            o.write(data)
        return dest


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    disc = GCDisc(sys.argv[1])
    cmd = sys.argv[2]
    if cmd == "info":
        print(f"game_id  : {disc.game_id}")
        print(f"title    : {disc.title}")
        print(f"dol_off  : {disc.dol_off:#x}  size ~ {disc.dol_size():#x} ({disc.dol_size()} bytes)")
        print(f"fst_off  : {disc.fst_off:#x}  fst_size {disc.fst_size:#x}")
        print(f"files    : {len(disc.files())}")
    elif cmd == "dol":
        p, size = disc.extract_dol(sys.argv[3])
        print(f"wrote {p} ({size} bytes)")
    elif cmd == "list":
        for p, o, s in sorted(disc.files()):
            print(f"{s:>10}  {o:#010x}  {p}")
    elif cmd == "extract":
        sub = sys.argv[3].lower()
        out = sys.argv[4]
        hits = [(p, o, s) for (p, o, s) in disc.files() if sub in p.lower()]
        for p, o, s in hits:
            dest = disc.extract(p, o, s, out)
            print(f"wrote {dest} ({s} bytes)")
        if not hits:
            print(f"no file matching {sub!r}")
    elif cmd == "extract-all":
        out = sys.argv[3]
        for p, o, s in disc.files():
            disc.extract(p, o, s, out)
        print(f"extracted {len(disc.files())} files to {out}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
