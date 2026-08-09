# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""插件 API。插件 = 一个 .py，暴露 register(api)。
   也可通过 --rpc PORT 用 JSON 行协议远程调用同一套 API（对标原仓库 McpPlugin）。
"""
from __future__ import annotations
import importlib.util, json, os, socket, threading, traceback


def parse_hex(text):
    """宽松十六进制解析：'12 34' / '1234' / '0x12,0x34' / 'D180: 12 34 |..|' / 多行"""
    out = bytearray()
    for line in str(text).replace("\r", "\n").split("\n"):
        if "|" in line:
            line = line.split("|", 1)[0]
        for tok in line.replace(",", " ").replace(";", " ").split():
            if tok.endswith(":"):                       # 地址前缀
                continue
            t = tok[2:] if tok[:2].lower() == "0x" else tok
            t = t.replace("_", "").replace("-", "")
            if not t:
                continue
            if any(c not in "0123456789abcdefABCDEF" for c in t):
                raise ValueError(f"非法十六进制: {tok!r}")
            if len(t) & 1:
                raise ValueError(f"半个字节: {tok!r}（需偶数位）")
            out += bytes.fromhex(t)
    return bytes(out)


class EmuAPI:
    VERSION = 1

    def __init__(self, emu, tui=None):
        self.emu = emu
        self.cpu = emu.cpu
        self.mmu = emu.mmu
        self.tui = tui
        self._frozen = {}         # addr -> value
        self._frame_cbs = []
        self._panels = {}
        self.commands = {}        # name -> (fn, help)

    # ---------------- 内存 ----------------
    def read8(self, addr):            return self.mmu.peek_raw(addr)
    def read16(self, addr):           return self.mmu.peek_raw(addr) | (self.mmu.peek_raw(addr + 1) << 8)
    def read_bytes(self, addr, n):    return bytes(self.mmu.peek_raw(addr + i) for i in range(n))
    def write8(self, addr, v):        self.mmu.write8(addr, v)
    def write16(self, addr, v):       self.mmu.write16(addr, v)
    def write_bytes(self, addr, data):
        for i, b in enumerate(data):
            self.mmu.write8(addr + i, b)
    def poke(self, addr, v):          self.mmu.poke_raw(addr, v)   # 绕过 watch

    # -------------- 即时覆写(freeze) --------------
    def freeze(self, addr, value, size=1):
        """把某地址锁死为固定值：写入会被立刻改回，并且每帧兜底刷新。"""
        for i in range(size):
            a = addr + i
            v = (value >> (8 * i)) & 0xFF
            self._frozen[a] = v
            self.mmu.poke_raw(a, v)
            self.mmu.add_watch(a, self._freeze_cb, on_write=True)

    def _freeze_cb(self, addr, value):
        want = self._frozen.get(addr)
        if want is not None and value != want:
            self.mmu.poke_raw(addr, want)

    def unfreeze(self, addr, size=1):
        for i in range(size):
            a = addr + i
            self._frozen.pop(a, None)
            self.mmu.del_watch(a, self._freeze_cb, on_write=True)

    def frozen_list(self):
        return dict(self._frozen)

    # ---------------- 监视 / Hook ----------------
    def on_write(self, addr, cb):  self.mmu.add_watch(addr, cb, True)
    def on_read(self, addr, cb):   self.mmu.add_watch(addr, cb, False)
    def on_exec(self, seg, off, cb):
        self.cpu.exec_hooks.setdefault((seg << 16) | off, []).append(cb)
        self.cpu._has_hooks = True
    def on_frame(self, cb):        self._frame_cbs.append(cb)
    def on_reset(self, cb):        self.emu.reset_hooks.append(cb)
    def on_break(self, cb):        self.emu.brk_hooks.append(cb)

    # ---------------- 寄存器 ----------------
    def get_reg(self, name):
        n = name.lower(); c = self.cpu
        if n.startswith("er"): return c.get_er(int(n[2:]))
        if n.startswith("xr"): return c.get_xr(int(n[2:]))
        if n.startswith("r"):  return c.r[int(n[1:])]
        return getattr(c, n)

    def set_reg(self, name, v):
        n = name.lower(); c = self.cpu
        if n.startswith("er"): c.set_er(int(n[2:]), v)
        elif n.startswith("xr"): c.set_xr(int(n[2:]), v)
        elif n.startswith("r"): c.r[int(n[1:])] = v & 0xFF
        else: setattr(c, n, v)

    def regs(self):
        c = self.cpu
        d = {f"r{i}": c.r[i] for i in range(16)}
        d.update(pc=c.pc, csr=c.csr, sp=c.sp, psw=c.psw, lr=c.lr,
                 ea=c.ea, dsr=c.dsr, cycles=c.cycles)
        return d

    # ---------------- 按键 / 屏幕 ----------------
    KEY_HOLD_MS = 1500                   # tap 默认保持（模拟时间）

    def code_of(self, name):  return self.emu.keyboard.code_of(name)
    def name_of(self, code):  return self.emu.keyboard.name_of(code)
    def keys_held(self):      return self.emu.keyboard.held_names()
    def keys_held_codes(self):return self.emu.keyboard.held_codes()
    def keylog(self, on=True):return self.emu.keyboard.keylog(on)
    def key_events(self, n=20):
        return list(self.emu.keyboard.events)[-n:]

    # --- 键码接口 ---
    def press_code(self, code, hold_ms=None, wall=False):
        return self.emu.keyboard.press_code(int(code), hold_ms, wall)
    def release_code(self, code):
        return self.emu.keyboard.release_code(int(code))
    def tap_code(self, code, hold_ms=None, wall=False):
        return self.emu.keyboard.tap_code(
            int(code), self.KEY_HOLD_MS if hold_ms is None else hold_ms, wall)

    # --- 名称接口（兼容） ---
    def press(self, key, hold_ms=None):
        return self.emu.keyboard.press_code(self.code_of(key), hold_ms)
    def release(self, key):
        return self.emu.keyboard.release_code(self.code_of(key))
    def release_all(self):
        self.emu.keyboard.release_all()
    def tap(self, key, hold_ms=None):
        """注意：旧版第二参数是"帧数"，现在是毫秒(模拟时间)。"""
        return self.tap_code(self.code_of(key), hold_ms)

    def type_keys(self, names, hold_ms=None, gap_ms=None):
        """排队顺序敲一串键（由 KeySequencer 驱动，非阻塞）"""
        return self.key_seq(names, hold_ms, gap_ms)

    # ---------------- 按键序列 ----------------
    def key_seq(self, names, hold_ms=None, gap_ms=None):
        kb = self.emu.keyboard
        for n in names:
            self.emu.keyseq.key(kb.code_of(n) if isinstance(n, str) else int(n),
                                hold_ms, gap_ms)
        return self.emu.keyseq.pending

    def key_seq_codes(self, codes, hold_ms=None, gap_ms=None):
        for c in codes:
            self.emu.keyseq.key(int(c), hold_ms, gap_ms)
        return self.emu.keyseq.pending

    def key_queue(self):     return self.emu.keyseq.peek(16)
    def key_queue_len(self): return self.emu.keyseq.pending
    def key_clear(self):     return self.emu.keyseq.clear()
    def key_busy(self):      return self.emu.keyseq.busy

    # ---------------- RAM 覆写 ----------------
    def patch(self, addr, data, freeze=False, raw=False):
        """data 可为 bytes 或宽松 hex 字符串。返回写入字节数。"""
        if isinstance(data, str):
            data = parse_hex(data)
        elif isinstance(data, (list, tuple)):
            data = bytes(data)
        addr = int(addr) & 0xFFFFF
        before = bytes(self.mmu.peek_raw(addr + i) for i in range(len(data)))
        for i, b in enumerate(data):
            if raw:
                self.mmu.poke_raw(addr + i, b)
            else:
                self.mmu.write8(addr + i, b)
        self.emu.patch_undo.append((addr, before))
        del self.emu.patch_undo[:-64]
        if freeze:
            for i, b in enumerate(data):
                self.freeze(addr + i, b)
        self.log(f"patch {addr:05X} <- {len(data)}B"
                 + (" +freeze" if freeze else "") + (" raw" if raw else ""))
        return len(data)

    def unpatch(self):
        if not self.emu.patch_undo:
            return 0
        addr, before = self.emu.patch_undo.pop()
        for i, b in enumerate(before):
            self.unfreeze(addr + i)
            self.mmu.poke_raw(addr + i, b)
        self.log(f"unpatch {addr:05X} restored {len(before)}B")
        return len(before)

    def region_of(self, addr):
        r = self.mmu.region_at(addr)
        return r.name if r else None

    def screen_bytes(self):  return bytes(self.emu.lcd.vram)
    def screen_bitmap(self):
        return self.emu.lcd.frame()[1]
    def screen_status(self):
        from .tui import status_text
        return status_text(self.emu.lcd.vram)
    def screen_text(self):
        from .render import render_braille
        st, f = self.emu.lcd.frame()
        return render_braille(f, self.emu.lcd.w, self.emu.lcd.h)

    # ---------------- 控制 ----------------
    def pause(self):  self.emu.paused = True
    def resume(self): self.emu.paused = False
    def step(self, n=1): self.emu.step(n)
    def reset(self):  self.emu.reset()
    def add_breakpoint(self, seg, off): self.emu.breakpoints.add((seg << 16) | off)
    def del_breakpoint(self, seg, off): self.emu.breakpoints.discard((seg << 16) | off)
    def snapshot(self): return self.emu.snapshot()
    def restore(self, blob): self.emu.restore(blob)

    # ---------------- UI ----------------
    def log(self, msg): self.emu.logmsg(str(msg))
    def register_command(self, name, fn, help=""):
        self.commands[name] = (fn, help)
    def add_panel(self, name, render_fn):
        """render_fn(width, height) -> list[str]，显示在右侧面板轮播里"""
        self._panels[name] = render_fn

    # ---------------- 内部 ----------------
    def _tick_frame(self):
        self.emu.keyboard.tick()          # headless 兜底：按键释放调度
        for a, v in self._frozen.items():
            if self.mmu.peek_raw(a) != v:
                self.mmu.poke_raw(a, v)
        for cb in self._frame_cbs:
            try:
                cb()
            except Exception:
                self.log("plugin frame error:\n" + traceback.format_exc())


class PluginManager:
    def __init__(self, api: EmuAPI):
        self.api = api
        self.loaded = {}

    def load_file(self, path):
        path = os.path.abspath(path)
        name = "u8plugin_" + os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if not hasattr(mod, "register"):
            raise RuntimeError(f"{path}: 缺少 register(api)")
        mod.register(self.api)
        self.loaded[path] = mod
        self.api.log(f"plugin loaded: {os.path.basename(path)}")
        return mod

    def load_dir(self, d):
        if not os.path.isdir(d):
            return
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".py") and not fn.startswith("_"):
                try:
                    self.load_file(os.path.join(d, fn))
                except Exception:
                    self.api.log(f"plugin {fn} failed:\n" + traceback.format_exc())


# ------------------- JSON-RPC (line protocol) -------------------
_RPC_WHITELIST = {
    "read8", "read16", "read_bytes", "write8", "write16", "write_bytes", "poke",
    "freeze", "unfreeze", "frozen_list", "regs", "get_reg", "set_reg",
    "press", "release", "release_all", "tap",
    "press_code", "release_code", "tap_code",
    "name_of", "code_of", "keys_held", "keys_held_codes",
    "keylog", "key_events", "type_keys",
    "key_seq", "key_seq_codes", "key_queue", "key_queue_len",
    "key_clear", "key_busy",
    "patch", "unpatch", "region_of",
    "screen_text", "screen_status", "pause", "resume", "step",
    "reset", "add_breakpoint", "del_breakpoint", "log",
}


class RpcServer(threading.Thread):
    """{"m":"read8","a":[0x8000]}\n  ->  {"ok":true,"r":18}\n"""
    daemon = True

    def __init__(self, api, host="127.0.0.1", port=4321, lock=None):
        super().__init__()
        self.api, self.lock = api, lock
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(4)

    def run(self):
        while True:
            conn, _ = self.sock.accept()
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        f = conn.makefile("rwb")
        for line in f:
            try:
                req = json.loads(line)
                m = req.get("m")
                if m not in _RPC_WHITELIST:
                    raise KeyError(f"method {m} not allowed")
                fn = getattr(self.api, m)
                if self.lock:
                    with self.lock:
                        r = fn(*req.get("a", []), **req.get("k", {}))
                else:
                    r = fn(*req.get("a", []), **req.get("k", {}))
                if isinstance(r, (bytes, bytearray)):
                    r = list(r)
                resp = {"ok": True, "r": r}
            except Exception as e:
                resp = {"ok": False, "e": str(e)}
            f.write((json.dumps(resp) + "\n").encode())
            f.flush()
