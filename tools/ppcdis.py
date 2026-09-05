#!/usr/bin/env python3
"""Disassemble a function in mk5gc_release.elf and resolve r13/r2 (small-data)
memory accesses to their global-variable addresses + symbol names.

    export MKDA_ELF=/path/to/mk5gc_release.elf      # extract with tools/gc_extract.py
    python3 ppcdis.py mode_menu_ctrl
    python3 ppcdis.py 0x80065cec 548

Needs: pip install pyelftools capstone
"""
from __future__ import annotations
import os, re, sys, struct
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

ELF = os.environ.get("MKDA_ELF", "mk5gc_release.elf")
if not os.path.isfile(ELF):
    sys.exit(f"ELF not found: {ELF}\n"
             "Set MKDA_ELF, or extract it: python3 gc_extract.py <disc> extract mk5gc_release.elf .")
e = ELFFile(open(ELF, "rb"))
segs = [(s['sh_addr'], s['sh_addr'] + s['sh_size'], s.name, s.data())
        for s in e.iter_sections() if s['sh_addr'] and s['sh_type'] == 'SHT_PROGBITS']
symtab = e.get_section_by_name('.symtab')
BYNAME, BYADDR = {}, {}
for s in symtab.iter_symbols():
    if s.name and s['st_value']:
        BYNAME.setdefault(s.name, (s['st_value'], s['st_size']))
        BYADDR.setdefault(s['st_value'], s.name)
SDA = BYNAME["_SDA_BASE_"][0]
SDA2 = BYNAME["_SDA2_BASE_"][0]

def read(v, n):
    for a, b, nm, d in segs:
        if a <= v < b:
            return d[v - a:v - a + n]

def sym_for(addr):
    if addr in BYADDR:
        return BYADDR[addr]
    # nearest preceding object symbol within 0x40
    best = None
    for s in symtab.iter_symbols():
        if s.name and s['st_value'] and s['st_value'] <= addr < s['st_value'] + max(s['st_size'], 1):
            best = f"{s.name}+{addr - s['st_value']:#x}" if addr != s['st_value'] else s.name
    return best or ""

def go(addr, size):
    code = read(addr, size)
    md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    md.detail = True
    hot = []
    for ins in md.disasm(code, addr):
        line = f"  {ins.address:#010x}  {ins.mnemonic:8} {ins.op_str}"
        m = re.search(r'(-?0x[0-9a-fA-F]+|-?\d+)\(r(13|2)\)', ins.op_str)
        if m:
            off = int(m.group(1), 16) if m.group(1).lower().startswith(("0x", "-0x")) else int(m.group(1))
            base = SDA if m.group(2) == "13" else SDA2
            tgt = base + off
            nm = sym_for(tgt)
            line += f"        ; [{tgt:#x}] {nm}"
            if ins.mnemonic.startswith(("lwz", "lha", "lbz", "stw", "sth", "stb", "lwzu", "addi")):
                hot.append((ins.address, ins.mnemonic, tgt, nm))
        print(line)
    print("\n  -- small-data accesses --")
    for a, mn, tgt, nm in hot:
        print(f"    {a:#010x} {mn:6} {tgt:#x}  {nm}")

if __name__ == "__main__":
    arg = sys.argv[1]
    if arg.startswith("0x"):
        go(int(arg, 16), int(sys.argv[2]))
    else:
        v, sz = BYNAME[arg]
        print(f"== {arg} @ {v:#x} ({sz} bytes) ==")
        go(v, sz)
