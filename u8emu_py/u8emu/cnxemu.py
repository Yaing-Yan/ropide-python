# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — Cnxemu 简易 API：加载/开关机/内存读写/终端控制台
"""用法:

    from u8emu.cnxemu import Cnxemu

    cnx = Cnxemu().load("rom.bin")          # 加载并立即开始运行（后台线程）
    cnx.control(exit_key="q")               # 终端控制台（纯 ANSI，原地刷新）
    cnx.write(0xE9E0, "11 45 14 19 19 81 00")
    print(cnx.showram(0xD180, 16))
    cnx.press("1")                          # 按一次键（键名/别名/键码）
    cnx.kill()                              # 彻底终结

    control() 只是"开启一个窗口"：退出后模拟器进度保留，再次调用从
    当前状态继续；write() 覆写的字节在 control 期间同样保留。
"""
import curses
import os
import sys
import threading
import time
from dataclasses import replace

from .models import MODELS
from .emulator import Emulator
from .render import render_braille
from .tui import status_text

def _load_emu(romfile, model, cfg=None):
    cfg = cfg or MODELS[model]
    emu = Emulator(cfg, romfile)
    emu.cpu.strict = False
    return emu


class Cnxemu:
    def __init__(self):
        self.emu = None
        self.cfg = None
        self.model = "fx991cnxf"
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self.lcd_rows = 16

    # ---------------- 生命周期 ----------------
    def load(self, romfile, model="fx991cnxf", speed=1.0, freq=None, wait_boot=True):
        """加载 ROM 并立即开始运行（后台线程，约 speed 倍实速）。

        wait_boot=True（默认）：阻塞直到固件完成启动（进入 idle 循环），
        返回后 write()/press() 立即有效；否则 boot 初始化会覆盖早期写入。

        freq：CPU 模拟频率（Hz），默认 None 使用模型默认频率（如 fx991cnxf=2097152）。
        指定后所有外设时序（按键保持、LCD 等）按新频率换算。
        """
        self.model = model
        cfg = MODELS[model]
        if freq is not None:
            cfg = replace(cfg, freq=int(freq))
        self.cfg = cfg
        self.emu = _load_emu(romfile, model, cfg)
        self._speed = max(0.1, speed)
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if wait_boot:
            self._wait_boot()
        return self

    def _wait_boot(self, timeout=10.0):
        """等待固件完成启动（进入 idle 循环 0xF926），超时兜底。"""
        booted = threading.Event()
        emu = self.emu
        if emu is not None:
            emu.cpu.exec_hooks[0xF926] = [lambda c: booted.set()]
            emu.cpu._has_hooks = True
        booted.wait(timeout)
        if emu is not None:
            emu.cpu.exec_hooks.pop(0xF926, None)

    def _run_loop(self):
        frame = max(1, int(self.cfg.freq / 60))
        period = 1 / (60 * self._speed)
        while self._running:
            t0 = time.perf_counter()
            with self._lock:
                if self.emu is None:
                    break
                self.emu.run(frame)
            time.sleep(max(0.0, period - (time.perf_counter() - t0)))

    def kill(self):
        """停止后台运行线程并释放模拟器（彻底终结）。"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        with self._lock:
            if self.emu is not None:
                try:
                    self.emu.keyboard.release_all()
                except Exception:
                    pass
                self.emu = None

    # ---------------- 内存访问 ----------------
    def write(self, off=0xE9E0, byte="11 45 14 19 19 81 00"):
        """向 off 起写字节（十六进制串，空格/逗号分隔）。返回写入字节数。"""
        if self.emu is None:
            raise RuntimeError("未加载 ROM：先调用 load()")
        data = bytes.fromhex(byte.replace(",", " ").replace(" ", ""))
        with self._lock:
            for i, v in enumerate(data):
                self.emu.mmu.poke_raw((off + i) & 0xFFFFF, v)
        return len(data)

    def showram(self, off=0xD180, byte_num=16):
        """读取 off 起 byte_num 字节，返回 "11 45 14 19 19" 格式字符串。"""
        if self.emu is None:
            raise RuntimeError("未加载 ROM：先调用 load()")
        with self._lock:
            return " ".join(f"{self.emu.mmu.peek_raw(off + i):02X}"
                            for i in range(byte_num))

    # ---------------- 按键 ----------------
    _KEY_ALIAS = {
        "SHIFT": "q", "ALPHA": "Q", "MENU": "t", "ON": "POWER",
        "POWER": "POWER", "AC": "C", "DEL": "o", "OPTN": "T",
        "CALC": "r", "UP": "E", "DOWN": "R", "LEFT": "!", "RIGHT": "$",
        "EXE": "=", "=": "=",
    }

    def press(self, key, hold_ms=50):
        """按一次键或一串键（空格分隔，如 "1 + 2 ="、"calc ="、"menu 2 shift menu 1 3"），
        逐个等待固件处理完成后再按下一个，不丢键。返回最后键码。

        key 可以是键名/通俗名（'1'、'p'、'shift'、'AC' 等）或键码 int（0x30）。
        """
        if self.emu is None:
            raise RuntimeError("未加载 ROM：先调用 load()")
        tokens = key.split() if isinstance(key, str) and " " in key.strip() \
            else [key]
        last = None
        for t in tokens:
            if isinstance(t, int):
                code = t & 0xFF
            else:
                name = self._KEY_ALIAS.get(str(t).upper(), t)
                code = self.emu.keyboard.code_of(name)
            with self._lock:
                self.emu.keyseq.key(code, hold_ms=hold_ms, gap_ms=0)
            while self.emu.keyseq.pending:
                time.sleep(0.005)
            last = code
        return last

    # ---------------- 终端控制台（curses 全屏） ----------------
    _CURSES_COLORS = {"black": 0, "red": 1, "green": 2, "yellow": 3,
                      "blue": 4, "magenta": 5, "cyan": 6, "white": 7}

    @staticmethod
    def _style_attrs(style):
        """'bold green' / 'cyan bold' → (curses 颜色, 属性)"""
        color, attrs = 7, 0
        for part in style.split():
            c = Cnxemu._CURSES_COLORS.get(part.lower())
            if c is not None:
                color = c
            elif part.lower() == "bold":
                attrs |= curses.A_BOLD
            elif part.lower() == "underline":
                attrs |= curses.A_UNDERLINE
            elif part.lower() == "reverse":
                attrs |= curses.A_REVERSE
        return color, attrs

    def control(self, exit_key="q", fps=20,
                style_status="bold green", style_screen="white",
                banner=None):
        """终端控制台（curses 全屏，清屏显示 LCD；退出后恢复终端）。

        style_status / style_screen：颜色样式（如 "bold green"、"cyan"）。
        顶部状态栏 + 中间 LCD + 底部按键提示。

        按键：q=退出 p=开机 s=SHIFT a=ALPHA c=AC `=CALC
              方向键=导航 退格=DEL 其余字符按 CWZ.N 映射直接输入

        control() 只是"开启一个窗口"：退出后模拟器进度保留，再次调用
        从当前状态继续；只有 kill() 彻底终结。
        """
        if self.emu is None:
            raise RuntimeError("未加载 ROM：先调用 load()")
        curses.wrapper(self._curses_run, exit_key, fps, banner,
                       style_status, style_screen)

    def _curses_run(self, stdscr, exit_key, fps, banner, st_s, st_sc):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
        fg_s, att_s = self._style_attrs(st_s)
        fg_c, att_c = self._style_attrs(st_sc)
        if curses.has_colors():
            curses.start_color()
            bg = -1
            try:
                curses.use_default_colors()
                curses.init_pair(1, fg_s, -1)      # PyPy 不支持 -1 时回退
            except (ValueError, curses.error):
                bg = curses.COLOR_BLACK
            curses.init_pair(1, fg_s, bg)
            curses.init_pair(2, fg_c, bg)
        interval = 1.0 / max(1, fps)
        try:
            while self._running and self.emu is not None:
                try:
                    ch = stdscr.get_wch()
                except curses.error:
                    ch = None
                if ch in (exit_key, exit_key.upper()):
                    break
                if ch is not None:
                    self._handle_curses_key(ch)
                snap = self._snapshot()
                if snap is not None:
                    self._draw_curses(stdscr, snap, banner,
                                      st_s, st_sc, att_s, att_c)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            with self._lock:
                if self.emu is not None:
                    try:
                        self.emu.keyboard.release_all()
                    except Exception:
                        pass

    def _handle_curses_key(self, ch):
        kb = self.emu.keyboard
        b = self.cfg.bindings
        if isinstance(ch, int):
            name = {curses.KEY_UP: "E", curses.KEY_DOWN: "R",
                    curses.KEY_LEFT: "!", curses.KEY_RIGHT: "$"}.get(ch)
            if name:
                with self._lock:
                    kb.tap_code(kb.code_of(name), hold_ms=50)
                return
            if ch in (curses.KEY_BACKSPACE, 8):
                with self._lock:
                    kb.tap_code(kb.code_of("o"), hold_ms=50)      # DEL
            return
        if ch in ("\x7f", "\b"):
            with self._lock:
                kb.tap_code(kb.code_of("o"), hold_ms=50)
            return
        k = b.get(ch) or b.get(ch.lower())
        if k:
            with self._lock:
                kb.tap_code(kb.code_of(k), hold_ms=50)

    def _draw_curses(self, stdscr, snap, banner, st_s, st_sc, att_s, att_c):
        status, rows, mode, inp, stbytes = snap
        cfg = self.cfg
        lines = render_braille(rows, cfg.lcd_w, cfg.lcd_h, 1, 1, False)
        self.lcd_rows = len(lines)
        h, w = stdscr.getmaxyx()
        w = max(1, w - 1)
        stdscr.erase()
        st = status_text(stbytes) or "·"
        status_line = f"STATUS {st}  mode={mode}  input={inp:02X}"
        try:
            stdscr.addnstr(0, 0, status_line[:w], w,
                           curses.color_pair(1) | att_s)
            for i, ln in enumerate(lines[:h - 3]):
                stdscr.addnstr(1 + i, 0, ln[:w], w, curses.color_pair(2) | att_c)
            hint = (banner if banner else
                    "q退出 p开机 s=SHIFT a=ALPHA c=AC `=CALC "
                    "方向键=导航 退格=DEL 其余字符直接输入")
            stdscr.addnstr(h - 1, 0, hint[:w], w, curses.A_REVERSE)
        except Exception:
            pass
        stdscr.refresh()

    def _snapshot(self):
        """锁内快速快照（渲染输出在锁外，不阻塞后台运行线程）。"""
        with self._lock:
            emu = self.emu
            if emu is None:
                return None
            status, rows = emu.lcd.frame()
            return (status, rows, emu.lcd.mode,
                    emu.mmu.peek_raw(0xD180),
                    bytes(emu.lcd.vram[0:24]))

