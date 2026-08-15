"""显存异步采样与盲文渲染

对齐 CasioEmuMsvc 的 Screen 外设 (Screen.cpp) 处理显存的方式:

- ClassWiz (fx-991CN X): 屏幕 192x63 点阵 + 顶部 1 条状态栏
- 显存位于 0xF800, 共 (63+1) x 32 = 2048 字节
- 每行 32 字节只显示前 24 字节 (24x8 = 192 像素), 后 8 字节为填充
- 点阵从第 1 行起渲染 (第 0 行是状态栏), 每字节 MSB 为最左像素
- 状态图标 (S/A/M/STO/DEG...) 全部编码在 buffer[1] 的各个位

盲文输出: 每个字符 = 2 列 x 4 行像素 (Unicode U+2800 系列 8 点),
192 像素宽 -> 96 字符/行, 63 行 -> 16 行。
"""

from __future__ import annotations

import threading

from .exceptions import CemError

# ---- ClassWiz (fx-991CN X) 屏幕参数 ----
N_ROW = 63           # 点阵行数
ROW_SIZE = 32        # 每行字节数
ROW_SIZE_DISP = 24   # 每行显示字节数 (24*8 = 192 像素)
FRAME_SIZE = (N_ROW + 1) * ROW_SIZE   # 2048 字节
FRAMEBUFFER_ADDR = 0xF800

# 状态栏图标: (名称, 帧内字节偏移) —— 来自 Screen.cpp sprite_bitmap
# ClassWiz 每个状态图标 = 0xF800 帧内某个字节的第 0 位 (mask=0x01),
# 偏移 0x00..0x16, 均位于状态栏行 (第 0 行) 区域。
STATUS_BITS = [
    ("S", 0x00), ("A", 0x01), ("M", 0x02), ("STO", 0x03),
    ("MATH", 0x05), ("D", 0x06), ("R", 0x07), ("G", 0x08),
    ("FIX", 0x09), ("SCI", 0x0A), ("E", 0x0B), ("CMPLX", 0x0C),
    ("ANGLE", 0x0D), ("WDOWN", 0x0F), ("LEFT", 0x10), ("DOWN", 0x11),
    ("UP", 0x12), ("RIGHT", 0x13), ("PAUSE", 0x15), ("SUN", 0x16),
]

# 像素位置 -> 盲文点 (2x4 块, U+2800 位序: 0,1,2=左列上中下; 3,4,5=右列上中下; 6,7=左/右下)
_PIXEL_TO_DOT = (0, 3, 1, 4, 2, 5, 6, 7)


def render_braille(frame, n_row=N_ROW, row_size=ROW_SIZE, disp=ROW_SIZE_DISP):
    """把显存帧渲染成盲文文本 (2列x4行/字符, U+2800 系列)。

    对齐 Screen.cpp: 点阵从第 1 行起 (第 0 行是状态栏, 不参与点阵),
    每行前 ``disp`` 字节, 每字节 MSB 为最左像素。返回多行文本。
    """
    width = disp * 8
    lines = []
    for cy in range((n_row + 3) // 4):
        chars = []
        for cx in range(width // 2):
            dots = 0
            for iy in range(4):
                dy = cy * 4 + iy          # 显示行号 (0 起)
                if dy >= n_row:
                    continue
                row = dy + 1              # 显存行号: 跳过状态栏行
                base = row * row_size
                for ix in range(2):
                    col = cx * 2 + ix
                    byte = frame[base + col // 8] if base + col // 8 < len(frame) else 0
                    if byte & (0x80 >> (col % 8)):
                        dots |= 1 << _PIXEL_TO_DOT[iy * 2 + ix]
            chars.append(chr(0x2800 + dots))
        lines.append("".join(chars))
    return "\n".join(lines)


def render_status(frame):
    """解析状态栏: 每个状态图标 = 帧内某字节 (偏移 0x00..0x16) 的第 0 位"""
    on = [
        name
        for name, offset in STATUS_BITS
        if offset < len(frame) and (frame[offset] & 0x01)
    ]
    return " ".join(on) if on else "-"


class ScreenView:
    """后台线程异步采样显存 (0xF800), 供 API 随时取用最新帧。

    :param emu: Emu 实例
    :param interval: 采样间隔秒数 (默认 0.15, 约 6.6 fps)
    """

    def __init__(self, emu, interval=0.15, size=FRAME_SIZE):
        self._emu = emu
        self.interval = float(interval)
        self.size = size
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame = b""
        self._version = 0

    # ------------------------------------------------------------------ #
    def start(self):
        """启动后台采样线程（重复调用安全）"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="cem-screen"
        )
        self._thread.start()

    def stop(self):
        """停止采样线程"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _loop(self):
        while not self._stop.is_set():
            try:
                frame = self._emu.read_bytes(FRAMEBUFFER_ADDR, self.size)
            except CemError:
                if not self._emu.running:
                    break            # 模拟器已退出
            except Exception:
                break
            else:
                with self._lock:
                    if frame != self._frame:
                        self._frame = frame
                        self._version += 1
            self._stop.wait(self.interval)

    # ------------------------------------------------------------------ #
    def latest(self):
        """最新一帧原始字节 (未采样到时为空 bytes)"""
        with self._lock:
            return bytes(self._frame)

    @property
    def version(self):
        """画面版本号 (每变化一次 +1)"""
        with self._lock:
            return self._version

    def text(self):
        """最新帧的盲文文本"""
        frame = self.latest()
        return render_braille(frame) if frame else ""

    def status(self):
        """最新帧的状态栏文本"""
        return render_status(self.latest())

    def wait_change(self, timeout=5.0):
        """阻塞等待画面变化, 返回是否在超时前发生变化"""
        target = self.version + 1
        deadline = self._monotonic() + timeout
        while self._monotonic() < deadline:
            if self.version >= target:
                return True
            self._stop.wait(0.05)
        return False

    @staticmethod
    def _monotonic():
        import time

        return time.monotonic()


class ScreenTUI:
    """终端 TUI: 后台线程反复打印盲文渲染的屏幕。

    独立于 ScreenView 采样线程运行 —— 只读最新帧, 不阻塞
    ``press`` / ``write`` / ``read`` 等其他 API 调用。
    画面无变化时不重复输出; 变化时清屏重绘 (ANSI)。

    :param view: ScreenView 实例
    :param interval: 刷新间隔秒数 (默认 0.15)
    :param show_status: 是否打印状态栏行
    """

    CLEAR = "\033[2J\033[H"   # 清屏 + 光标归位

    def __init__(self, view, interval=0.15, show_status=True):
        self._view = view
        self.interval = float(interval)
        self.show_status = bool(show_status)
        self._thread = None
        self._stop = threading.Event()
        self._last_version = -1
        self._out = None

    # ------------------------------------------------------------------ #
    def start(self, out=None):
        """启动打印线程。``out`` 可注入输出流 (默认 sys.stdout)。

        重复调用安全。返回 self。
        """
        self._out = out
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="cem-tui"
        )
        self._thread.start()
        return self

    def stop(self):
        """停止打印线程"""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def _loop(self):
        while not self._stop.is_set():
            version = self._view.version
            if version != self._last_version:
                self._last_version = version
                text = self._view.text()
                if text:
                    self._render(text)
            self._stop.wait(self.interval)

    def _render(self, text):
        import sys

        out = self._out if self._out is not None else sys.stdout
        parts = []
        if self.show_status:
            parts.append("状态栏: " + self._view.status())
        parts.append(text)
        out.write(self.CLEAR + "\n".join(parts) + "\n")
        out.flush()
