---
name: Region calibration data
about: Addresses for a non-USA disc (PAL / German / Japan)
title: "[region] "
labels: calibration
---

**Region / disc id**
<!-- PAL GMKP5D / German GMKD5D / Japan GMKJ5D -->

**How you got the addresses**
<!-- The recommended way is docs/CALIBRATION.md §2: extract mk5gc_release.elf from
     that disc and read its symbol table — the symbol names are identical across
     regions, only the numbers move. -->

**Addresses** (paste the ones from `mkda_addrs.py` that differ)
```python
MENU_ON        = 0x...
MENU_STACK_PTR = 0x...
MENU_STACK     = 0x...
MAIN_MENU_TBL  = 0x...
# ... etc
P1_POS = 0x...
P2_POS = 0x...
CHAR_DATA_TBL = 0x...
```

**Verified?**
- [ ] Menu narration checked live (navigated the main menu, heard correct labels)
- [ ] Character select checked live
