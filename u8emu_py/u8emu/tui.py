# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
import curses, time, threading, array
from collections import Counter
from .render import RENDERERS
from .disasm import disasm
from .models import _CNX_NAMES, _CNX_COMMON
from .plugin import EmuAPI, PluginManager, RpcServer, parse_hex

# 状态符号行（fx-991CN X，Screen.cpp sprite_bitmap）: (名称, 字节偏移, 掩码)
_STATUS_SPRITES = [
    ("S", 0x00, 0x01), ("A", 0x01, 0x01), ("M", 0x02, 0x01), ("STO", 0x03, 0x01),
    ("MATH", 0x05, 0x01), ("D", 0x06, 0x01), ("R", 0x07, 0x01), ("G", 0x08, 0x01),
    ("FIX", 0x09, 0x01), ("SCI", 0x0A, 0x01), ("E", 0x0B, 0x01), ("CMPLX", 0x0C, 0x01),
    ("ANGLE", 0x0D, 0x01), ("WDOWN", 0x0F, 0x01), ("LEFT", 0x10, 0x01),
    ("DOWN", 0x11, 0x01), ("UP", 0x12, 0x01), ("RIGHT", 0x13, 0x01),
    ("PAUSE", 0x15, 0x01), ("SUN", 0x16, 0x01),
]


def status_text(vram):
    out = []
    for name, off, mask in _STATUS_SPRITES:
        if off < len(vram) and vram[off] & mask:
            out.append(name)
    return " ".join(out)


class PatchDialog:
    """F4 打开。ADDR 填偏移(hex)，DATA 直接粘贴十六进制串。"""
    HINT = ("Tab/↑↓切换  Enter写入  Esc取消  Ctrl-U清空  "
            "F6冻结  F7裸写  F8读回当前值")

    def __init__(self, tui):
        self.tui = tui
        self.api = tui.api
        self.addr = f"{tui.mem_addr:X}"
        self.data = ""
        self.focus = 1
        self.freeze = False
        self.raw = False
        self.msg = ""

    # ---------- 输入 ----------
    def feed(self, ch, paste=False):
        if ch == "\x1b" and not paste:
            self.tui.dialog = None
            return
        if ch in ("\n", "\r"):
            if paste:                       # 粘贴里的换行 → 分隔符
                if self.focus == 1:
                    self.data += " "
                return
            self.apply()
            return
        if ch == "\t" or ch in (curses.KEY_DOWN, curses.KEY_UP):
            self.focus ^= 1
            return
        if ch in (curses.KEY_BACKSPACE, "\x7f", "\b", 263):
            if self.focus == 0:
                self.addr = self.addr[:-1]
            else:
                self.data = self.data[:-1]
            return
        if ch == "\x15":
            if self.focus == 0:
                self.addr = ""
            else:
                self.data = ""
            return
        if ch == curses.KEY_F6:
            self.freeze = not self.freeze
            return
        if ch == curses.KEY_F7:
            self.raw = not self.raw
            return
        if ch == curses.KEY_F8:
            self.load_current()
            return
        if not isinstance(ch, str) or not ch.isprintable():
            return
        if self.focus == 0:
            if ch in "0123456789abcdefABCDEFxX":
                self.addr += ch
        else:
            self.data += ch

    # ---------- 解析 ----------
    def parsed(self):
        try:
            addr = int(self.addr.lower().replace("0x", "") or "0", 16)
        except ValueError:
            return None, None, "地址非法"
        try:
            data = parse_hex(self.data)
        except ValueError as e:
            return addr, None, str(e)
        return addr, data, ""

    def load_current(self):
        addr, data, err = self.parsed()
        if addr is None:
            self.msg = err
            return
        n = len(data) if data else 16
        self.data = self.api.read_bytes(addr, n).hex(" ")
        self.msg = f"读回 {n} 字节"

    def apply(self):
        addr, data, err = self.parsed()
        if err or data is None:
            self.msg = err or "数据为空"
            return
        if not data:
            self.msg = "数据为空"
            return
        try:
            with self.tui.lock:
                n = self.api.patch(addr, data, freeze=self.freeze, raw=self.raw)
        except Exception as e:
            self.msg = f"失败: {e}"
            return
        self.tui.mem_addr = addr
        self.tui.emu.logmsg(f"[patch] {addr:05X} <- {data.hex(' ')[:60]}"
                            + ("…" if len(data) > 20 else ""))
        self.tui.dialog = None

    # ---------- 绘制 ----------
    def draw(self, stdscr, h, w):
        bw = min(78, max(46, w - 4)); bh = 13
        y0 = max(0, (h - bh) // 2); x0 = max(0, (w - bw) // 2)
        blank = " " * bw
        for i in range(bh):
            stdscr.addnstr(y0 + i, x0, blank, bw)

        def put(row, s, attr=0):
            stdscr.addnstr(y0 + row, x0 + 1, s, bw - 2, attr)

        stdscr.addnstr(y0, x0, "┌─ RAM PATCH (F4) " + "─" * bw, bw, curses.A_BOLD)
        stdscr.addnstr(y0 + bh - 1, x0, "└" + "─" * (bw - 2), bw)

        addr, data, err = self.parsed()
        fw = bw - 12
        for i, (label, val) in enumerate((("ADDR", self.addr), ("DATA", self.data))):
            sel = (self.focus == i)
            shown = val[-fw:] if len(val) > fw else val
            put(2 + i * 2, f"{label} 0x" if i == 0 else f"{label}   ", curses.A_DIM)
            stdscr.addnstr(y0 + 2 + i * 2, x0 + 8,
                           (shown + "▏").ljust(fw), fw,
                           curses.A_REVERSE if sel else curses.A_UNDERLINE)

        reg = self.api.region_of(addr) if addr is not None else None
        if err:
            put(6, "✗ " + err, curses.color_pair(5) if curses.has_colors() else 0)
        elif data:
            put(6, f"→ {addr:05X}..{addr+len(data)-1:05X}  {len(data)} 字节  "
                   f"region={reg or '<UNMAPPED>'}"
                   + ("  ⚠只读" if reg and not self._writable(addr) else ""))
            old = self.api.read_bytes(addr, min(len(data), 16)).hex(" ")
            put(7, f"old: {old}" + ("…" if len(data) > 16 else ""))
            put(8, f"new: {data[:16].hex(' ')}" + ("…" if len(data) > 16 else ""))
        else:
            put(6, f"→ {addr:05X}  region={reg or '<UNMAPPED>'}  (粘贴十六进制串)")

        put(10, f"[{'x' if self.freeze else ' '}] F6 写后冻结   "
                f"[{'x' if self.raw else ' '}] F7 裸写(绕过 MMIO/监视)")
        put(11, self.msg or self.HINT, curses.A_DIM)
        stdscr.refresh()

    def _writable(self, addr):
        r = self.tui.emu.mmu.region_at(addr)
        return bool(r and (r.writable or r.writer))


class TUI:
    def __init__(self, emu, args):
        self.emu = emu
        self.args = args
        self.style = args.style
        self.hscale, self.vscale = args.hscale, args.vscale
        self.invert = args.invert
        self.fps = args.fps
        self.cycles_per_frame = max(1, int(emu.cfg.freq / self.fps * args.speed))
        self.lock = threading.RLock()
        self.api = EmuAPI(emu, self)
        self.pm = PluginManager(self.api)
        self.cmdline = ""
        self.mode = "run"          # run | cmd
        self.right_tab = 0
        self.mem_addr = emu.cfg.ram[0]
        self.keys_scroll = 0            # KEYS 面板键码表滚动行
        self.hold_ms = int(args.hold * 1000)
        self.gap_ms = int(getattr(args, "gap", 0.2) * 1000)
        self.hold_wall = (args.hold_unit == "wall")
        emu.keyseq.default_hold_ms = self.hold_ms
        emu.keyseq.default_gap_ms = self.gap_ms
        self.dialog = None
        self.quit = False
        if args.keylog:
            emu.keyboard.keylog(True)
        self.status = "F1 暂停 F2 单步 F4 补丁 F5 复位 : 命令 q 退出"
        self.real_speed = 0.0

    # ---------- 按键 ----------
    def tap(self, key, hold_ms=None):
        """终端按键 / 插件 / :key 的统一入口 —— 一律走队列，快速连打不会互相踩。"""
        try:
            code = self.emu.keyboard.code_of(key) if isinstance(key, str) else int(key)
        except KeyError as e:
            self.emu.logmsg(str(e))
            return
        self.emu.keyseq.key(code, hold_ms or self.hold_ms, self.gap_ms)

    # ---------- 主循环 ----------
    @staticmethod
    def _default_bg_ok(stdscr):
        """探测 init_pair 是否支持 -1（终端默认背景色）。PyPy 的 curses 会拒绝负数。"""
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_BLACK, -1)
            return True
        except (ValueError, curses.error):
            return False

    def run(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        if curses.has_colors():
            curses.start_color()
            colors = [0, curses.COLOR_GREEN, curses.COLOR_CYAN,
                      curses.COLOR_YELLOW, curses.COLOR_MAGENTA, curses.COLOR_RED]
            bg = -1 if self._default_bg_ok(curses) else curses.COLOR_BLACK
            for i in range(1, 6):
                curses.init_pair(i, colors[i], bg)
        target = 1.0 / self.fps
        while True:
            t0 = time.perf_counter()
            if not self._input(stdscr):
                break
            with self.lock:
                if not self.emu.paused:
                    used = self.emu.run(self.cycles_per_frame)
                    self.real_speed = used * self.fps
                self.api._tick_frame()
            self._draw(stdscr)
            dt = time.perf_counter() - t0
            if dt < target:
                time.sleep(target - dt)
        return

    # ---------- 输入 ----------
    def _input(self, stdscr):
        batch = []
        while len(batch) < 8192:
            try:
                batch.append(stdscr.get_wch())
            except curses.error:
                break
        if not batch:
            return not self.quit
        paste = len(batch) > 8                      # 粘贴突发：换行当分隔符，不触发回车
        for ch in batch:
            if self.dialog is not None:
                self.dialog.feed(ch, paste)
                continue
            if self.mode == "cmd":
                self._feed_cmd(ch)
                continue
            self._feed_run(ch)
        return not self.quit

    def _feed_cmd(self, ch):
        if ch in ("\n", "\r"):
            line, self.cmdline, self.mode = self.cmdline, "", "run"
            self._exec_cmd(line)
        elif ch == "\x1b":
            self.cmdline, self.mode = "", "run"
        elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b", 263):
            self.cmdline = self.cmdline[:-1]
        elif ch == "\x15":                          # Ctrl-U
            self.cmdline = ""
        elif isinstance(ch, str) and ch.isprintable():
            self.cmdline += ch

    def _feed_run(self, ch):
        if ch == curses.KEY_F1:
            self.emu.paused = not self.emu.paused
        elif ch == curses.KEY_F2:
            with self.lock: self.emu.step(1)
        elif ch == curses.KEY_F3:
            with self.lock: self.emu.step(100)
        elif ch == curses.KEY_F4:
            self.dialog = PatchDialog(self)          # ★ RAM 覆写面板
        elif ch == curses.KEY_F5:
            with self.lock: self.emu.reset()
        elif ch in (curses.KEY_PPAGE, "["):          # MEM 面板上翻一屏（无 PgUp 键用 [）
            self.mem_addr = max(0, self.mem_addr - self._mem_page())
        elif ch in (curses.KEY_NPAGE, "]"):          # MEM 面板下翻一屏（无 PgDn 键用 ]）
            self.mem_addr = min(0xFFFFF, self.mem_addr + self._mem_page())
        elif ch in ("j", "k"):
            tab = self._right_tab_name()
            if tab == "MEM":
                # vim 风格翻页：j 下翻 / k 上翻（仅 MEM 面板，避免误触计算器键）
                if ch == "j":
                    self.mem_addr = min(0xFFFFF, self.mem_addr + self._mem_page())
                else:
                    self.mem_addr = max(0, self.mem_addr - self._mem_page())
            elif tab == "KEYS":
                step = max(1, self._keys_per)
                if ch == "j":
                    self.keys_scroll += step
                else:
                    self.keys_scroll = max(0, self.keys_scroll - step)
        elif ch in (curses.KEY_BACKSPACE, "\x7f", "\b", 263, 8):
            self.tap("o")                    # DEL = 退格键
        elif ch in (curses.KEY_UP, curses.KEY_DOWN,
                    curses.KEY_LEFT, curses.KEY_RIGHT):
            self.tap({curses.KEY_UP: "E", curses.KEY_DOWN: "R",
                      curses.KEY_LEFT: "!", curses.KEY_RIGHT: "$"}[ch])
        elif ch == "\t":
            self.right_tab = (self.right_tab + 1) % (5 + len(self.api._panels))
        elif ch == ":":
            self.mode, self.cmdline = "cmd", ""
        elif ch == "\x18":                           # Ctrl-X 清空按键队列
            n = self.emu.keyseq.clear()
            self.emu.logmsg(f"key queue cleared ({n})")
        elif ch in ("q", "Q") and self.args.qquit and not self.emu.cfg.bindings.get(ch):
            self.quit = True
        elif isinstance(ch, str):
            # 大小写不敏感：精确匹配优先，未命中回退小写（S/s 都触发 SHIFT 等）
            k = self.emu.cfg.bindings.get(ch) or self.emu.cfg.bindings.get(ch.lower())
            if k:
                self.tap(k)

    def _mem_page(self):
        return max(1, getattr(self, "mem_per", 8)) * 16

    def _right_tab_name(self):
        tabs = ["REGS", "MEM", "FROZEN", "KEYS", "SCREEN"] + list(self.api._panels.keys())
        return tabs[self.right_tab % len(tabs)]

    # ---------- 命令 ----------
    def _exec_cmd(self, line):
        parts = line.split()
        if not parts:
            return
        cmd, a = parts[0], parts[1:]
        L = self.emu.logmsg
        try:
            if cmd in ("q", "quit"):
                raise SystemExit
            elif cmd == "r":                       # :r 8000 [len]
                addr = int(a[0], 16); n = int(a[1]) if len(a) > 1 else 16
                L(f"{addr:05X}: " + " ".join(f"{b:02X}" for b in self.api.read_bytes(addr, n)))
            elif cmd == "w":                       # :w 8000 12 34 ..
                addr = int(a[0], 16)
                self.api.write_bytes(addr, bytes(int(x, 16) for x in a[1:]))
                L(f"wrote {len(a)-1} bytes @ {addr:05X}")
            elif cmd == "freeze":                  # :freeze 8123 FF [size]
                self.api.freeze(int(a[0], 16), int(a[1], 16), int(a[2]) if len(a) > 2 else 1)
                L(f"frozen {a[0]}={a[1]}")
            elif cmd == "unfreeze":
                self.api.unfreeze(int(a[0], 16)); L("unfrozen")
            elif cmd == "bp":
                self.api.add_breakpoint(int(a[0], 16), int(a[1], 16)); L("bp set")
            elif cmd == "goto":
                self.mem_addr = int(a[0], 16)
            elif cmd == "page":            # :page +100 / :page -10 / :page 0xE9E0
                if not a:
                    d = self._mem_page()
                elif a[0][0] in "+-":
                    d = int(a[0], 16)      # 相对偏移
                else:
                    self.mem_addr = int(a[0], 16) & 0xFFFFF   # 绝对地址
                    L(f"mem view @ {self.mem_addr:05X}")
                    return
                self.mem_addr = max(0, min(0xFFFFF, self.mem_addr + d))
                L(f"mem view @ {self.mem_addr:05X}")
            elif cmd == "reg":
                self.api.set_reg(a[0], int(a[1], 16)); L("reg set")
            elif cmd == "plugin":
                self.pm.load_file(a[0])
            elif cmd == "save":
                open(a[0], "wb").write(self.api.snapshot()); L("snapshot saved")
            elif cmd == "load":
                self.api.restore(open(a[0], "rb").read()); L("snapshot loaded")
            elif cmd == "speed":
                self.cycles_per_frame = int(self.emu.cfg.freq / self.fps * float(a[0]))
            elif cmd == "style":
                self.style = a[0]
            elif cmd == "vscale":
                self.vscale = int(a[0])
            elif cmd == "key":            # :key 1 [秒]  全自动点按（入队）
                kb = self.emu.keyboard
                code = kb.code_of(a[0])
                hold = int(float(a[1]) * 1000) if len(a) > 1 else self.hold_ms
                self.emu.keyseq.submit(self._parse_key_tokens([a[0]]))
                if len(a) > 1:              # 覆盖本次 hold
                    it = self.emu.keyseq.q[-1]
                    self.emu.keyseq.q[-1] = (it[0], it[1], hold, it[3])
                L(f"key {a[0]} queued (code 0x{code:02X}, hold {hold}ms emu)")
            elif cmd in ("optn", "keys", "seq", "type"):
                if a and a[0] == "-t":      # :optn -t 1+2=   按字符走终端绑定
                    names = [self.emu.cfg.bindings[c] for c in "".join(a[1:])
                             if c in self.emu.cfg.bindings]
                    items = self._parse_key_tokens(names)
                else:
                    items = self._parse_key_tokens(a)
                self.emu.keyseq.submit(items)
                L(f"queued {len(items)} step(s); pending={self.emu.keyseq.pending}")
            elif cmd in ("kq", "keyq"):
                L("queue: " + (" ".join(self.emu.keyseq.peek(20)) or "<empty>"))
            elif cmd in ("kclear", "kc"):
                L(f"cleared {self.emu.keyseq.clear()}")
            elif cmd == "tap":            # :tap 1 [ms]  一次性点按
                self.tap(a[0], int(a[1]) if len(a) > 1 else 0)
                L(f"tap {a[0]} hold={self.hold_ms}ms")
            elif cmd == "keyup":          # 兜底：:keyup all 恐慌释放
                kb = self.emu.keyboard
                if not a or a[0] == "all":
                    self.emu.keyseq.clear(); kb.release_all(); L("all released")
                else:
                    kb.release_code(kb.code_of(a[0])); L(f"{a[0]} released")
            elif cmd == "khold":          # 高级：手动按住（组合键调试）
                kb = self.emu.keyboard
                kb.press_code(kb.code_of(a[0])); L(f"{a[0]} HELD (use :keyup)")
            elif cmd == "keylog":         # :keylog on|off
                on = (not a) or a[0] not in ("off", "0", "false")
                self.emu.keyboard.keylog(on); L(f"keylog {'on' if on else 'off'}")
            elif cmd == "keycode":        # :keycode 1 | :keycode 0x30
                kb = self.emu.keyboard
                try:
                    L(f"{a[0]} -> 0x{kb.code_of(a[0]):02X}")
                except KeyError:
                    c = int(a[0], 16)
                    L(f"0x{c:02X} -> {kb.name_of(c)}")
            elif cmd == "hold":           # :hold 2.5  运行时改保持时长(秒)
                self.hold_ms = int(float(a[0]) * 1000)
                self.emu.keyseq.default_hold_ms = self.hold_ms
                L(f"hold={self.hold_ms}ms")
            elif cmd == "gap":            # :gap 0.1  连击间隔(秒)
                self.gap_ms = int(float(a[0]) * 1000)
                self.emu.keyseq.default_gap_ms = self.gap_ms
                L(f"gap={self.gap_ms}ms")
            elif cmd == "patch":          # :patch            → 打开面板
                if not a:                  # :patch D180 12 34 → 直接写
                    self.dialog = PatchDialog(self)
                    return
                n = self.api.patch(int(a[0], 16), " ".join(a[1:]))
                L(f"patched {n} bytes @ {a[0]}")
            elif cmd == "unpatch":
                L(f"restored {self.api.unpatch()} bytes")
            elif cmd == "prof":                    # :prof on|off|clear
                m = self.emu.mmu
                if a and a[0] == "off":
                    m.profile = None; L("profile off")
                elif a and a[0] == "clear":
                    m.profile = array.array("I", [0]) * (1 << 14); L("profile cleared")
                else:
                    m.profile = array.array("I", [0]) * (1 << 14); L("profile on")
            elif cmd == "vramtop":                 # :vramtop [n]
                m = self.emu.mmu
                if m.profile is None:
                    L("run :prof on first"); return
                n = int(a[0]) if a else 10
                hits = sorted(((c, i) for i, c in enumerate(m.profile) if c),
                              reverse=True)
                merged = []
                for c, i in hits:
                    if merged and merged[-1][1] + merged[-1][2] == i:
                        merged[-1][0] += c; merged[-1][2] += 1
                    else:
                        merged.append([c, i, 1])
                for c, i, ln in merged[:n]:
                    reg = m.region_at(i << 6)
                    L(f"{i<<6:05X}-{((i+ln)<<6)-1:05X} writes={c:<9} "
                      f"{reg.name if reg else '<UNMAPPED>'}")
            elif cmd == "lcd":                     # :lcd base=F800 w=192 h=63 stride=32 layout=row_msb
                kw = dict(x.split("=") for x in a)
                l = self.emu.lcd
                def gi(k, cur, base=10):
                    return int(kw[k], base) if k in kw else cur
                l.configure(gi("base", l.base, 16), gi("w", l.w), gi("h", l.h),
                            gi("stride", l.stride),
                            gi("skip", l.row_skip), gi("disp", l.disp_bytes),
                            kw.get("layout", l.layout))
                L(f"LCD -> {l.base:05X} {l.w}x{l.h} stride={l.stride} "
                  f"skip={l.row_skip} disp={l.disp_bytes} {l.layout}")
            elif cmd == "unmapped":                # 看空洞读写
                m = self.emu.mmu
                m.trace_unmapped = not m.trace_unmapped
                if not m.trace_unmapped:
                    cnt = Counter((k, a0 >> 8) for k, a0 in m.unmapped_log)
                    for (k, p), c in cnt.most_common(10):
                        L(f"{k} {p<<8:05X}xx  x{c}")
                    m.unmapped_log.clear()
                    L("unmapped trace off")
                else:
                    L("unmapped trace on")
            elif cmd in self.api.commands:
                self.api.commands[cmd][0](*a)
            else:
                L(f"unknown command: {cmd}")
        except SystemExit:
            raise
        except Exception as e:
            L(f"cmd error: {e}")

    # ---------- 键序列 token 解析 ----------
    def _parse_key_tokens(self, toks):
        """token: 名称 | #7F/0x7F 键码 | name*3 重复 | w500 等待ms
                  | hold:q 按住 | up:q 释放"""
        kb = self.emu.keyboard
        items = []
        for t in toks:
            if len(t) > 1 and t[0] == "w" and t[1:].isdigit():
                items.append(("wait", None, int(t[1:]), 0)); continue
            if t.startswith("hold:"):
                items.append(("hold", kb.code_of(t[5:]), 0, 0)); continue
            if t.startswith("up:"):
                items.append(("up", kb.code_of(t[3:]), 0, 0)); continue
            rep = 1
            if "*" in t[1:]:
                t, r = t.rsplit("*", 1)
                rep = max(1, int(r))
            if t.startswith("#"):
                code = int(t[1:], 16)
            elif t[:2].lower() == "0x":
                code = int(t, 16)
            else:
                try:
                    code = kb.code_of(t)         # 键名（CWZ.N 字符）
                except KeyError:
                    name = _CNX_COMMON.get(t.lower())
                    if name is None:
                        raise KeyError(f"unknown key: {t!r}")
                    code = kb.code_of(name)      # 通俗名（menu/sin/ac...）
            items += [("key", code, self.hold_ms, self.gap_ms)] * rep
        return items

    # ---------- 绘制 ----------
    def _draw(self, stdscr):
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        lcd = self.emu.lcd
        # LCD 优先：先保证 96 字符（192/2）完整显示，剩余宽度才给右栏；
        # 终端太窄时右栏压缩（REGS 面板自适应列数），而不是截断 LCD。
        lcd_chars = (lcd.w + 2 * self.hscale - 1) // (2 * self.hscale)
        right_w = max(0, min(46, w - lcd_chars - 2 - 1))
        left_w = w - right_w - 1
        status, frame = lcd.frame()
        lines = RENDERERS[self.style](frame, lcd.w, lcd.h,
                                      self.hscale, self.vscale, self.invert)
        top = 0
        stdscr.addnstr(0, 0, f"┌ LCD {lcd.w}x{lcd.h} mode={lcd.mode} "
                             f"[{self.style} {self.hscale}x{self.vscale}] "
                             + "─" * left_w, left_w, curses.A_BOLD)
        # 状态符号行（文本）
        st = status_text(lcd.vram) or "·"
        stdscr.addnstr(1, 1, "STATUS " + st, left_w - 2, curses.A_BOLD)
        for i, ln in enumerate(lines):
            if 2 + i >= h - 2: break
            stdscr.addnstr(2 + i, 1, ln, left_w - 1, curses.color_pair(2))
        top = 2 + len(lines)
        if top > h - 11:                    # 终端太小：压缩 LCD 区，防止 DISASM/LOG 越界崩溃
            top = max(0, h - 11)

        # -- 反汇编 --
        c = self.emu.cpu
        stdscr.addnstr(top, 0, "├ DISASM " + "─" * left_w, left_w)
        for i, (a, raw, txt) in enumerate(disasm(c, c.csr, c.pc, 8)):
            y = top + 1 + i
            if y >= h - 6: break
            mark = ">" if i == 0 else " "
            stdscr.addnstr(y, 1, f"{mark}{c.csr:X}:{a:04X} {raw:04X}  {txt}",
                           left_w - 2, curses.A_REVERSE if i == 0 else 0)
        top += 9

        # -- 日志 --
        stdscr.addnstr(top, 0, "├ LOG " + "─" * left_w, left_w)
        logs = self.emu.log[-(h - top - 3):]
        for i, ln in enumerate(logs):
            y = top + 1 + i
            if y >= h - 1: break
            stdscr.addnstr(y, 1, ln, left_w - 2)

        # -- 右栏 --
        self._draw_right(stdscr, h, w, left_w + 1, right_w)

        # -- 状态栏 --
        held = self.emu.keyboard.held_names()
        q = self.emu.keyseq.pending
        st = (f"{'PAUSE' if self.emu.paused else 'RUN  '} "
              f"{self.real_speed/1e6:5.2f}MHz  cyc={c.cycles} "
              f"KEY[{','.join(held) if held else '-'}]"
              f"{f' Q:{q}' if q else ''}  {self.status}")
        stdscr.addnstr(h - 1, 0, (":" + self.cmdline) if self.mode == "cmd" else st,
                       w - 1, curses.A_REVERSE)
        if self.dialog is not None:
            self.dialog.draw(stdscr, h, w)
        stdscr.refresh()

    def _draw_right(self, stdscr, h, w, x, rw):
        if x >= w or rw <= 0:
            return                     # 终端太窄，右栏无空间
        c = self.emu.cpu
        tabs = ["REGS", "MEM", "FROZEN", "KEYS", "SCREEN"] + list(self.api._panels.keys())
        t = tabs[self.right_tab % len(tabs)]
        stdscr.addnstr(0, x, f"┤ {t} (Tab切换) " + "─" * rw, rw, curses.A_BOLD)
        y = 1
        def put(s):
            nonlocal y
            if y < h - 1 and x + 1 < w and rw - 2 > 0:
                stdscr.addnstr(y, x + 1, s, rw - 2)
                y += 1
        if t == "REGS":
            for i in range(0, 16, 4):
                put(" ".join(f"R{j:<2}={c.r[j]:02X}" for j in range(i, i + 4)))
            put("")
            for i in range(0, 16, 2):
                put(f"ER{i:<2}={c.get_er(i):04X}   " +
                    (f"ER{i+2:<2}={c.get_er(i+2):04X}" if i + 2 < 16 else ""))
            put("")
            put(f"PC ={c.csr:X}:{c.pc:04X}  SP={c.sp:04X}")
            put(f"LR ={c.lcsr:X}:{c.lr:04X}  EA={c.ea:04X}")
            put(f"DSR={c.dsr:02X} PSW={c.psw:02X} "
                f"[{'C' if c.psw&0x80 else '-'}{'Z' if c.psw&0x40 else '-'}"
                f"{'S' if c.psw&0x20 else '-'}{'V' if c.psw&0x10 else '-'}"
                f"{'I' if c.psw&0x08 else '-'}{'H' if c.psw&0x04 else '-'}"
                f"] EL={c.psw&3}")
            put(f"halted={c.halted} intm={self.emu.int_mask:04X} "
                f"intp={self.emu.int_pending:04X}")
        elif t == "MEM":
            per = max(4, (rw - 10) // 3)
            self.mem_per = per
            a = self.mem_addr
            put(f"j/k [ ] 翻页  :page ±n / 0xADDR")
            while y < h - 1:
                row = self.api.read_bytes(a, per)
                put(f"{a:05X} " + " ".join(f"{b:02X}" for b in row))
                a += per
        elif t == "FROZEN":
            fr = self.api.frozen_list()
            put(f"{len(fr)} frozen cells")
            for a, v in list(fr.items())[:h - 3]:
                put(f"{a:05X} = {v:02X}")
        elif t == "SCREEN":
            l = self.emu.lcd
            put(f"base={l.base:05X} {l.w}x{l.h} st={l.stride}")
            put(f"skip={l.row_skip} disp={l.disp_bytes} en={l.mode}")
            put(f"nonzero bytes = {l.nonzero()}/{l.size}")
            for r in range(min(6, l.h)):
                b = (r + l.row_skip) * l.stride
                put(l.vram[b:b + min(8, l.disp_bytes)].hex(" "))
        elif t == "KEYS":
            kb, sq = self.emu.keyboard, self.emu.keyseq
            put(f"hold={self.hold_ms}ms gap={self.gap_ms}ms "
                f"({'wall' if self.hold_wall else 'emu'})")
            put(f"KO=0x{kb.ko:03X} mask=0x{kb.ko_mask:03X} "
                f"log={'ON' if kb.log_enabled else 'off'}")
            put(f"HELD: {', '.join(kb.held_names()) or '-'}")
            put(f"QUEUE({sq.pending}): {' '.join(sq.peek(10)) or '-'}   [Ctrl-X 清空]")
            put("-- 键码表  j/k 滚动 --")
            keys = sorted((((ko & 0xF) << 4) | (ki & 0x7), name)
                          for name, (ko, ki) in self.emu.cfg.keys.items()
                          if name != self.emu.cfg.power_key)
            per = max(1, (rw - 2) // 11)
            self._keys_per = per
            put(f"{'码':>4} {'ASCII':<6}{'键':<5}")
            put("─" * (rw - 2))
            for i in range(self.keys_scroll, len(keys), per):
                if y >= h - 1:
                    break
                row = " ".join(
                    f"{c:02X}  {n:<4}{_CNX_NAMES.get(n, n)[:4]}"
                    for c, n in keys[i:i + per])
                put(row)
        else:
            for ln in self.api._panels[t](rw - 2, h - 2):
                put(ln)


def start(emu, args):
    tui = TUI(emu, args)
    tui.pm.load_dir(args.plugin_dir)
    for p in args.plugin:
        tui.pm.load_file(p)
    if args.rpc:
        RpcServer(tui.api, port=args.rpc, lock=tui.lock).start()
        emu.logmsg(f"RPC listening on 127.0.0.1:{args.rpc}")
    curses.wrapper(tui.run)
