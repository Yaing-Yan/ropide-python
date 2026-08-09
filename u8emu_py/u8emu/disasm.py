# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
from .isa import COND


def disasm_one(cpu, seg, off):
    op = cpu.mmu.read_code16(seg, off)
    rec = cpu.info[op]
    if rec is None:
        return off + 2, f".dw {op:04X}"
    name, fmt, extra = rec
    imm16 = cpu.mmu.read_code16(seg, (off + 2) & 0xFFFF) if extra else 0
    i8 = op & 0xFF
    d = dict(
        n=(op >> 8) & 0xF, m=(op >> 4) & 0xF, i8=i8, i7=op & 0x7F,
        i8s=i8 - 0x100 if i8 & 0x80 else i8,
        i7s=(op & 0x7F) - 0x80 if op & 0x40 else op & 0x7F,
        w=(op >> 4) & 7, b=(op >> 4) & 7, d6=op & 0x3F,
        sw=op & 0x3F, seg=(op >> 8) & 0xF, imm16=imm16,
        cond=COND[(op >> 8) & 0xF],
        target=(off + 2 + (((i8 - 0x100) if i8 & 0x80 else i8) * 2)) & 0xFFFF,
        rlist="|".join(x for x, bit in
                       (("lr", 8), ("psw", 4), ("elr", 2), ("ea", 1))
                       if ((op >> 8) & 0xF) & bit) or "-",
    )
    try:
        text = fmt.format(**d)
    except Exception:
        text = name
    return (off + 2 + 2 * extra) & 0xFFFF, text


def disasm(cpu, seg, off, count):
    out = []
    for _ in range(count):
        cur = off
        off, text = disasm_one(cpu, seg, off)
        raw = cpu.mmu.read_code16(seg, cur)
        out.append((cur, raw, text))
    return out
