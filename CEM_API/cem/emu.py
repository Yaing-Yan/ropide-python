"""class Emu —— CasioEmuMsvc 的 Python 控制接口

Emu 负责:
1. 启动 CasioEmuMsvc
2. 等待 MCP 调试服务 (127.0.0.1:3001) 就绪
3. 通过 JSON-RPC 工具接口完成 按键 / 内存读写 等操作
4. kill() 关闭模拟器进程
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from .exceptions import (
    EmulatorNotFound,
    EmulatorNotRunning,
    EmulatorStartFailed,
    InvalidKeyError,
    PortBusyError,
)
from .keys import Key
from .mcp import McpClient
from .romfile import is_model_dir, load_buttons, make_model_dir
from .screen import ScreenTUI, ScreenView

EXE_CANDIDATES = ("CasioEmuMsvc.exe", "CasioEmuMsvc")


def _to_bytes(data, what="数据"):
    """把 hex 字符串 / bytes / int 列表 统一转为 bytearray"""
    if isinstance(data, str):
        tokens = data.strip().split()
        if not tokens:
            raise ValueError(f"{what} 为空")
        try:
            return bytearray(int(tok, 16) for tok in tokens)
        except ValueError as exc:
            raise ValueError(f"{what} 不是合法 hex 字符串: {data!r}") from exc
    if isinstance(data, (bytes, bytearray)):
        return bytearray(data)
    if isinstance(data, (list, tuple)):
        if not all(isinstance(item, int) and 0 <= item <= 255 for item in data):
            raise ValueError(f"{what} 必须是 0-255 的整数列表")
        return bytearray(data)
    raise TypeError(f"{what} 必须是 hex 字符串 / bytes / int 列表，收到 {type(data).__name__}")


def _to_hex_string(raw):
    """bytes -> '11 45 14 19'"""
    return " ".join(f"{b:02X}" for b in raw)


class Emu:
    """CasioEmuMsvc 模拟器实例。

    :param rom_file: 可传入 model 目录（含 config.json/config.bin）或裸 ROM
        文件（自动打包成 model 目录）。
    :param exe: CasioEmuMsvc 可执行文件路径；缺省时依次查找环境变量
        ``CASIOEMU_EXE``、当前目录、PATH。
    :param port: MCP 端口（默认 3001，与 McpPlugin 一致）。
    :param paused: 启动后是否暂停 CPU。
    :param headless: 无窗口模式（Linux/macOS 用 SDL dummy 驱动，Windows 需
        SDL 2.0.22+）。窗口不弹出，但 MCP 操控、显存读取照常可用。
    :param hold: press() 按键的按住时长（秒）。
    :param timeout: 等待 MCP 服务就绪的超时时间（秒）。
    :param attach: 端口已被占用时是否直接挂接现有实例（不启动新进程）。
    :param logfile: 模拟器 stdout/stderr 重定向文件；None 表示丢弃。
    """

    def __init__(
        self,
        rom_file=None,
        *,
        exe=None,
        port=3001,
        host="127.0.0.1",
        paused=True,
        headless=False,
        hold=0.08,
        timeout=60.0,
        attach=False,
        logfile=None,
        model_dir=None,
        extra_args=None,
        env=None,
        workdir=None,
    ):
        if rom_file is None and model_dir is None and not attach:
            raise ValueError("必须提供 rom_file 或 model_dir（或 attach=True）")
        if rom_file is not None and model_dir is not None:
            raise ValueError("rom_file 与 model_dir 不能同时提供")

        self.port = port
        self.host = host
        self.hold = float(hold)
        self.attach = attach
        self.headless = bool(headless)
        self._proc = None
        self._closed = False
        self.buttons = {}
        self._screen = None
        self._tui = None

        exe_path = self._resolve_exe(exe)
        if exe_path is not None:
            self.exe = exe_path
        else:
            self.exe = None

        # ---- 解析 model 目录（attach 模式可不提供，仅用于按键名表）----
        self.model_dir = None
        if model_dir is not None:
            self.model_dir = Path(model_dir)
            if not is_model_dir(self.model_dir):
                raise ValueError(
                    f"不是有效 model 目录（缺少 config.json/config.bin）: {self.model_dir}"
                )
        elif not attach:
            source = Path(rom_file)
            if is_model_dir(source):
                self.model_dir = source
            elif source.is_file():
                self.model_dir = make_model_dir(source)
            else:
                raise ValueError(f"rom_file 既不是 model 目录也不是文件: {source}")

        self.buttons = load_buttons(self.model_dir) if self.model_dir else {}

        # ---- MCP 客户端 ----
        self._mcp = McpClient(host=host, port=port, timeout=10.0)

        # ---- 启动 / 挂接 ----
        existing = self._mcp.health()
        if existing is not None:
            if not attach:
                raise PortBusyError(
                    f"{host}:{port} 已有 MCP 服务在运行；"
                    "如需挂接现有模拟器请传入 attach=True"
                )
            self._attach(existing)
        else:
            if exe_path is None:
                raise EmulatorNotFound(
                    "找不到 CasioEmuMsvc 可执行文件。请通过 exe= 指定，"
                    "或设置 CASIOEMU_EXE 环境变量，或用 tools/fetch_release.py 下载。"
                )
            self._launch(
                paused=paused,
                logfile=logfile,
                extra_args=extra_args,
                env=env,
                workdir=workdir,
            )
            self._wait_ready(timeout)

        # 初始化 MCP 会话
        self._mcp.initialize()

    # ------------------------------------------------------------------ #
    # 进程管理
    # ------------------------------------------------------------------ #
    @staticmethod
    def _resolve_exe(exe):
        if exe is not None:
            path = Path(exe)
            if path.is_file():
                return str(path)
            raise EmulatorNotFound(f"exe 不存在: {exe}")
        env_exe = os.environ.get("CASIOEMU_EXE")
        if env_exe:
            path = Path(env_exe)
            if path.is_file():
                return str(path)
        for candidate in EXE_CANDIDATES:
            found = shutil.which(candidate)
            if found:
                return found
            local = Path(candidate)
            if local.is_file():
                return str(local)
        return None

    def _launch(self, *, paused, logfile, extra_args, env, workdir):
        args = [self.exe, str(self.model_dir)]
        # 注意: CasioEmuMsvc 只要 argv 中存在 paused 参数就会暂停 CPU
        # (源码 Emulator.cpp: argv_map.find("paused") != end)，paused=0 无效。
        # 因此 paused=False 时干脆不传该参数。
        if paused:
            args.append("paused=1")
        for key, value in (extra_args or {}).items():
            args.append(f"{key}={value}")

        if logfile is None:
            stdout = stderr = subprocess.DEVNULL
        else:
            log = open(logfile, "ab", buffering=0)
            stdout = stderr = log
        launch_env = dict(os.environ)
        if env:
            launch_env.update(env)
        if self.headless:
            # 无窗口模式: SDL dummy 视频驱动 + 软件渲染器
            # （Windows 需 SDL 2.0.22+ 才支持 dummy 驱动）
            launch_env.setdefault("SDL_VIDEODRIVER", "dummy")
            launch_env.setdefault("SDL_RENDER_DRIVER", "software")
        cwd = workdir or str(Path(self.exe).parent)

        try:
            self._proc = subprocess.Popen(
                args,
                cwd=cwd,
                env=launch_env,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise EmulatorStartFailed(f"无法启动 {self.exe}: {exc}") from exc

    def _attach(self, health):
        self._proc = None
        self.attached = True

    def _wait_ready(self, timeout):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise EmulatorStartFailed(
                    f"模拟器进程提前退出，退出码 {self._proc.returncode}"
                )
            health = self._mcp.health()
            if health is not None and health.get("status") == "ok":
                return
            time.sleep(0.25)
        raise EmulatorStartFailed(
            f"MCP 服务 {self.host}:{self.port} 在 {timeout:.0f}s 内未就绪。"
            "请确认 McpPlugin.dll 与 CasioEmuMsvc.exe 在同一目录。"
        )

    def kill(self):
        """终止模拟器进程。重复调用安全。"""
        if self._tui is not None:
            self._tui.stop()
        if self._screen is not None:
            self._screen.stop()
        if self._closed and self._proc is None:
            return
        self._closed = True
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

    def close(self):
        self.kill()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.kill()

    def __del__(self):
        try:
            self.kill()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 状态
    # ------------------------------------------------------------------ #
    def _check(self):
        if self._closed:
            raise EmulatorNotRunning("模拟器已被 kill()")
        if self._proc is not None and self._proc.poll() is not None:
            raise EmulatorNotRunning(
                f"模拟器进程已退出，退出码 {self._proc.returncode}"
            )

    def _call(self, tool, arguments=None):
        self._check()
        return self._mcp.call_tool(tool, arguments)

    @property
    def running(self):
        if self._closed:
            return False
        if self._proc is None:
            return True  # attach 模式
        return self._proc.poll() is None

    @property
    def model_name(self):
        return self.status().get("model_name", "")

    # ------------------------------------------------------------------ #
    # 显存异步采样 / 盲文渲染
    # ------------------------------------------------------------------ #
    @property
    def screen(self):
        """后台异步采样显存的 ScreenView（需先 start_screen 启动线程）"""
        if self._screen is None:
            self._screen = ScreenView(self)
        return self._screen

    def start_screen(self, interval=0.15):
        """启动显存异步采样线程，返回 ScreenView。

        之后可用 ``emu.screen.text()`` 取盲文渲染文本、
        ``emu.screen.status()`` 取状态栏、``emu.screen.wait_change()``
        等待画面变化。headless 模式下同样可用。
        """
        self.screen.interval = float(interval)
        self.screen.start()
        return self.screen

    def showscreen(self, interval=0.15, show_status=True, out=None):
        """启动终端 TUI 反复打印屏幕（异步）。

        后台线程循环刷新盲文渲染的屏幕，**不阻塞** press/write/read 等
        其他调用 —— 可以边看屏幕边按键。画面变化时自动重绘。

        :param interval: 刷新间隔秒数
        :param show_status: 是否打印状态栏（S/A/M/STO/DEG...）
        :param out: 输出流（默认 sys.stdout，测试可注入）
        :return: ScreenTUI 对象（可用 .stop() 停止）
        """
        self.start_screen(interval=interval)
        if self._tui is None:
            self._tui = ScreenTUI(self.screen)
        self._tui.interval = float(interval)
        self._tui.show_status = bool(show_status)
        self._tui.start(out=out)
        return self._tui

    def hidescreen(self):
        """停止 showscreen 的打印线程（采样线程保留）"""
        if self._tui is not None:
            self._tui.stop()

    def status(self):
        """获取运行状态: model_name / paused / program_counter / cps ..."""
        return self._call("get_status")

    def pause(self):
        return self._call("pause")

    def resume(self):
        return self._call("resume")

    def reset(self):
        return self._call("reset")

    def step_into(self):
        return self._call("step_into")

    def step_over(self):
        return self._call("step_over")

    def step_out(self):
        return self._call("step_out")

    # ------------------------------------------------------------------ #
    # 键盘
    # ------------------------------------------------------------------ #
    def _resolve(self, key):
        """int / Key 常量 / 字符串键名 -> kiko 码

        字符串键的解析顺序: 通俗表示 (Key 表, 如 "="、 "sin"、"POWER")
        优先，model 按钮表兜底。部分旧版 model 配置用 SDL 键名（如 0x30
        记为 '='、0x42 记为 'Space'），与真实键位不符，因此以通俗表示为准。
        """
        if isinstance(key, str):
            name = key.strip()
            if name:
                try:
                    return Key.resolve(name)
                except InvalidKeyError:
                    if name in self.buttons:
                        return self.buttons[name]
                    raise InvalidKeyError(
                        f"未知键名: {key!r}。可用通俗表示（如 'POWER'/'sin'/'M+'）"
                        f"或 model 键名: {sorted(self.buttons) or '(无)'}"
                    ) from None
        return Key.resolve(key)

    def key_down(self, key):
        """按下指定键（保持按住）"""
        code = self._resolve(key)
        return self._call("keyboard_code", {"code": code, "pressed": True})

    def key_up(self, key):
        """松开指定键"""
        code = self._resolve(key)
        return self._call("keyboard_code", {"code": code, "pressed": False})

    def press(self, keys, hold=None, interval=0.1):
        """按一下键（支持空格分隔的连续按键）。

        :param keys: 单个键（int / Key.KEY_* / 通俗表示），或用空格分隔的
            多个键字符串，例如 ``"shift 9 3 = ac"`` —— 依次按下每个键。
        :param hold: 每个键的按住时长（默认用 self.hold）
        :param interval: 连续按键之间（前一个松开后）的间隔秒数，默认 0.1
        """
        if isinstance(keys, str):
            tokens = keys.split()
            if len(tokens) > 1:
                results = []
                for index, token in enumerate(tokens):
                    results.append(self.press(token, hold=hold, interval=interval))
                    if index != len(tokens) - 1:
                        time.sleep(interval)
                return results
            if not tokens:
                raise InvalidKeyError("按键序列为空")
            key = tokens[0]
        else:
            key = keys
        self.key_down(key)
        time.sleep(self.hold if hold is None else float(hold))
        return self.key_up(key)

    def release_all_keys(self):
        return self._call("keyboard_release_all")

    def keyboard_matrix(self, ki, ko, pressed):
        """按 KI/KO 矩阵坐标按键（ki: 0-7, ko: 0-15）"""
        return self._call("keyboard_key", {"ki": ki, "ko": ko, "pressed": pressed})

    # ------------------------------------------------------------------ #
    # 开机 / 引导检测
    # ------------------------------------------------------------------ #
    # 屏幕显存地址: ES PLUS / ClassWiz / fx-9860G 家族统一在 0xF800
    # (Screen.cpp "Screen/Buffer")。读取 (216+1) 行 x 48 字节覆盖所有机型。
    FRAMEBUFFER_ADDR = 0xF800
    FRAMEBUFFER_SIZE = 217 * 48

    def screen_buffer(self, size=None):
        """读取屏幕显存原始字节（可据此判断开机/界面状态）"""
        return self.read_bytes(self.FRAMEBUFFER_ADDR, size or self.FRAMEBUFFER_SIZE)

    def wait_boot(self, timeout=30.0, interval=0.5, window=8, min_idle_samples=3):
        """等待引导完成。

        判据: 屏幕必须先发生过变化（电源键重置 -> 引导 -> 菜单），随后在
        最近 ``window`` 次采样内只出现 <=2 种内容（静态画面=1 种，
        光标闪烁=2 种）即认为已进入稳定运行状态。若一开始就毫无变化
        （已开机的静止界面），连续 ``min_idle_samples`` 次无变化也视为就绪。

        返回是否在超时前就绪。
        """
        import hashlib

        from collections import deque

        deadline = time.monotonic() + timeout
        recent = deque(maxlen=window)
        last = None
        saw_change = False
        idle = 0
        while time.monotonic() < deadline:
            digest = hashlib.md5(self.screen_buffer()).digest()
            if last is not None and digest != last:
                saw_change = True
                idle = 0
            else:
                idle += 1
            last = digest
            recent.append(digest)
            if saw_change and len(set(recent)) <= 2 and len(recent) >= 3:
                return True
            if not saw_change and idle >= min_idle_samples:
                return True
            time.sleep(interval)
        return False

    def power_on(self, hold=1.0, wait=True, timeout=25.0):
        """按下电源键 (0xFF) 开机，可选等待引导完成。

        注意: MCP 的 PC/寄存器在 nX-U8 机型上不可靠（读取的是未执行的
        JIT CPU），因此用显存内容变化判断开机状态。
        """
        self.press(Key.KEY_POWER, hold=hold)
        if wait:
            return self.wait_boot(timeout=timeout)
        return True

    # ------------------------------------------------------------------ #
    # 内存读写（核心 API）
    # ------------------------------------------------------------------ #
    def read(self, offset, byte=4):
        """读取 ``byte`` 个字节，返回 hex 字符串如 '11 45 14 19'。"""
        size = int(byte)
        if size < 0:
            raise ValueError("byte 不能为负数")
        result = self._call("read_memory", {"address": int(offset), "size": size})
        raw = bytes(result.get("bytes", []))
        return _to_hex_string(raw)

    def read_bytes(self, offset, size):
        """读取 ``size`` 个字节，返回 bytes"""
        result = self._call("read_memory", {"address": int(offset), "size": int(size)})
        return bytes(result.get("bytes", []))

    def write(self, offset, byte="", *, data=None):
        """向 ``offset`` 写入字节。

        :param offset: 起始地址
        :param byte: hex 字符串，如 '11 45 14 19'（也接受 bytes / int 列表）
        :param data: 与 byte 等价的别名参数（bytes）
        """
        if data is not None:
            raw = _to_bytes(data, "data")
        else:
            raw = _to_bytes(byte, "byte")
        return self._call(
            "write_memory",
            {"address": int(offset), "bytes": [int(b) for b in raw]},
        )

    def write_bytes(self, offset, data):
        """向 ``offset`` 写入 bytes"""
        return self.write(offset, data=data)

    # ------------------------------------------------------------------ #
    # 代码空间 / 调试
    # ------------------------------------------------------------------ #
    def read_code(self, offset, count):
        """读取代码空间的 16-bit 指令字列表"""
        result = self._call("read_code", {"address": int(offset), "count": int(count)})
        return list(result.get("words", []))

    def write_code(self, offset, byte=""):
        """向 ROM 镜像打补丁（write_code）"""
        raw = _to_bytes(byte, "byte")
        return self._call(
            "write_code",
            {"address": int(offset), "bytes": [int(b) for b in raw]},
        )

    def disassemble(self, address, count=16):
        """反汇编 count 条指令"""
        return self._call(
            "disassemble", {"address": int(address), "count": int(count)}
        ).get("lines", [])

    def registers(self):
        """列出全部寄存器"""
        return self._call("list_registers").get("registers", [])

    def read_register(self, name):
        result = self._call("read_register", {"name": name})
        return {"value": result["value"], "bit_width": result["bit_width"]}

    def write_register(self, name, value):
        return self._call("write_register", {"name": name, "value": int(value)})

    def backtrace(self):
        return self._call("get_backtrace").get("backtrace", "")

    def labels(self, query="", limit=256):
        return self._call("list_labels", {"query": query, "limit": limit}).get(
            "labels", []
        )

    # ------------------------------------------------------------------ #
    # 断点 / 快照
    # ------------------------------------------------------------------ #
    def add_execution_breakpoint(self, address):
        return self._call("add_execution_breakpoint", {"address": int(address)})

    def remove_execution_breakpoint(self, address):
        return self._call("remove_execution_breakpoint", {"address": int(address)})

    def add_memory_breakpoint(self, address, write, break_when_hit=True):
        return self._call(
            "add_memory_breakpoint",
            {
                "address": int(address),
                "write": bool(write),
                "break_when_hit": bool(break_when_hit),
            },
        )

    def remove_memory_breakpoint(self, address, write):
        return self._call(
            "remove_memory_breakpoint", {"address": int(address), "write": bool(write)}
        )

    def clear_memory_breakpoints(self):
        return self._call("clear_memory_breakpoints")

    def list_snapshots(self):
        return self._call("list_snapshots").get("snapshots", [])

    def save_snapshot(self, label="CEM-API Snapshot"):
        return self._call("save_snapshot", {"label": label})

    def load_snapshot(self, snapshot_id):
        return self._call("load_snapshot", {"id": int(snapshot_id)})

    def delete_snapshot(self, snapshot_id):
        return self._call("delete_snapshot", {"id": int(snapshot_id)})

    # ------------------------------------------------------------------ #
    # 硬件设置
    # ------------------------------------------------------------------ #
    def set_cycles_per_second(self, cps):
        return self._call("set_cycles_per_second", {"cps": int(cps)})

    def raise_interrupt(self, index):
        return self._call("raise_interrupt", {"index": int(index)})

    def hot_reload_rom(self):
        return self._call("hot_reload_rom")
