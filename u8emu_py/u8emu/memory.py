# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
from __future__ import annotations
from typing import Callable, Optional, List

PAGE_SHIFT = 8
PAGE = 1 << PAGE_SHIFT
DATA_PAGES = (1 << 20) >> PAGE_SHIFT      # 20-bit data space


class Region:
    __slots__ = ("start", "size", "name", "data", "reader", "writer", "writable", "prio")

    def __init__(self, start, size, name, data=None,
                 reader=None, writer=None, writable=True, prio=0):
        self.start = start
        self.size = size
        self.name = name
        self.data = data          # bytearray / memoryview  (fast path)
        self.reader = reader      # fn(addr) -> int         (MMIO)
        self.writer = writer      # fn(addr, value)
        self.writable = writable
        self.prio = prio          # 页冲突时优先级高者获胜（后贴覆盖）

    def __repr__(self):
        return f"<Region {self.name} {self.start:05X}..{self.start+self.size-1:05X}>"


class MMU:
    """20-bit data space + separate code space (U8 是哈佛结构, ROM window 共享同一 bytearray)."""

    def __init__(self, code_size=0x100000):
        self.code = bytearray(code_size)
        self.pages: List[Optional[Region]] = [None] * DATA_PAGES
        self.regions: List[Region] = []
        self.watch_r = {}     # addr -> [cb(addr, value)]
        self.watch_w = {}     # addr -> [cb(addr, value)]
        self._has_wr = False
        self._has_ww = False
        self.unmapped_log = []
        self.trace_unmapped = False
        self.pd_value = 0x00  # 未映射读的返回值（fx991cnx model.lua: pd_value=0x00）
        self.profile = None   # array('I') 写热度桶（每 64B 一个），探测 VRAM 用

    # ---------- mapping ----------
    def _repage(self):
        """按 prio 升序贴页：prio 大的区域覆盖小的（VRAM 压过 SFR）"""
        self.pages = [None] * DATA_PAGES
        for r in sorted(self.regions, key=lambda x: x.prio):
            for p in range(r.start >> PAGE_SHIFT,
                           (r.start + r.size + PAGE - 1) >> PAGE_SHIFT):
                self.pages[p] = r

    def add_region(self, r: Region):
        self.regions.append(r)
        self._repage()
        return r

    def remove_region(self, r: Region):
        if r in self.regions:
            self.regions.remove(r)
            self._repage()

    def region_at(self, addr) -> Optional[Region]:
        return self.pages[(addr & 0xFFFFF) >> PAGE_SHIFT]

    # ---------- data space ----------
    def read8(self, addr):
        addr &= 0xFFFFF
        r = self.pages[addr >> PAGE_SHIFT]
        if r is None:
            if self.trace_unmapped:
                self.unmapped_log.append(("r", addr))
            return self.pd_value
        v = r.data[addr - r.start] if r.data is not None else r.reader(addr)
        if self._has_wr:
            cbs = self.watch_r.get(addr)
            if cbs:
                for cb in cbs:
                    cb(addr, v)
        return v

    def write8(self, addr, value):
        addr &= 0xFFFFF
        value &= 0xFF
        if self.profile is not None:      # 未映射的写也要计数
            self.profile[addr >> 6] += 1
        r = self.pages[addr >> PAGE_SHIFT]
        if r is None:
            if self.trace_unmapped:
                self.unmapped_log.append(("w", addr))
            return
        if r.data is not None:
            if r.writable:
                r.data[addr - r.start] = value
        elif r.writer is not None:
            r.writer(addr, value)
        if self._has_ww:
            cbs = self.watch_w.get(addr)
            if cbs:
                for cb in cbs:
                    cb(addr, value)

    def read16(self, addr):
        return self.read8(addr) | (self.read8(addr + 1) << 8)

    def write16(self, addr, v):
        self.write8(addr, v & 0xFF)
        self.write8(addr + 1, (v >> 8) & 0xFF)

    # 绕过 watchpoint 的裸写（插件 freeze 用，避免递归）
    def poke_raw(self, addr, value):
        addr &= 0xFFFFF
        r = self.pages[addr >> PAGE_SHIFT]
        if r is None:
            return
        if r.data is not None:
            r.data[addr - r.start] = value & 0xFF
        elif r.writer:
            r.writer(addr, value & 0xFF)

    def peek_raw(self, addr):
        addr &= 0xFFFFF
        r = self.pages[addr >> PAGE_SHIFT]
        if r is None:
            return self.pd_value
        return r.data[addr - r.start] if r.data is not None else r.reader(addr)

    # ---------- code space ----------
    def read_code16(self, seg, off):
        a = ((seg & 0xF) << 16) | (off & 0xFFFF)
        c = self.code
        return c[a] | (c[a + 1] << 8)

    def read_code8(self, seg, off):
        return self.code[(((seg & 0xF) << 16) | (off & 0xFFFF))]

    # ---------- watchpoints ----------
    def add_watch(self, addr, cb, on_write=True):
        d = self.watch_w if on_write else self.watch_r
        d.setdefault(addr & 0xFFFFF, []).append(cb)
        self._has_ww = bool(self.watch_w)
        self._has_wr = bool(self.watch_r)

    def del_watch(self, addr, cb=None, on_write=True):
        d = self.watch_w if on_write else self.watch_r
        a = addr & 0xFFFFF
        if a in d:
            if cb is None:
                del d[a]
            else:
                d[a] = [c for c in d[a] if c is not cb]
                if not d[a]:
                    del d[a]
        self._has_ww = bool(self.watch_w)
        self._has_wr = bool(self.watch_r)
