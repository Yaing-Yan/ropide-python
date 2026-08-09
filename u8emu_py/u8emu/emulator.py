# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
#
# 中断系统（对应 Chipset::AcceptInterrupt）：
#   0xF010 中断掩码 / 0xF014 中断挂起（可屏蔽中断 idx 5..17，位 = idx-4）
#   优先级: reset(1) > software(0x40+) > emulator(3) > break(2) > nmi(4) > maskable
#   向量 = index*2；SWI index = 0x40+n
import pickle, time
from .memory import MMU, Region
from .cpu import CPU
from .peripherals import LCD, Keyboard, Timer, StandbyControl, SFR, KeySequencer

INT_RESET, INT_BREAK, INT_EMULATOR, INT_NMI, INT_MASKABLE = 1, 2, 3, 4, 5


class Emulator:
    def __init__(self, cfg, rom_path=None):
        self.cfg = cfg
        self.mmu = MMU(cfg.rom_size)
        self.cpu = CPU(self)
        self.paused = False
        self.breakpoints = set()
        self.log = []
        self.brk_hooks = []
        self.reset_hooks = []
        self.int_mask = 0          # 0xF010
        self.int_pending = 0       # 0xF014
        self.int_active = set()    # 待接受的中断 index
        # ROM 必须先于 _build_map() 装入（memoryview 钉住 code）
        if rom_path:
            self.load_rom(rom_path)
        self._build_map()
        self.reset()

    # ---------- memory map ----------
    def _build_map(self):
        c = self.mmu
        # 数据空间 ROM 段（含 DSR 访问的高段字库/常量表）
        for data_base, rom_base, size in self.cfg.rom_segments:
            self.mmu.add_region(Region(
                data_base, size, f"ROM@{data_base:05X}",
                data=memoryview(self.mmu.code)[rom_base:rom_base + size],
                writable=False, prio=0))
        rs, rsz = self.cfg.ram
        self.ram = bytearray(rsz)
        self.mmu.add_region(Region(rs, rsz, "RAM", data=self.ram, prio=2))
        # 先建外设再建 SFR（SFR 构造时注册引用）；页冲突靠 prio 裁决
        self.lcd = LCD(self.cfg, self.mmu)
        self.keyboard = Keyboard(self.cfg, self)
        self.keyseq = KeySequencer(self.keyboard, self.cfg, self.cpu, self)
        self.standby = StandbyControl(self.cfg, self)
        self.timer = Timer(self.cfg, self)
        self.sfr = SFR(self.cfg, self.mmu, self)
        self.patch_undo = []          # [(addr, bytes_before)]

    def load_rom(self, path):
        if getattr(self, "lcd", None) is not None:
            raise RuntimeError(
                "memory map 已构建（ROMWIN memoryview 钉住了 code），"
                "请用 Emulator(cfg, rom_path) 在构造时加载 ROM")
        with open(path, "rb") as f:
            data = f.read()
        self.mmu.code[:len(data)] = data
        self.rom_path = path
        self.logmsg(f"ROM loaded: {path} ({len(data)} bytes)")

    def reset(self):
        self.int_mask = 0
        self.int_pending = 0
        self.int_active.clear()
        self.cpu.reset()
        for cb in self.reset_hooks:
            cb()

    def logmsg(self, msg):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        del self.log[:-500]

    # ---------- 中断（对应 Chipset::Raise* / AcceptInterrupt）----------
    def raise_maskable(self, index):
        if index < INT_MASKABLE or index >= 0x40:
            raise ValueError(f"invalid maskable index {index}")
        if index not in self.int_active:
            self.int_active.add(index)

    def raise_software(self, n):
        self.int_active.add(0x40 + n)

    def raise_break(self):
        if self.cpu.el > 1:
            self.reset()
            self.logmsg("BRK with ELEVEL>1 -> reset")
            return
        self.int_active.add(INT_BREAK)

    def on_brk(self):
        self.raise_break()

    def raise_nmi(self):
        self.int_active.add(INT_NMI)

    def check_interrupts(self):
        if not self.int_active:
            return
        idx = None
        if INT_RESET in self.int_active:
            idx = INT_RESET
        elif any(i >= 0x40 for i in self.int_active):
            idx = min(i for i in self.int_active if i >= 0x40)
        elif INT_EMULATOR in self.int_active:
            idx = INT_EMULATOR
        elif INT_BREAK in self.int_active:
            idx = INT_BREAK
        elif INT_NMI in self.int_active and self.cpu.el <= 2:
            idx = INT_NMI
        elif self.cpu.el <= 1:
            for i in range(INT_MASKABLE, 0x40):
                if i in self.int_active:
                    idx = i
                    break
        if idx is None:
            return
        self.int_active.discard(idx)
        self.cpu.halted = False            # 接受中断即唤醒（对应 run_mode = RM_RUN）
        if INT_MASKABLE <= idx < 0x40:
            bit = 1 << (idx - 4)
            if not (self.int_mask & bit):
                return                     # 未使能：丢弃（已唤醒）
            self.int_pending |= bit
            if self.cpu.psw & 0x08:        # MIE
                self.int_pending &= ~bit   # 接受中断时硬件自动清挂起位（固件 ISR 不再写 0xF014）
                self.cpu.raise_int(1, idx)
        else:
            level = {INT_BREAK: 2, INT_NMI: 2, INT_EMULATOR: 3}.get(idx, 1)
            self.cpu.raise_int(level, idx)

    # ---------- 外设 tick ----------
    def tick_peripherals(self, cycles):
        self.timer.tick(cycles)
        self.keyboard._irq_assert()  # 每指令热路径：只做中断断言（确保落入 ROM 的 MIE 窗口）

    def _periph_tick(self, used):
        """每帧调度：按键序列 → 键盘释放调度 → 中断断言（定时器已在每指令的
        tick_peripherals 里走，帧末不重复 tick，避免速率翻倍）"""
        self.keyseq.tick()
        self.keyboard.tick()
        self.keyboard._irq_assert()

    # ---------- run ----------
    def run(self, budget_cycles):
        cpu = self.cpu
        if cpu.halted:
            self.keyseq.tick()                     # 先处理按键序列（可能按下新键）
            self.keyboard.tick()                   # 到期释放
            self.check_interrupts()                # 键盘等瞬时唤醒
            if cpu.halted:
                wake = self.timer.cycles_until_raise(budget_cycles)
                self.tick_peripherals(wake)        # 定时器只走到下一次中断
                cpu.cycles += wake                 # 待机只流逝到唤醒点
                self.check_interrupts()
                if cpu.halted:
                    return 0
                budget_cycles -= wake              # 剩余预算：本帧内立即执行唤醒路径
        start = cpu.cycles
        end = start + budget_cycles
        bps = self.breakpoints
        while cpu.cycles < end:
            if bps and ((cpu.csr << 16) | cpu.pc) in bps:
                self.paused = True
                self.logmsg(f"breakpoint @ {cpu.csr:X}:{cpu.pc:04X}")
                break
            cpu.step()
            if cpu.halted:
                # 帧内停机：睡到下一个唤醒事件（定时器中断/键盘）后继续，
                # 避免固件每段 delay 的 STOP 都浪费一整帧（按键处理要 5~6 段 delay）
                wake = self.timer.cycles_until_raise(end - cpu.cycles)
                if wake <= 0:
                    break
                self.tick_peripherals(wake)
                cpu.cycles += wake
                self.check_interrupts()
                if cpu.halted:
                    break
        used = cpu.cycles - start
        self._periph_tick(used)
        return used

    def step(self, n=1):
        for _ in range(n):
            self.cpu.step()

    def enter_standby(self):
        self.cpu.halted = True

    # ---------- snapshot ----------
    def snapshot(self):
        c = self.cpu
        return pickle.dumps({
            "r": bytes(c.r), "cr": bytes(c.cr),
            "pc": c.pc, "csr": c.csr,
            "elr": c.elr[:], "ecsr": c.ecsr[:], "epsw": c.epsw[:],
            "psw": c.psw, "sp": c.sp, "ea": c.ea,
            "dsr": c.dsr, "dsr_last": c.dsr_last,
            "cycles": c.cycles, "halted": c.halted,
            "ram": bytes(self.ram), "vram": bytes(self.lcd.vram),
            "sfr": bytes(self.sfr.shadow),
            "int_mask": self.int_mask, "int_pending": self.int_pending,
        }, 2)

    def restore(self, blob):
        d = pickle.loads(blob)
        c = self.cpu
        c.r[:] = d["r"]
        c.cr[:] = d.get("cr", bytes(16))
        for k in ("pc", "csr", "psw", "sp", "ea", "dsr", "dsr_last",
                  "cycles", "halted"):
            setattr(c, k, d[k])
        c.elr, c.ecsr, c.epsw = d["elr"], d["ecsr"], d["epsw"]
        self.ram[:] = d["ram"]
        self.lcd.vram[:] = d["vram"]
        self.sfr.shadow[:] = d["sfr"]
        self.int_mask = d["int_mask"]
        self.int_pending = d["int_pending"]
