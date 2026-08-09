# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
#
# 语义与 CasioEmuNeo/CasioEmuNeo/emulator/Chipset/*.cpp 逐一对应：
#   - 标志位机制: 每条指令 _fin(输入)/_fout(输出, 初始 Z=1)/_fchg(改动掩码)
#   - DSR 前缀: 只影响当前指令链(Next 内 while 循环, H_DS 续链)
#   - 中断: 向量 = index*2；SWI index = 0x40+n；BRK/NMI 级别 2
from __future__ import annotations
from .isa import build_tables

C, Z, S, OV, MIE, HC = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04
EL_MASK = 0x03


class IllegalInstruction(Exception):
    pass


class CPU:
    def __init__(self, emu):
        self.emu = emu
        self.mmu = emu.mmu
        self.r = bytearray(16)
        self.cr = bytearray(16)          # 协处理器寄存器
        self.pc = 0
        self.csr = 0
        self.lr = 0                      # = elr[0]
        self.lcsr = 0                    # = ecsr[0]
        self.elr = [0, 0, 0, 0]
        self.ecsr = [0, 0, 0, 0]
        self.epsw = [0, 0, 0, 0]         # epsw[0] 即 psw
        self.psw = 0
        self.sp = 0
        self.ea = 0
        self.dsr = 0
        self.dsr_last = 0                # 最近一次 H_DW 写入的 DSR
        self.dsr_active = False
        self.cycles = 0
        self.halted = False
        self.strict = False
        self.exec_hooks = {}             # (csr<<16|pc) -> [cb]
        self._has_hooks = False
        self._fin = self._fout = self._fchg = 0
        self.dispatch, self.info = build_tables(
            lambda n: getattr(type(self), "op_" + n, type(self)._op_bad))

    # ================= registers =================
    def get_er(self, n): return self.r[n] | (self.r[n + 1] << 8)
    def set_er(self, n, v):
        self.r[n] = v & 0xFF; self.r[n + 1] = (v >> 8) & 0xFF

    def get_xr(self, n): return self.get_er(n) | (self.get_er(n + 2) << 16)
    def set_xr(self, n, v):
        self.set_er(n, v & 0xFFFF); self.set_er(n + 2, (v >> 16) & 0xFFFF)

    @property
    def el(self): return self.psw & EL_MASK

    # ================= reset / 中断 =================
    def reset(self):
        self.sp = self.mmu.read_code16(0, 0)
        self.dsr = 0
        self.psw = 0
        self.pc = self.mmu.read_code16(0, 2)   # Reset 向量 = index 1
        self.csr = 0
        self.halted = False
        for i in range(16):
            self.r[i] = 0

    def raise_int(self, level, index):
        """对应 CPU::Raise —— 不保存 PSW（epsw 由 ISR 自行处理）"""
        if level == 1:
            self.psw &= ~MIE
        self.psw = (self.psw & ~EL_MASK) | level
        self.elr[level] = self.pc
        self.ecsr[level] = self.csr
        self.csr = 0
        self.pc = self.mmu.read_code16(0, index * 2)

    # ================= data access (DSR 仅在 dsr_active 时生效) =================
    def _da(self, off):
        if self.dsr_active:
            return ((self.dsr << 16) | (off & 0xFFFF)) & 0xFFFFF
        return off & 0xFFFF

    def ld8(self, off):  return self.mmu.read8(self._da(off))
    def ld16(self, off): return self.mmu.read16(self._da(off))
    def st8(self, off, v):  self.mmu.write8(self._da(off), v)
    def st16(self, off, v): self.mmu.write16(self._da(off), v)

    def push16(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.mmu.write8(self.sp, v & 0xFF)
        self.mmu.write8((self.sp + 1) & 0xFFFF, (v >> 8) & 0xFF)

    def pop16(self):
        v = self.mmu.read8(self.sp) | (self.mmu.read8((self.sp + 1) & 0xFFFF) << 8)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    # ================= 标志位机制（对应 impl_flags_*）=================
    def _exec(self, fn, op):
        self._fin = self.psw
        self._fout = Z                  # 每条指令 out 初始 Z=1（ZSCheck 只清不置）
        self._fchg = 0
        fn(self, op)
        self.psw = (self.psw & ~self._fchg) | (self._fout & self._fchg)

    def _add8(self, c_in):
        """对应 Add8：C/OV/HC，返回 8 位和"""
        a = self._op0 & 0xFF
        b = self._op1 & 0xFF
        carry8 = (a + b + c_in) >> 8
        carry7 = ((a & 0x7F) + (b & 0x7F) + c_in) >> 7
        carry4 = ((a & 0x0F) + (b & 0x0F) + c_in) >> 4
        r = (a + b + c_in) & 0xFF
        self._fchg |= C | OV | HC
        self._fout = (self._fout & ~(C | OV | HC))
        if carry8: self._fout |= C
        if carry8 ^ carry7: self._fout |= OV
        if carry4: self._fout |= HC
        return r

    def _zs(self, v):
        """对应 ZSCheck：只清 Z，S = bit7"""
        self._fchg |= Z | S
        if v & 0xFF:
            self._fout &= ~Z
        self._fout = (self._fout & ~S) | (S if v & 0x80 else 0)

    # ================= step =================
    def fetch(self):
        v = self.mmu.read_code16(self.csr, self.pc)
        self.pc = (self.pc + 2) & 0xFFFF
        return v

    def step(self):
        """外设 tick → 中断接受 → 指令链（H_DS 连续执行）"""
        self.emu.tick_peripherals(1)
        self.emu.check_interrupts()
        self.dsr_active = False
        while True:
            if self._has_hooks:
                key = (self.csr << 16) | self.pc
                cbs = self.exec_hooks.get(key)
                if cbs:
                    for cb in cbs:
                        cb(self)
            op = self.fetch()
            fn = self.dispatch[op]
            if fn is None:                    # 未知指令：静默跳过（上游 continue）
                if self.strict:
                    raise IllegalInstruction(
                        f"unknown opcode {op:04X} at {self.csr:X}:{(self.pc-2)&0xFFFF:04X}")
                self.cycles += 1
                continue
            self._exec(fn, op)
            self.cycles += 1
            if fn not in (CPU.op_dsr_i8, CPU.op_dsr_r, CPU.op_dsr_dsr):
                break

    def _op_bad(self, op):
        pass

    # ================= handlers =================
    # ---- 8 位算术 ----

    def op_add_r_r(s, op):
        n = (op >> 8) & 0xF
        s._fin &= ~C; s._fin |= Z
        s._op0, s._op1 = s.r[n], s.r[(op >> 4) & 0xF]
        s._op0 = s._add8(1 if s._fin & C else 0)
        s._zs(s._op0)
        s.r[n] = s._op0

    def op_add_r_i(s, op):
        n = (op >> 8) & 0xF
        s._fin &= ~C; s._fin |= Z
        s._op0, s._op1 = s.r[n], op & 0xFF
        s._op0 = s._add8(0)
        s._zs(s._op0)
        s.r[n] = s._op0

    def op_addc_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0, s._op1 = s.r[n], s.r[(op >> 4) & 0xF]
        s._op0 = s._add8(1 if s._fin & C else 0)
        if not (s._fin & Z): s._fout &= ~Z
        s._zs(s._op0)
        s.r[n] = s._op0

    def op_addc_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0, s._op1 = s.r[n], op & 0xFF
        s._op0 = s._add8(1 if s._fin & C else 0)
        if not (s._fin & Z): s._fout &= ~Z
        s._zs(s._op0)
        s.r[n] = s._op0

    def _sub(s, op, wb, sticky):
        n = (op >> 8) & 0xF
        if sticky:
            s._fin &= ~C; s._fin |= Z
        s._op0 = s.r[n] ^ 0xFF
        s._op1 = s.r[(op >> 4) & 0xF]
        s._op0 = s._add8(1 if s._fin & C else 0)
        r = (s._op0 ^ 0xFF) & 0xFF
        if not (s._fin & Z): s._fout &= ~Z
        s._zs(r)
        if wb:
            s.r[n] = r

    def _sub_i(s, op, wb, sticky):
        n = (op >> 8) & 0xF
        if sticky:
            s._fin &= ~C; s._fin |= Z
        s._op0 = s.r[n] ^ 0xFF
        s._op1 = op & 0xFF
        s._op0 = s._add8(1 if s._fin & C else 0)
        r = (s._op0 ^ 0xFF) & 0xFF
        if not (s._fin & Z): s._fout &= ~Z
        s._zs(r)
        if wb:
            s.r[n] = r

    def op_sub_r_r(s, op):  s._sub(op, True, True)
    def op_sub_r_i(s, op):  s._sub_i(op, True, True)
    def op_cmp_r_r(s, op):  s._sub(op, False, True)
    def op_cmp_r_i(s, op):  s._sub_i(op, False, True)
    def op_subc_r_r(s, op): s._sub(op, True, False)
    def op_subc_r_i(s, op): s._sub_i(op, True, False)
    def op_cmpc_r_r(s, op): s._sub(op, False, False)
    def op_cmpc_r_i(s, op): s._sub_i(op, False, False)

    def op_and_r_r(s, op):  n = (op >> 8) & 0xF; s.r[n] = s.r[n] & s.r[(op >> 4) & 0xF] & 0xFF; s._zs(s.r[n])
    def op_and_r_i(s, op):  n = (op >> 8) & 0xF; s.r[n] = (s.r[n] & (op & 0xFF)) & 0xFF; s._zs(s.r[n])
    def op_or_r_r(s, op):   n = (op >> 8) & 0xF; s.r[n] = (s.r[n] | s.r[(op >> 4) & 0xF]) & 0xFF; s._zs(s.r[n])
    def op_or_r_i(s, op):   n = (op >> 8) & 0xF; s.r[n] = (s.r[n] | (op & 0xFF)) & 0xFF; s._zs(s.r[n])
    def op_xor_r_r(s, op):  n = (op >> 8) & 0xF; s.r[n] = (s.r[n] ^ s.r[(op >> 4) & 0xF]) & 0xFF; s._zs(s.r[n])
    def op_xor_r_i(s, op):  n = (op >> 8) & 0xF; s.r[n] = (s.r[n] ^ (op & 0xFF)) & 0xFF; s._zs(s.r[n])
    def op_mov_r_r(s, op):  n = (op >> 8) & 0xF; s.r[n] = s.r[(op >> 4) & 0xF] & 0xFF; s._zs(s.r[n])
    def op_mov_r_i(s, op):  n = (op >> 8) & 0xF; s.r[n] = op & 0xFF; s._zs(s.r[n])

    # ---- 16 位 ----
    def op_mov_er_er(s, op):
        b = s.get_er((op >> 4) & 0xE)
        lo = b & 0xFF
        s._zs(lo)
        hi = (b >> 8) & 0xFF
        s._zs(hi)
        s.set_er((op >> 8) & 0xE, (hi << 8) | lo)

    def op_mov_er_i7(s, op):
        b = op & 0x7F
        if b & 0x40: b |= 0xFF80
        lo = b & 0xFF
        s._zs(lo)
        hi = (b >> 8) & 0xFF
        s._zs(hi)
        s.set_er((op >> 8) & 0xE, (hi << 8) | lo)

    def op_add_er_er(s, op):
        a = s.get_er((op >> 8) & 0xE)
        b = s.get_er((op >> 4) & 0xE)
        s._fin &= ~C
        al, bl = a & 0xFF, b & 0xFF
        s._op0, s._op1 = al, bl
        s._op0 = s._add8(0)
        lo = s._op0
        s._zs(lo)
        s._fin = (s._fin & ~C) | (s._fout & C)
        ah, bh = (a >> 8) & 0xFF, (b >> 8) & 0xFF
        s._op0, s._op1 = ah, bh
        s._op0 = s._add8(1 if s._fin & C else 0)
        s._zs(s._op0)
        s.set_er((op >> 8) & 0xE, (s._op0 << 8) | lo)

    def op_add_er_i7(s, op):
        b = op & 0x7F
        if b & 0x40: b |= 0xFF80
        s._fin &= ~C
        a = s.get_er((op >> 8) & 0xE)
        al, bl = a & 0xFF, b & 0xFF
        s._op0, s._op1 = al, bl
        s._op0 = s._add8(0)
        lo = s._op0
        s._zs(lo)
        s._fin = (s._fin & ~C) | (s._fout & C)
        ah, bh = (a >> 8) & 0xFF, (b >> 8) & 0xFF
        s._op0, s._op1 = ah, bh
        s._op0 = s._add8(1 if s._fin & C else 0)
        s._zs(s._op0)
        s.set_er((op >> 8) & 0xE, (s._op0 << 8) | lo)

    def op_cmp_er_er(s, op):
        a = s.get_er((op >> 8) & 0xE)
        b = s.get_er((op >> 4) & 0xE)
        s._fin &= ~C
        al, bl = a & 0xFF, b & 0xFF
        s._op0 = al ^ 0xFF
        s._op1 = bl
        s._op0 = s._add8(0)
        r_lo = (s._op0 ^ 0xFF) & 0xFF
        s._zs(r_lo)
        s._fin = (s._fin & ~C) | (s._fout & C)
        ah, bh = (a >> 8) & 0xFF, (b >> 8) & 0xFF
        s._op0 = ah ^ 0xFF
        s._op1 = bh
        s._op0 = s._add8(1 if s._fin & C else 0)
        r_hi = (s._op0 ^ 0xFF) & 0xFF
        s._zs(r_hi)

    # ---- 移位（只改 C！）----
    def _shift_left(s):
        v = s._op0 & 0xFF
        sh = s._op1 & 7
        result = (v << sh) | (s._shift_buf >> (8 - sh))
        s._fchg |= C
        if result & 0x100:
            s._fout |= C
        s._op0 = result & 0xFF

    def _shift_right(s):
        v = s._op0 & 0xFF
        sh = s._op1 & 7
        result = (v << (8 - sh)) | (s._shift_buf << (16 - sh))
        s._fchg |= C
        if result & 0x80:
            s._fout |= C
        s._op0 = (result >> 8) & 0xFF

    def op_sll_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = s.r[(op >> 4) & 0xF]
        s._shift_buf = 0
        s._shift_left()
        s.r[n] = s._op0

    def op_sll_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = (op >> 4) & 7
        s._shift_buf = 0
        s._shift_left()
        s.r[n] = s._op0

    def op_sllc_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = s.r[(op >> 4) & 0xF]
        s._shift_buf = s.r[(n - 1) & 15]
        s._shift_left()
        s.r[n] = s._op0

    def op_sllc_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = (op >> 4) & 7
        s._shift_buf = s.r[(n - 1) & 15]
        s._shift_left()
        s.r[n] = s._op0

    def op_srl_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = s.r[(op >> 4) & 0xF]
        s._shift_buf = 0
        s._shift_right()
        s.r[n] = s._op0

    def op_srl_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = (op >> 4) & 7
        s._shift_buf = 0
        s._shift_right()
        s.r[n] = s._op0

    def op_srlc_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = s.r[(op >> 4) & 0xF]
        s._shift_buf = s.r[(n + 1) & 15]
        s._shift_right()
        s.r[n] = s._op0

    def op_srlc_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = (op >> 4) & 7
        s._shift_buf = s.r[(n + 1) & 15]
        s._shift_right()
        s.r[n] = s._op0

    def op_sra_r_r(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = s.r[(op >> 4) & 0xF]
        s._shift_buf = 0
        msb = s._op0 & 0x80
        s._shift_right()
        if msb:
            s._op0 |= (0xFF >> (s._op1 & 7)) ^ 0xFF
        s.r[n] = s._op0 & 0xFF

    def op_sra_r_i(s, op):
        n = (op >> 8) & 0xF
        s._op0 = s.r[n]; s._op1 = (op >> 4) & 7
        s._shift_buf = 0
        msb = s._op0 & 0x80
        s._shift_right()
        if msb:
            s._op0 |= (0xFF >> (s._op1 & 7)) ^ 0xFF
        s.r[n] = s._op0 & 0xFF

    # ---- load / store ----
    def _ls(s, offset, length, st):
        """对应 LoadStore：R8 直接寻址寄存器，偶数长度对齐"""
        reg_base = s._ls_base
        if length % 2 == 0:
            offset &= ~1
        if st:
            for ix in range(length - 1, -1, -1):
                s.mmu.write8(s._da(offset + ix), s.r[reg_base + ix])
        else:
            for ix in range(length):
                v = s.mmu.read8(s._da(offset + ix))
                s._zs(v)
                s.r[reg_base + ix] = v

    def op_l_r_er(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.get_er((op >> 4) & 0xE), 1, False)

    def op_st_r_er(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.get_er((op >> 4) & 0xE), 1, True)

    def op_l_er_er(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.get_er((op >> 4) & 0xE), 2, False)

    def op_st_er_er(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.get_er((op >> 4) & 0xE), 2, True)

    def op_l_r_d16_er(s, op):
        d = s.fetch()
        s._ls_base = (op >> 8) & 0xF
        s._ls((s.get_er((op >> 4) & 0xE) + d) & 0xFFFF, 1, False)

    def op_st_r_d16_er(s, op):
        d = s.fetch()
        s._ls_base = (op >> 8) & 0xF
        s._ls((s.get_er((op >> 4) & 0xE) + d) & 0xFFFF, 1, True)

    def op_l_er_d16_er(s, op):
        d = s.fetch()
        s._ls_base = (op >> 8) & 0xE
        s._ls((s.get_er((op >> 4) & 0xE) + d) & 0xFFFF, 2, False)

    def op_st_er_d16_er(s, op):
        d = s.fetch()
        s._ls_base = (op >> 8) & 0xE
        s._ls((s.get_er((op >> 4) & 0xE) + d) & 0xFFFF, 2, True)

    def op_l_r_d(s, op):
        a = s.fetch()
        s._ls_base = (op >> 8) & 0xF
        s._ls(a, 1, False)

    def op_st_r_d(s, op):
        a = s.fetch()
        s._ls_base = (op >> 8) & 0xF
        s._ls(a, 1, True)

    def op_l_er_d(s, op):
        a = s.fetch()
        s._ls_base = (op >> 8) & 0xE
        s._ls(a, 2, False)

    def op_st_er_d(s, op):
        a = s.fetch()
        s._ls_base = (op >> 8) & 0xE
        s._ls(a, 2, True)

    def op_l_r_ea(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.ea, 1, False)

    def op_st_r_ea(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.ea, 1, True)

    def op_l_er_ea(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.ea, 2, False)

    def op_st_er_ea(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.ea, 2, True)

    def op_l_xr_ea(s, op):
        s._ls_base = (op >> 8) & 0xC
        s._ls(s.ea, 4, False)

    def op_st_xr_ea(s, op):
        s._ls_base = (op >> 8) & 0xC
        s._ls(s.ea, 4, True)

    def op_l_qr_ea(s, op):
        s._ls_base = (op >> 8) & 0x8
        s._ls(s.ea, 8, False)

    def op_st_qr_ea(s, op):
        s._ls_base = (op >> 8) & 0x8
        s._ls(s.ea, 8, True)

    def _ea_ia(s, length):
        s.ea = (s.ea + length) & 0xFFFF
        if length != 1:
            s.ea &= ~1

    def op_l_r_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.ea, 1, False)
        s._ea_ia(1)

    def op_st_r_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s.ea, 1, True)
        s._ea_ia(1)

    def op_l_er_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.ea, 2, False)
        s._ea_ia(2)

    def op_st_er_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s.ea, 2, True)
        s._ea_ia(2)

    def op_l_xr_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xC
        s._ls(s.ea, 4, False)
        s._ea_ia(4)

    def op_st_xr_ea_p(s, op):
        s._ls_base = (op >> 8) & 0xC
        s._ls(s.ea, 4, True)
        s._ea_ia(4)

    def op_l_qr_ea_p(s, op):
        s._ls_base = (op >> 8) & 0x8
        s._ls(s.ea, 8, False)
        s._ea_ia(8)

    def op_st_qr_ea_p(s, op):
        s._ls_base = (op >> 8) & 0x8
        s._ls(s.ea, 8, True)
        s._ea_ia(8)

    def _bpfp(s, op, base_reg):
        d = op & 0x3F
        if d & 0x20:
            d |= 0xFFC0
        return (s.get_er(base_reg) + d) & 0xFFFF

    def op_l_r_bp(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s._bpfp(op, 12), 1, False)

    def op_l_r_fp(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s._bpfp(op, 14), 1, False)

    def op_st_r_bp(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s._bpfp(op, 12), 1, True)

    def op_st_r_fp(s, op):
        s._ls_base = (op >> 8) & 0xF
        s._ls(s._bpfp(op, 14), 1, True)

    def op_l_er_bp(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s._bpfp(op, 12), 2, False)

    def op_l_er_fp(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s._bpfp(op, 14), 2, False)

    def op_st_er_bp(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s._bpfp(op, 12), 2, True)

    def op_st_er_fp(s, op):
        s._ls_base = (op >> 8) & 0xE
        s._ls(s._bpfp(op, 14), 2, True)

    # ---- 协处理器 ----
    def op_mov_cr_r(s, op):
        s.cr[(op >> 8) & 0xF] = s.r[(op >> 4) & 0xF]

    def op_mov_r_cr(s, op):
        s.r[(op >> 8) & 0xF] = s.cr[(op >> 4) & 0xF]

    def _cr_ea(s, op, size, st, ia):
        base = (op >> 8) & 0xF
        if st:
            for ix in range(size - 1, -1, -1):
                s.mmu.write8(s._da(s.ea + ix), s.cr[base + ix])
        else:
            for ix in range(size):
                s.cr[base + ix] = s.mmu.read8(s._da(s.ea + ix))
        if ia:
            s._ea_ia(size)

    def op_l_cr1_ea(s, op): s._cr_ea(op, 1, False, False)
    def op_l_cr1_ea_p(s, op): s._cr_ea(op, 1, False, True)
    def op_l_cr2_ea(s, op): s._cr_ea(op, 2, False, False)
    def op_l_cr2_ea_p(s, op): s._cr_ea(op, 2, False, True)
    def op_l_cr4_ea(s, op): s._cr_ea(op, 4, False, False)
    def op_l_cr4_ea_p(s, op): s._cr_ea(op, 4, False, True)
    def op_l_cr8_ea(s, op): s._cr_ea(op, 8, False, False)
    def op_l_cr8_ea_p(s, op): s._cr_ea(op, 8, False, True)
    def op_st_cr1_ea(s, op): s._cr_ea(op, 1, True, False)
    def op_st_cr1_ea_p(s, op): s._cr_ea(op, 1, True, True)
    def op_st_cr2_ea(s, op): s._cr_ea(op, 2, True, False)
    def op_st_cr2_ea_p(s, op): s._cr_ea(op, 2, True, True)
    def op_st_cr4_ea(s, op): s._cr_ea(op, 4, True, False)
    def op_st_cr4_ea_p(s, op): s._cr_ea(op, 4, True, True)
    def op_st_cr8_ea(s, op): s._cr_ea(op, 8, True, False)
    def op_st_cr8_ea_p(s, op): s._cr_ea(op, 8, True, True)

    # ---- 控制寄存器 ----
    def op_add_sp_i8(s, op):
        i = op & 0xFF
        if i & 0x80:
            i |= 0xFF00
        s.sp = (s.sp + i) & 0xFFFE

    def op_mov_ecsr_r(s, op): s.ecsr[s.el] = s.r[(op >> 4) & 0xF]
    def op_mov_elr_er(s, op): s.elr[s.el] = s.get_er((op >> 4) & 0xE)
    def op_mov_epsw_r(s, op):
        if s.el:
            s.epsw[s.el] = s.r[(op >> 4) & 0xF]
    def op_mov_er_elr(s, op): s.set_er((op >> 8) & 0xE, s.elr[s.el])
    def op_mov_er_sp(s, op):  s.set_er((op >> 8) & 0xE, s.sp)
    def op_mov_psw_r(s, op):  s.psw = s.r[(op >> 4) & 0xF]
    def op_mov_psw_i(s, op):  s.psw = op & 0xFF
    def op_mov_r_ecsr(s, op): s.r[(op >> 8) & 0xF] = s.ecsr[s.el]
    def op_mov_r_epsw(s, op):
        if s.el:
            s.r[(op >> 8) & 0xF] = s.epsw[s.el]
    def op_mov_r_psw(s, op):  s.r[(op >> 8) & 0xF] = s.psw
    def op_mov_sp_er(s, op):  s.sp = s.get_er((op >> 4) & 0xE) & 0xFFFE

    def op_ei(s, op):   s.psw |= MIE
    def op_di(s, op):   s.psw &= ~MIE
    def op_sc(s, op):   s.psw |= C
    def op_rc(s, op):   s.psw &= ~C
    def op_cplc(s, op): s.psw ^= C

    # ---- EA / ALU ----
    def op_lea_er(s, op): s.ea = s.get_er((op >> 4) & 0xE)
    def op_lea_d16_er(s, op):
        d = s.fetch()
        s.ea = (s.get_er((op >> 4) & 0xE) + d) & 0xFFFF
    def op_lea_d(s, op): s.ea = s.fetch()

    def op_daa(s, op):
        n = (op >> 8) & 0xF
        v = s.r[n]
        add = 0
        if (v & 0x0F) > 0x09 or (s._fin & HC): add |= 0x06
        if (v & 0xF0) > 0x90 or (s._fin & C): add |= 0x60
        if (v & 0xF0) == 0x90 and (v & 0x0F) > 0x09 and not (s._fin & HC): add |= 0x60
        backup = s._fin
        s._fin &= ~C; s._fin |= Z
        s._op0, s._op1 = v, add
        s._op0 = s._add8(0)
        s._zs(s._op0)
        s._fout |= backup & C
        s._fchg &= ~OV
        s.r[n] = s._op0

    def op_das(s, op):
        n = (op >> 8) & 0xF
        v = s.r[n]
        sub = 0
        if (v & 0x0F) > 0x09 or (s._fin & HC): sub |= 0x06
        if (v & 0xF0) > 0x90 or (s._fin & C): sub |= 0x60
        backup = s._fin
        s._fin &= ~C; s._fin |= Z
        s._op0 = v ^ 0xFF
        s._op1 = sub
        s._op0 = s._add8(0)
        r = (s._op0 ^ 0xFF) & 0xFF
        s._zs(r)
        s._fout |= backup & C
        s._fchg &= ~OV
        s.r[n] = r

    def op_neg(s, op):
        n = (op >> 8) & 0xF
        s._fin &= ~C; s._fin |= Z
        s._op0 = 0 ^ 0xFF
        s._op1 = s.r[n]
        s._op0 = s._add8(0)
        r = (s._op0 ^ 0xFF) & 0xFF
        s._zs(r)
        s.r[n] = r

    def op_inc_ea(s, op):
        v = s.mmu.read8(s._da(s.ea))
        s._fin &= ~C; s._fin |= Z
        s._op0, s._op1 = v, 1
        s._op0 = s._add8(0)
        s._zs(s._op0)
        s._fchg &= ~C
        s.mmu.write8(s._da(s.ea), s._op0)

    def op_dec_ea(s, op):
        v = s.mmu.read8(s._da(s.ea))
        s._fin &= ~C; s._fin |= Z
        s._op0 = v ^ 0xFF
        s._op1 = 1
        s._op0 = s._add8(0)
        r = (s._op0 ^ 0xFF) & 0xFF
        s._zs(r)
        s._fchg &= ~C
        s.mmu.write8(s._da(s.ea), r)

    # ---- 位操作 ----
    def _bitmod(s, op, mode):
        b = (op >> 4) & 7
        bit = 1 << b
        if op & 0x0080:                       # 直接寻址（H_TI）
            addr = s.fetch()
            v = s.mmu.read8(s._da(addr))
        else:
            v = s.r[(op >> 8) & 0xF]
        s._fchg |= Z
        s._fout = 0 if (v & bit) else Z
        if mode == "sb":
            v |= bit
        elif mode == "rb":
            v &= ~bit
        if mode != "tb":
            if op & 0x0080:
                s.mmu.write8(s._da(addr), v)
            else:
                s.r[(op >> 8) & 0xF] = v

    def op_sb_r(s, op): s._bitmod(op, "sb")
    def op_rb_r(s, op): s._bitmod(op, "rb")
    def op_tb_r(s, op): s._bitmod(op, "tb")
    def op_sb_d(s, op): s._bitmod(op, "sb")
    def op_rb_d(s, op): s._bitmod(op, "rb")
    def op_tb_d(s, op): s._bitmod(op, "tb")

    # ---- 符号扩展 ----
    def op_extbw(s, op):
        index = (op & 0x00E0) >> 4
        s.r[index + 1] = 0xFF if s.r[index] & 0x80 else 0x00
        s._zs(s.r[index + 1])

    # ---- 乘除 ----
    def op_mul(s, op):
        n = (op >> 8) & 0xE
        res = (s.r[n] * s.r[(op >> 4) & 0xF]) & 0xFFFF
        s._fchg |= Z
        s._fout = 0 if res else Z
        s.set_er(n, res)

    def op_div(s, op):
        n = (op >> 8) & 0xE
        m = (op >> 4) & 0xF
        d = s.r[m]
        s._fchg |= Z | C
        if d == 0:
            s._fout |= C
            return
        q = s.get_er(n) // d
        rem = s.get_er(n) % d
        if q:
            s._fout &= ~Z
        s.set_er(n, q)
        s.r[m] = rem

    # ---- DSR ----
    def op_dsr_i8(s, op):
        s.dsr_last = op & 0xFF
        s.dsr = s.dsr_last
        s.dsr_active = True

    def op_dsr_r(s, op):
        s.dsr_last = s.r[(op >> 4) & 0xF]
        s.dsr = s.dsr_last
        s.dsr_active = True

    def op_dsr_dsr(s, op):
        s.dsr = s.dsr_last
        s.dsr_active = True

    # ---- PUSH/POP ----
    def op_push_r(s, op):
        n = (op >> 8) & 0xF
        size = 2
        s.sp = (s.sp - size) & 0xFFFF
        s.mmu.write8(s.sp, s.r[n])
        s.mmu.write8((s.sp + 1) & 0xFFFF, 0)

    def op_push_er(s, op):
        n = (op >> 8) & 0xE
        size = 2
        s.sp = (s.sp - size) & 0xFFFF
        s.mmu.write8(s.sp, s.get_er(n) & 0xFF)
        s.mmu.write8((s.sp + 1) & 0xFFFF, (s.get_er(n) >> 8) & 0xFF)

    def op_push_xr(s, op):
        n = (op >> 8) & 0xC
        size = 4
        v = s.get_xr(n)
        s.sp = (s.sp - size) & 0xFFFF
        for ix in range(size):
            s.mmu.write8((s.sp + ix) & 0xFFFF, (v >> (8 * ix)) & 0xFF)

    def op_push_qr(s, op):
        n = (op >> 8) & 0x8
        size = 8
        v = sum(s.r[n + ix] << (8 * ix) for ix in range(8))
        s.sp = (s.sp - size) & 0xFFFF
        for ix in range(size):
            s.mmu.write8((s.sp + ix) & 0xFFFF, (v >> (8 * ix)) & 0xFF)

    def op_push_l(s, op):
        lst = (op >> 8) & 0xF
        if lst & 2:
            s.push16(s.ecsr[s.el])
            s.push16(s.elr[s.el])
        if lst & 4:
            s.push16(s.epsw[s.el])
        if lst & 8:
            s.push16(s.lcsr)
            s.push16(s.lr)
        if lst & 1:
            s.push16(s.ea)

    def op_pop_r(s, op):
        n = (op >> 8) & 0xF
        s.r[n] = s.mmu.read8(s.sp)
        s.sp = (s.sp + 2) & 0xFFFF

    def op_pop_er(s, op):
        n = (op >> 8) & 0xE
        s.set_er(n, s.pop16())

    def op_pop_xr(s, op):
        n = (op >> 8) & 0xC
        v = 0
        for ix in range(4):
            v |= s.mmu.read8((s.sp + ix) & 0xFFFF) << (8 * ix)
        s.sp = (s.sp + 4) & 0xFFFF
        s.set_xr(n, v)

    def op_pop_qr(s, op):
        n = (op >> 8) & 0x8
        for ix in range(8):
            s.r[n + ix] = s.mmu.read8((s.sp + ix) & 0xFFFF)
        s.sp = (s.sp + 8) & 0xFFFF

    def op_pop_l(s, op):
        lst = (op >> 8) & 0xF
        if lst & 1:
            s.ea = s.pop16()
        if lst & 8:
            s.lr = s.pop16()
            s.lcsr = s.pop16() & 0xF
        if lst & 4:
            s.psw = s.pop16() & 0xFF
        if lst & 2:
            s.pc = s.pop16()
            s.csr = s.pop16() & 0xF

    # ---- 分支 ----
    def op_bcond(s, op):
        fin = s._fin
        c = bool(fin & C); z = bool(fin & Z)
        sflag = bool(fin & S); ov = bool(fin & OV)
        le = z | c
        lts = ov ^ sflag
        les = lts | z
        cond = (op >> 8) & 0xF
        branch = {
            0: not c, 1: c, 2: not le, 3: le, 4: not lts, 5: lts,
            6: not les, 7: les, 8: not z, 9: z, 10: not ov, 11: ov,
            12: not sflag, 13: sflag,
        }.get(cond, True)
        if branch:
            d = op & 0xFF
            if d & 0x80:
                d |= 0x7F00
            s.pc = (s.pc + (d << 1)) & 0xFFFF

    def op_b_cadr(s, op):
        a = s.fetch()                  # 目标字从旧 csr 段取（先取后改）
        s.csr = (op >> 8) & 0xF
        s.pc = a

    def op_b_er(s, op):
        s.pc = s.get_er((op >> 4) & 0xE)

    def op_bl_cadr(s, op):
        a = s.fetch()
        s.lr = s.pc
        s.lcsr = s.csr
        s.csr = (op >> 8) & 0xF
        s.pc = a

    def op_bl_er(s, op):
        s.lr = s.pc
        s.lcsr = s.csr
        s.pc = s.get_er((op >> 4) & 0xE)

    def op_rt(s, op):
        s.csr = s.lcsr
        s.pc = s.lr

    def op_rti(s, op):
        el = s.el
        s.csr = s.ecsr[el]
        s.pc = s.elr[el]
        s.psw = s.epsw[el]

    def op_swi(s, op):
        s.emu.raise_software(op & 0x3F)

    def op_brk(s, op):
        s.emu.on_brk()

    def op_nop(s, op):
        pass
