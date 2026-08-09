# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
#
# 语义与 CasioEmuNeo/emulator/Peripheral/*.cpp 一致：
#   - Screen: VRAM 0xF800, (N_ROW+1)*ROW_SIZE 字节；第 0 行=状态符号行，
#     像素行 y 的数据在 buffer 第 y+1 行的 [0, ROW_SIZE_DISP) 字节（MSB 位序）
#   - Keyboard: KI=0xF040(低有效), KOMask=0xF044, KO=0xF046(10位)，
#     含 ghost 连接分量逻辑；键码 code = ko<<4|ki
#   - Timer: interval=0xF020, counter=0xF022(读清零), control=0xF025, idx=9
#   - Standby: STPACP=0xF008, SBYCON=0xF009
import time
from collections import deque
from .memory import Region


class LCD:
    def __init__(self, cfg, mmu):
        self.mmu = mmu
        self.region = None
        self.enabled = True
        self.mode = 0          # 0xF031：4/5/6 才点亮点阵
        self.contrast = 8      # 0xF032
        self.configure(cfg.lcd_base, cfg.lcd_w, cfg.lcd_h,
                       cfg.lcd_stride, cfg.lcd_row_skip,
                       getattr(cfg, "lcd_disp_bytes", 0),
                       getattr(cfg, "lcd_layout", "row_msb"))

    def configure(self, base, w, h, stride, row_skip=1, disp_bytes=0,
                  layout="row_msb"):
        """运行时重绑定（:lcd 命令用）。disp_bytes=每行可写字节数（0=全部）。"""
        if self.region:
            self.mmu.remove_region(self.region)
        self.base, self.w, self.h = base, w, h
        self.stride, self.row_skip = stride, row_skip
        self.disp_bytes = disp_bytes or stride
        self.layout = layout
        rows = (h + 7) // 8 if layout == "page" else h + row_skip
        self.size = stride * rows
        self.vram = bytearray(self.size)
        self.region = self.mmu.add_region(
            Region(base, self.size, "VRAM",
                   reader=self._read, writer=self._write, prio=10))

    def _read(self, addr):
        o = addr - self.base
        if o % self.stride >= self.disp_bytes:
            return 0
        return self.vram[o]

    def _write(self, addr, v):
        o = addr - self.base
        if o % self.stride >= self.disp_bytes:
            return
        self.vram[o] = v & 0xFF

    def frame(self):
        """-> (status_row, [pixel_row...])，值 0/1。状态行=第 0 行 disp_bytes 字节"""
        v, w, h, st, sk = self.vram, self.w, self.h, self.stride, self.row_skip
        lay = self.layout
        rows = (h + 7) // 8 if lay == "page" else h
        out = []
        if self.mode in (4, 5, 6):
            if lay == "page":
                for y in range(h):
                    row = bytearray(w)
                    b = (y >> 3) * st
                    sh = y & 7
                    for x in range(w):
                        row[x] = (v[b + (x >> 3)] >> sh) & 1
                    out.append(row)
            else:
                for y in range(h):
                    row = bytearray(w)
                    b = (y + sk) * st
                    if lay == "row_msb":
                        for x in range(w):
                            row[x] = (v[b + (x >> 3)] >> (7 - (x & 7))) & 1
                    else:  # row_lsb
                        for x in range(w):
                            row[x] = (v[b + (x >> 3)] >> (x & 7)) & 1
                    out.append(row)
        else:
            for _ in range(h):
                out.append(bytearray(w))
        status = bytearray(w)
        if self.mode in (5, 6):
            for x in range(min(w, self.disp_bytes * 8)):
                status[x] = (v[x >> 3] >> (7 - (x & 7))) & 1
        return status, out

    def status_bytes(self):
        return bytes(self.vram[0:self.disp_bytes])

    def nonzero(self):
        return sum(1 for b in self.vram if b)


POWER_CODE = 0xFF


class Keyboard:
    """矩阵键盘。键码 code = ko<<4 | ki (0x00~0x67 范围)，0xFF = POWER。

    保持时长以【模拟周期】为准（hold_ms * freq / 1000），宿主速度不影响按键收入；
    --hold-unit wall 时也可按墙钟。KI 低有效（默认 0xFF，按下清位）。"""

    def __init__(self, cfg, emu):
        self.cfg = cfg
        self.emu = emu
        self.cpu = emu.cpu
        self.ko = 0
        self.ko_mask = 0
        self.input_filter = 0
        self.held = set()               # 按住的键码
        self.power = False
        self._rel_cyc = {}              # code -> 到期模拟周期
        self._rel_wall = {}             # code -> 到期 time.monotonic()
        self.events = deque(maxlen=cfg.keylog_size)
        self.log_enabled = False
        self._last_ki = None
        self.ghost = [0] * 8
        self._irq_bit = 1 << (cfg.ki_vector // 2 - 4)
        self._build_maps()
        self.recalc_ghost()

    # ---------------- 名称 / 键码 映射 ----------------
    def _build_maps(self):
        self.code_by_name, self.name_by_code = {}, {}
        for name, v in self.cfg.keys.items():
            if name == self.cfg.power_key:
                code = POWER_CODE
            elif isinstance(v, int):
                code = v & 0xFF
            else:
                code = ((v[0] & 0xF) << 4) | (v[1] & 0x7)
            self.code_by_name[name] = code
            self.name_by_code.setdefault(code, name)
        if self.cfg.power_key and self.cfg.power_key not in self.code_by_name:
            self.code_by_name[self.cfg.power_key] = POWER_CODE
            self.name_by_code.setdefault(POWER_CODE, self.cfg.power_key)

    def code_of(self, name):
        c = self.code_by_name.get(name)
        if c is None:
            raise KeyError(f"unknown key name: {name!r}")
        return c

    def name_of(self, code):
        if code is None:
            return None
        return self.name_by_code.get(code & 0xFF)

    def valid(self, code):
        if code == POWER_CODE:
            return True
        return (code >> 4) < self.cfg.ko_count and (code & 0xF) < self.cfg.ki_count

    # ---------------- 事件日志 (F4) ----------------
    def _ev(self, kind, code=None, extra=""):
        if not self.log_enabled:
            return
        self.events.append({
            "t": time.strftime("%H:%M:%S"), "cyc": self.cpu.cycles,
            "kind": kind, "code": code,
            "name": self.name_of(code) if code is not None else None,
            "ko": None if code is None else (code >> 4),
            "ki": None if code is None else (code & 0xF),
            "extra": extra,
        })
        if code is None:
            self.emu.logmsg(f"[key] {kind} {extra}")
        else:
            self.emu.logmsg(
                f"[key] {kind} {self.name_of(code)} code=0x{code:02X} "
                f"(ko{code >> 4},ki{code & 0xF}) cyc={self.cpu.cycles} {extra}")

    def keylog(self, on=True):
        self.log_enabled = bool(on)
        return self.log_enabled

    # ---------------- 按下 / 释放 ----------------
    def press_code(self, code, hold_ms=None, wall=False):
        """按住。hold_ms=None → 一直按住直到显式释放。"""
        code &= 0xFF
        if not self.valid(code):
            self.emu.logmsg(f"[key] ignore illegal code 0x{code:02X}")
            return False
        if code in self.held or (code == POWER_CODE and self.power):
            # 同键重按 → 先释放再按下，重置计时
            self._ev("repress", code)
            self.release_code(code, quiet=True)
        if code == POWER_CODE:
            if not self.power:
                # 开机键 = 芯片复位（硬件接复位线，跳 0x0002 向量）
                # 对应 CasioEmuMsvc PressButton: chipset.Reset()
                self.emu.reset()
            self.power = True
        else:
            self.held.add(code)
        self.recalc_ghost()
        self._schedule(code, hold_ms, wall)
        self._ev("press", code, f"hold={hold_ms}ms" if hold_ms else "hold=∞")
        return True

    def release_code(self, code, quiet=False):
        code &= 0xFF
        if code == POWER_CODE:
            self.power = False
        self.held.discard(code)
        self.recalc_ghost()
        self._rel_cyc.pop(code, None)
        self._rel_wall.pop(code, None)
        if not quiet:
            self._ev("release", code)
        return True

    def tap_code(self, code, hold_ms=50, wall=False):
        return self.press_code(code, hold_ms=hold_ms, wall=wall)

    # 名称接口（向后兼容）
    def press(self, name, hold_ms=None):
        return self.press_code(self.code_of(name), hold_ms)

    def release(self, name):
        return self.release_code(self.code_of(name))

    def release_all(self):
        for c in list(self.held) + ([POWER_CODE] if self.power else []):
            self.release_code(c)

    def held_codes(self):
        return sorted(self.held) + ([POWER_CODE] if self.power else [])

    def held_names(self):
        return [self.name_of(c) or f"0x{c:02X}" for c in self.held_codes()]

    # ---------------- 定时释放调度 ----------------
    def _schedule(self, code, hold_ms, wall):
        if not hold_ms:
            return
        if wall:
            self._rel_wall[code] = time.monotonic() + hold_ms / 1000.0
        else:
            self._rel_cyc[code] = self.cpu.cycles + int(
                self.cfg.freq * hold_ms / 1000)

    def tick(self):
        """帧级调度：到期释放。中断断言见 _irq_assert（每指令调用）。"""
        cyc = self.cpu.cycles
        if self._rel_cyc:
            for code, at in list(self._rel_cyc.items()):
                if cyc >= at:
                    self._ev("auto-release", code)
                    self.release_code(code, quiet=True)
        if self._rel_wall:
            now = time.monotonic()
            for code, at in list(self._rel_wall.items()):
                if now >= at:
                    self._ev("auto-release", code, "(wall)")
                    self.release_code(code, quiet=True)

    def _irq_assert(self):
        """每指令调用（热路径）：键盘中断电平断言 + input_filter 门控。

        POWER(ON) 是硬线唤醒（真实硬件走芯片复位线），不受 input_filter 门控，
        否则关机/复位后固件 filter=0 时按 ON 永远无法开机；
        其余键只在固件开过滤(0xFF)的空闲窗口生效，处理键时 filter=0 不重复触发。"""
        if self.power or (self.held and self.input_filter):
            if not (self.emu.int_pending & self._irq_bit):
                self.emu.raise_maskable(self.cfg.ki_vector // 2)

    # ---------------- SFR 读写 ----------------
    def read_ki(self):
        c = self.cfg
        ghosted = 0
        for ix in range(c.ko_count):
            if self.ko & ~self.ko_mask & (1 << ix):
                ghosted |= self.ghost[ix]
        if c.ki_active_low:
            ki = (1 << c.ki_count) - 1
            for code in self.held:
                ki_bit = 1 << (code & 7)
                if (self.ko == 0 and c.ki_all_when_ko_zero) \
                        or ((1 << (code >> 4)) & ghosted):
                    ki &= ~ki_bit
        else:
            ki = 0
            for code in self.held:
                ki_bit = 1 << (code & 7)
                if (self.ko == 0 and c.ki_all_when_ko_zero) \
                        or ((1 << (code >> 4)) & ghosted):
                    ki |= ki_bit
            ki &= (1 << c.ki_count) - 1
        if self.log_enabled and (ki, self.ko) != self._last_ki:
            self._last_ki = (ki, self.ko)
            self._ev("ki-read", None,
                     f"KO=0x{self.ko:03X} KI=0x{ki:02X} held={self.held_names()}")
        return ki

    def write_ko(self, addr, v):
        o = addr - 0xF046
        self.ko = ((self.ko & ~(0xFF << (8 * o))) | (v << (8 * o))) & 0x03FF

    def read_ko(self, addr):
        return (self.ko >> (8 * (addr - 0xF046))) & 0xFF

    def write_ko_mask(self, addr, v):
        o = addr - 0xF044
        self.ko_mask = ((self.ko_mask & ~(0xFF << (8 * o))) | (v << (8 * o))) & 0x03FF

    def read_ko_mask(self, addr):
        return (self.ko_mask >> (8 * (addr - 0xF044))) & 0xFF

    # ---- 对应 RecalculateGhost（3 角幻影键检测）----
    def recalc_ghost(self):
        m = [[False] * 8 for _ in range(8)]
        for code in self.held:
            if code < 0x80:
                m[code >> 4][code & 7] = True
        conn = [0] * 8
        for cx in range(8):
            for rx in range(8):
                if m[cx][rx]:
                    for ax in range(8):
                        if m[ax][rx]:
                            conn[cx] |= 1 << ax
        seen = [False] * 8
        self.ghost = [0] * 8
        for cx in range(8):
            if seen[cx] or not conn[cx]:
                continue
            to_visit, mask = 1 << cx, 1 << cx
            seen[cx] = True
            while to_visit:
                new_visit = 0
                for vx in range(8):
                    if to_visit & (1 << vx):
                        for sx in range(8):
                            if (conn[vx] & (1 << sx)) and not seen[sx]:
                                new_visit |= 1 << sx
                                mask |= 1 << sx
                                seen[sx] = True
                to_visit = new_visit
            for gx in range(8):
                if mask & (1 << gx):
                    self.ghost[gx] = mask


class KeySequencer:
    """按队列顺序敲键。item = (kind, code, a, b)
       kind: key(a=hold_ms, b=gap_ms) / wait(a=ms) / hold(按住不放) / up(释放)
       时序一律按【模拟周期】计（hold_ms * freq / 1000）。"""

    def __init__(self, kb, cfg, cpu, emu=None):
        self.kb, self.cfg, self.cpu, self.emu = kb, cfg, cpu, emu
        self.q = deque()
        self.cur = None
        self.until = 0
        self.default_hold_ms = 50
        self.default_gap_ms = 50
        self.done = 0
        self._woke = None             # 本键是否已唤醒固件（处理完成判定）

    def _c(self, ms):
        return int(self.cfg.freq * ms / 1000)

    # ---- 入队 ----
    def key(self, code, hold_ms=None, gap_ms=None):
        self.q.append(("key", code & 0xFF,
                       self.default_hold_ms if hold_ms is None else hold_ms,
                       self.default_gap_ms if gap_ms is None else gap_ms))
        return len(self.q)

    def wait(self, ms):   self.q.append(("wait", None, ms, 0))
    def hold(self, code): self.q.append(("hold", code & 0xFF, 0, 0))
    def up(self, code):   self.q.append(("up", code & 0xFF, 0, 0))
    def submit(self, items):
        self.q.extend(items)
        return len(self.q)

    def clear(self, release=True):
        n = len(self.q) + (1 if self.cur else 0)
        self.q.clear()
        if self.cur and self.cur[0] == "key" and release:
            self.kb.release_code(self.cur[1])
        self.cur = None
        return n

    @property
    def busy(self):    return bool(self.q or self.cur)
    @property
    def pending(self): return len(self.q) + (1 if self.cur else 0)

    def peek(self, n=6):
        out = []
        if self.cur:
            if self.cur[1] is not None:
                out.append("*" + (self.kb.name_of(self.cur[1]) or self.cur[0]))
            else:
                out.append(f"*w{self.cur[2]}")     # wait 项无键码
        for it in list(self.q)[:n]:
            out.append(self.kb.name_of(it[1]) if it[1] is not None else f"w{it[2]}")
        return out

    # ---- 驱动 ----
    def tick(self):
        cyc = self.cpu.cycles
        for _ in range(64):                      # 防死循环
            if self.cur is not None:
                kind, code, a, b = self.cur
                if kind == "waitidle":
                    # 上一键处理完：等固件完全回到 idle 扫描态（halted +
                    # input_filter 已重开），再按下一个键，保证新键能被唤醒。
                    if cyc >= self.until:
                        self.cur = None          # 超时兜底，继续
                        continue
                    if self.emu.cpu.halted and self.kb.input_filter:
                        self.cur = None
                        continue
                    return
                done = False
                if cyc >= self.until:
                    done = True                  # hold 超时兜底
                elif kind == "key" and self._woke is not None:
                    h = self.emu.cpu.halted
                    if h and self._woke and self.kb.input_filter:
                        done = True              # 唤醒过且已回 idle = 处理完成
                    if not h:
                        self._woke = True        # 固件已被本键唤醒
                if not done:
                    return
                self.cur = None
                if kind == "key":
                    self.kb.release_code(code)
                    self.done += 1
                    self._woke = None
                    if b > 0:                    # 进入 gap
                        self.cur = ("gap", None, b, 0)
                        self.until = cyc + self._c(b)
                        return
                    self.cur = ("waitidle", None, 0, 0)
                    self.until = cyc + self._c(max(a * 3, 200))
                    return
            if not self.q:
                return
            kind, code, a, b = item = self.q.popleft()
            if kind == "key":
                self.kb.press_code(code)
                self.cur = item
                self.until = cyc + self._c(max(a, 120))
                self._woke = None
                return
            if kind == "wait":
                self.cur = item
                self.until = cyc + self._c(a)
                return
            if kind == "hold":
                self.kb.press_code(code)
            elif kind == "up":
                self.kb.release_code(code)


class Timer:
    """interval=0xF020, counter=0xF022(写清零), control=0xF025, 中断 idx=9。
    ext_to_int: 每 CPS/10000 周期一个分频 tick。"""

    def __init__(self, cfg, emu):
        self.emu = emu
        self.interval = 1
        self.counter = 0
        self.control = 0
        self.ext_counter = 0
        self.ext_next = 0
        self.ext_done = 0
        self.raise_required = False

    def tick(self, cycles):
        cps = self.emu.cfg.freq
        remaining = cycles
        while remaining > 0:
            if self.ext_counter == self.ext_next:
                self.divide_ticks(cps)
                if self.raise_required:
                    # 挂起位是闩存器：即使 pending 已置位也不能丢触发（否则固件
                    # 带着未消费的 pending 进 STOP 后永远无法被定时器唤醒）
                    if (self.emu.int_mask & (1 << (9 - 4))):
                        self.emu.raise_maskable(9)
                    self.raise_required = False
            step = self.ext_next - self.ext_counter
            if step <= 0:
                step = 1
            if step > remaining:
                step = remaining
            self.ext_counter += step
            remaining -= step

    def cycles_until_raise(self, limit):
        """待机用：距离下一次定时器中断的周期数（模拟 divide_tick 序列，与 tick() 行为一致）。
        定时器未开/中断被屏蔽/已待决/超限 → 返回 limit。"""
        if limit <= 0 or not (self.control & 1):
            return limit
        bit = 1 << (9 - 4)
        if not (self.emu.int_mask & bit) or (self.emu.int_pending & bit):
            return limit
        cps = self.emu.cfg.freq
        cyc = 0
        ext_done, ext_counter, ext_next, counter = (
            self.ext_done, self.ext_counter, self.ext_next, self.counter)
        while cyc < limit:
            step = ext_next - ext_counter
            if step <= 0:
                step = 1
            if cyc + step > limit:
                return limit
            cyc += step
            ext_done += 1
            if ext_done == 10000:
                ext_done = 0
                ext_counter = 0
            ext_next = cps * (ext_done + 1) // 10000
            if counter == self.interval:
                return cyc
            counter += 1
        return limit

    def divide_ticks(self, cps):
        self.ext_done += 1
        if self.ext_done == 10000:
            self.ext_done = 0
            self.ext_counter = 0
        self.ext_next = cps * (self.ext_done + 1) // 10000
        if self.control & 1:
            if self.counter == self.interval:
                self.counter = 0
                if self.emu.int_mask & (1 << (9 - 4)):
                    self.raise_required = True
            self.counter += 1

    # ---- SFR ----
    def read_interval(self, addr):
        return (self.interval >> (8 * (addr - 0xF020))) & 0xFF

    def write_interval(self, addr, v):
        o = addr - 0xF020
        self.interval = (self.interval & ~(0xFF << (8 * o))) | (v << (8 * o))
        if not self.interval:
            self.interval = 0x10000          # 0 = 最大周期（16 位计数器回绕）

    def read_counter(self, addr):
        return (self.counter >> (8 * (addr - 0xF022))) & 0xFF

    def write_counter(self, addr, v):
        self.counter = 0

    def read_control(self, addr):
        return self.control & 0x01

    def write_control(self, addr, v):
        self.control = v & 0x01
        self.raise_required = False


class StandbyControl:
    def __init__(self, cfg, emu):
        self.emu = emu
        self.stpacp_last = 0
        self.stop_acceptor_enabled = False

    def read(self, addr):
        return 0x00

    def write(self, addr, v):
        if addr == 0xF008:
            if (v & 0xF0) == 0xA0 and (self.stpacp_last & 0xF0) == 0x50:
                self.stop_acceptor_enabled = True
            self.stpacp_last = v
        elif addr == 0xF009:
            if v & 0x01:
                self.emu.cpu.halted = True
                return
            if v & 0x02 and self.stop_acceptor_enabled:
                self.stop_acceptor_enabled = False
                self.emu.cpu.halted = True


class SFR:
    """SFR 转发：已知寄存器交给外设，其余落影子 RAM。

    地址表（fx-991CN X，CASIO ClassWiz）：
      0xF000 DSR / 0xF008-09 Standby / 0xF010-11 中断掩码 / 0xF014-15 中断挂起
      0xF020-22 定时器 / 0xF030-32 屏幕 / 0xF040-47 键盘 / 0xF048*8 / 0xF220*4
      13 个未知单字节寄存器 + 0xF050 等
    """

    def __init__(self, cfg, mmu, emu):
        self.emu = emu
        self.cfg = cfg
        self.mmu = mmu
        self.trace = False
        self.trace_log = []
        self.shadow = bytearray(0x800)          # 0xF000..0xF7FF
        self.regs = {}                          # addr -> (reader, writer)
        self._register(cfg)
        mmu.add_region(Region(cfg.sfr_base, 0x800, "SFR",
                              reader=self.read, writer=self.write, prio=1))

    def _r(self, addr, fn): self.regs[addr] = (fn, None)
    def _rw(self, addr, rd, wr): self.regs[addr] = (rd, wr)

    def _register(self, cfg):
        kb, tm, sc, sb = self.emu.keyboard, self.emu.timer, self.emu.lcd, self.emu.standby
        def _wr_dsr(a, v):
            self.emu.cpu.dsr = v
            self.emu.cpu.dsr_active = True   # 当前指令剩余访问生效
        self._rw(0xF000, None, _wr_dsr)
        self._rw(0xF008, sb.read, sb.write)
        self._rw(0xF009, sb.read, sb.write)
        self._rw(0xF010, self._read_mask, self._write_mask)
        self._rw(0xF011, self._read_mask, self._write_mask)
        self._rw(0xF014, self._read_pending, self._write_pending)
        self._rw(0xF015, self._read_pending, self._write_pending)
        self._rw(0xF020, tm.read_interval, tm.write_interval)
        self._rw(0xF021, tm.read_interval, tm.write_interval)
        self._rw(0xF022, tm.read_counter, tm.write_counter)
        self._rw(0xF023, tm.read_counter, tm.write_counter)
        self._rw(0xF025, tm.read_control, tm.write_control)
        self._rw(0xF030, self._read_byte, lambda a, v: setattr(sc, "range", v & 0x07))
        self._rw(0xF031, self._read_byte, lambda a, v: setattr(sc, "mode", v & 0x07))
        self._rw(0xF032, self._read_byte, lambda a, v: setattr(sc, "contrast", v & 0x3F))
        self._rw(0xF040, lambda a: kb.read_ki(), lambda a, v: None)
        self._rw(0xF042, self._read_byte, lambda a, v: setattr(kb, "input_filter", v))
        self._rw(0xF044, kb.read_ko_mask, kb.write_ko_mask)
        self._rw(0xF045, kb.read_ko_mask, kb.write_ko_mask)
        self._rw(0xF046, kb.read_ko, kb.write_ko)
        self._rw(0xF047, kb.read_ko, kb.write_ko)
        # 未知寄存器（影子 RAM）
        for a in (0xF00A, 0xF018, 0xF033, 0xF034, 0xF041, 0xF035, 0xF036,
                  0xF039, 0xF012, 0xF03D, 0xF224, 0xF028, 0xF310,
                  0xF048, 0xF049, 0xF04A, 0xF04B, 0xF04C, 0xF04D, 0xF04E, 0xF04F,
                  0xF220, 0xF221, 0xF222, 0xF223):
            self._rw(a, self._read_byte, self._write_byte)

    def _read_mask(self, addr):
        return (self.emu.int_mask >> (8 * (addr - 0xF010))) & 0xFF

    def _write_mask(self, addr, v):
        o = addr - 0xF010
        self.emu.int_mask = (self.emu.int_mask & ~(0xFF << (8 * o))) | (v << (8 * o))
        self.emu.int_mask &= 0x1FFF

    def _read_pending(self, addr):
        return (self.emu.int_pending >> (8 * (addr - 0xF014))) & 0xFF

    def _write_pending(self, addr, v):
        o = addr - 0xF014
        self.emu.int_pending = (self.emu.int_pending & ~(0xFF << (8 * o))) | (v << (8 * o))
        self.emu.int_pending &= 0x1FFF

    def _read_byte(self, addr):
        return self.shadow[addr - 0xF000]

    def _write_byte(self, addr, v):
        self.shadow[addr - 0xF000] = v & 0xFF

    # ---- MMU 入口 ----
    def read(self, addr):
        if self.trace:
            self.trace_log.append(("r", addr))
        h = self.regs.get(addr)
        if h and h[0]:
            return h[0](addr)
        return self.shadow[addr - 0xF000]

    def write(self, addr, v):
        if self.trace:
            self.trace_log.append(("w", addr, v))
        h = self.regs.get(addr)
        if h and h[1]:
            h[1](addr, v)
            return
        self.shadow[addr - 0xF000] = v & 0xFF
