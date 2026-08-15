"""CEM-API 测试: 纯单元测试 + 假 MCP 服务器集成测试

运行: python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cem import Emu, Key, InvalidKeyError, ToolError
from cem.keys import resolve_key
from cem.mcp import McpClient
from cem.romfile import (
    default_config,
    is_model_dir,
    load_buttons,
    make_model_dir,
    write_blank_png,
)
from cem.screen import (
    FRAME_SIZE,
    N_ROW,
    ROW_SIZE,
    ROW_SIZE_DISP,
    render_braille,
    render_status,
)

TESTS_DIR = Path(__file__).resolve().parent
FAKE_EMULATOR = TESTS_DIR / "fake_emulator.py"


def free_port():
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeMcpServer:
    """在测试进程内直接启动假 MCP 服务器（供 McpClient 测试）"""

    def __init__(self):
        import threading

        from http.server import ThreadingHTTPServer

        self.port = free_port()
        sys.path.insert(0, str(TESTS_DIR))
        import fake_emulator as fake

        fake.PORT = self.port
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), fake.Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self):
        self._server.shutdown()
        self._server.server_close()


class TestHexParsing(unittest.TestCase):
    def test_write_bytes_format(self):
        from cem.emu import _to_bytes, _to_hex_string

        raw = _to_bytes("11 45 14 19")
        self.assertEqual(bytes(raw), b"\x11\x45\x14\x19")
        self.assertEqual(_to_bytes("11,45,14,19".replace(",", " ")), raw)
        self.assertEqual(_to_bytes([0x11, 0x45]), b"\x11\x45")
        self.assertEqual(_to_bytes(b"\x11\x45"), b"\x11\x45")
        self.assertEqual(_to_hex_string(raw), "11 45 14 19")
        with self.assertRaises(ValueError):
            _to_bytes("11 ZZ")
        with self.assertRaises(ValueError):
            _to_bytes([256])


class TestKeys(unittest.TestCase):
    def test_verified_values(self):
        # 与原版 CEM fx570esplus / CasioEmuX fx991cnx model.lua 一致
        self.assertEqual(Key.KEY_7, 0x02)
        self.assertEqual(Key.KEY_8, 0x12)
        self.assertEqual(Key.KEY_9, 0x22)
        self.assertEqual(Key.KEY_4, 0x01)
        self.assertEqual(Key.KEY_5, 0x11)
        self.assertEqual(Key.KEY_6, 0x21)
        self.assertEqual(Key.KEY_1, 0x00)
        self.assertEqual(Key.KEY_2, 0x10)
        self.assertEqual(Key.KEY_3, 0x20)
        self.assertEqual(Key.KEY_0, 0x64)
        self.assertEqual(Key.KEY_DOT, 0x63)
        self.assertEqual(Key.KEY_EXP, 0x35)     # '^' 乘方 (CNX 键码矩阵 20 08)
        self.assertEqual(Key.KEY_X10, 0x62)     # '×10ˣ' (04 40)
        self.assertEqual(Key.KEY_ANS, 0x61)     # 'M' (02 40)
        self.assertEqual(Key.KEY_ADD, 0x30)
        self.assertEqual(Key.KEY_SUB, 0x40)
        self.assertEqual(Key.KEY_MUL, 0x31)
        self.assertEqual(Key.KEY_DIV, 0x41)
        self.assertEqual(Key.KEY_EXE, 0x60)
        self.assertEqual(Key.KEY_ACON, 0x42)
        self.assertEqual(Key.KEY_DEL, 0x32)
        self.assertEqual(Key.KEY_UP, 0x27)
        self.assertEqual(Key.KEY_DOWN, 0x36)
        self.assertEqual(Key.KEY_LEFT, 0x26)
        self.assertEqual(Key.KEY_RIGHT, 0x37)
        self.assertEqual(Key.KEY_POWER, 0xFF)

    def test_cwz_common_names(self):
        """fx-991CN X 通俗表示 (CWZ.N)，对照 document.tex 键码矩阵"""
        # 功能键: 16位键码 0xKO:KI -> kiko = (列号<<4)|行号
        self.assertEqual(Key.KEY_SHIFT, 0x07)   # 80 01
        self.assertEqual(Key.KEY_ALPHA, 0x17)   # 80 02
        self.assertEqual(Key.KEY_MENU, 0x47)    # 80 10
        self.assertEqual(Key.KEY_OPTN, 0x06)    # 40 01
        self.assertEqual(Key.KEY_CALC, 0x16)    # 40 02
        self.assertEqual(Key.KEY_INT, 0x46)     # 40 10
        self.assertEqual(Key.KEY_X, 0x56)       # 40 20
        self.assertEqual(Key.KEY_FRAC, 0x05)    # 20 01
        self.assertEqual(Key.KEY_SQRT, 0x15)    # 20 02
        self.assertEqual(Key.KEY_SQ, 0x25)      # 20 04
        self.assertEqual(Key.KEY_LOG, 0x45)     # 20 10
        self.assertEqual(Key.KEY_LN, 0x55)      # 20 20
        self.assertEqual(Key.KEY_NEGA, 0x04)    # 10 01
        self.assertEqual(Key.KEY_DMS, 0x14)     # 10 02
        self.assertEqual(Key.KEY_RECI, 0x24)    # 10 04
        self.assertEqual(Key.KEY_SIN, 0x34)     # 10 08
        self.assertEqual(Key.KEY_COS, 0x44)     # 10 10
        self.assertEqual(Key.KEY_TAN, 0x54)     # 10 20
        self.assertEqual(Key.KEY_STO, 0x03)     # 08 01
        self.assertEqual(Key.KEY_ENG, 0x13)     # 08 02
        self.assertEqual(Key.KEY_LPAREN, 0x23)  # 08 04
        self.assertEqual(Key.KEY_RPAREN, 0x33)  # 08 08
        self.assertEqual(Key.KEY_S2D, 0x43)     # 08 10
        self.assertEqual(Key.KEY_MPLUS, 0x53)   # 08 20

    def test_resolve(self):
        self.assertEqual(resolve_key(0x42), 0x42)
        self.assertEqual(resolve_key(Key.KEY_ACON), 0x42)
        self.assertEqual(resolve_key("KEY_ACON"), 0x42)
        self.assertEqual(resolve_key("ACON"), 0x42)

    def test_resolve_common_names(self):
        """通俗表示: 大小写不敏感，含符号键"""
        self.assertEqual(resolve_key("POWER"), 0xFF)
        self.assertEqual(resolve_key("power"), 0xFF)
        self.assertEqual(resolve_key("ON"), 0xFF)
        self.assertEqual(resolve_key("sin"), 0x34)
        self.assertEqual(resolve_key("SIN"), 0x34)
        self.assertEqual(resolve_key("Shift"), 0x07)
        self.assertEqual(resolve_key("menu"), 0x47)
        self.assertEqual(resolve_key("M+"), 0x53)
        self.assertEqual(resolve_key("m+"), 0x53)
        self.assertEqual(resolve_key("AC"), 0x42)
        self.assertEqual(resolve_key("×"), 0x31)
        self.assertEqual(resolve_key("*"), 0x31)
        self.assertEqual(resolve_key("÷"), 0x41)
        self.assertEqual(resolve_key("/"), 0x41)
        self.assertEqual(resolve_key("+"), 0x30)
        self.assertEqual(resolve_key("-"), 0x40)
        self.assertEqual(resolve_key("="), 0x60)
        self.assertEqual(resolve_key("("), 0x23)
        self.assertEqual(resolve_key(")"), 0x33)
        self.assertEqual(resolve_key("10^X"), 0x62)

    def test_resolve_cwz_aliases(self):
        """CWZ.N 别名词表（对照 index.html 的 MAP）"""
        aliases = {
            "dfm": 0x14, "dms": 0x14,
            "jf": 0x46, "int": 0x46,
            "fs": 0x05, "frac": 0x05,
            "gh": 0x15, "sqrt": 0x15,
            "pf": 0x25, "sq": 0x25,
            "cf": 0x35, "exp": 0x35,
            "fu": 0x04, "nega": 0x04,
            "ds": 0x24, "reci": 0x24,
            "times": 0x31, "cheng": 0x31,
            "chu": 0x41,
            "plus": 0x30, "jia": 0x30,
            "sub": 0x40, "jian": 0x40,
            "dot": 0x63,
            "del": 0x32, "ac": 0x42, "on": 0xFF,
            "s2d": 0x43, "x10": 0x62, "ans": 0x61,
            "sto": 0x03, "eng": 0x13, "calc": 0x16,
            "optn": 0x06, "alpha": 0x17, "up": 0x27,
            "down": 0x36, "left": 0x26, "right": 0x37,
            "log": 0x45, "ln": 0x55, "cos": 0x44, "tan": 0x54,
        }
        for name, code in aliases.items():
            self.assertEqual(resolve_key(name), code, f"别名 {name!r}")

    def test_unknown(self):
        with self.assertRaises(InvalidKeyError):
            resolve_key("NOPE")
        with self.assertRaises(InvalidKeyError):
            resolve_key(-1)
        with self.assertRaises(InvalidKeyError):
            resolve_key(256)


class TestRomFile(unittest.TestCase):
    def test_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_blank_png(Path(tmp) / "interface.png", 410, 810)
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            # 解压验证尺寸
            import struct
            import zlib

            ihdr = data[16:24]
            w, h = struct.unpack(">II", ihdr[:8])
            self.assertEqual((w, h), (410, 810))
            zlib.decompress(data[41:-12])

    def test_make_model_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "rom.bin"
            rom.write_bytes(b"\x00" * 128)
            model = make_model_dir(rom, Path(tmp) / "model")
            self.assertTrue(is_model_dir(model))
            self.assertTrue((model / "rom.bin").is_file())
            self.assertTrue((model / "interface.png").is_file())
            self.assertTrue((model / "config.json").is_file())
            config = default_config()
            required = [
                "model_name", "hardware_id", "csr_mask", "real_hardware",
                "pd_value", "interface_path", "rom_path", "flash_path",
                "ink_color", "enable_new_screen", "is_sample_rom",
                "legacy_ko", "u16_mode", "ml620_mirroring", "large_model",
                "buttons", "sprites",
            ]
            for field in required:
                self.assertIn(field, config)

    def test_buttons_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "rom.bin"
            rom.write_bytes(b"\x00" * 8)
            model = make_model_dir(rom, Path(tmp) / "model")
            buttons = load_buttons(model)
            self.assertEqual(buttons["AC/ON"], 0x42)
            self.assertEqual(buttons["0"], 0x64)
            self.assertEqual(buttons["EXE"], 0x60)
            self.assertGreaterEqual(len(buttons), 20)


class TestMcpClient(unittest.TestCase):
    def test_lifecycle(self):
        server = FakeMcpServer()
        try:
            client = McpClient(port=server.port)
            self.assertIsNotNone(client.health())
            client.initialize()
            self.assertEqual(client.session_id, "fake-session-1234")
            result = client.call_tool("get_status")
            self.assertEqual(result["model_name"], "FAKE-570ES-PLUS")
        finally:
            server.close()

    def test_memory_roundtrip(self):
        server = FakeMcpServer()
        try:
            client = McpClient(port=server.port)
            client.call_tool(
                "write_memory",
                {"address": 0xE9E0, "bytes": [0x11, 0x45, 0x14, 0x19]},
            )
            result = client.call_tool("read_memory", {"address": 0xE9E0, "size": 4})
            self.assertEqual(result["bytes"], [0x11, 0x45, 0x14, 0x19])
        finally:
            server.close()

    def test_unknown_tool(self):
        server = FakeMcpServer()
        try:
            client = McpClient(port=server.port)
            with self.assertRaises(ToolError):
                client.call_tool("no_such_tool")
        finally:
            server.close()


class TestEmuIntegration(unittest.TestCase):
    """用假模拟器进程走完整 Emu 生命周期"""

    fake_exe = str(TESTS_DIR / "fake_emulator.sh")

    def test_full_flow(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 4096)
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(
                rom,
                exe=self.fake_exe,
                env=env,
                port=port,
                workdir=str(TESTS_DIR),
                timeout=30,
            ) as emu:
                self.assertTrue(emu.running)
                self.assertEqual(emu.status()["model_name"], "FAKE-570ES-PLUS")
                self.assertTrue(emu.status()["paused"])

                emu.press(Key.KEY_ACON)
                self.assertEqual(emu.read(0xE9E0, 4), "00 00 00 00")
                emu.write(offset=0xE9E0, byte="11 45 14 19")
                self.assertEqual(emu.read(0xE9E0, 4), "11 45 14 19")
                self.assertEqual(emu.read(offset=0xE9E0), "11 45 14 19")

                emu.write(0x100, byte="FF 00")
                self.assertEqual(emu.read_bytes(0x100, 2), b"\xff\x00")

                emu.press("0")
                emu.key_down("AC/ON")
                emu.key_up("AC/ON")

                regs = emu.registers()
                self.assertEqual(regs[0]["name"], "r0")
                self.assertEqual(emu.read_register("r0")["value"], 0x12)

                emu.pause()
                self.assertTrue(emu.status()["paused"])
                emu.resume()
                self.assertFalse(emu.status()["paused"])

            # 退出 context manager 后进程应已终止
            self.assertFalse(emu.running)

    def test_press_sequence(self):
        """空格分隔的连续按键"""
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(rom, exe=self.fake_exe, env=env, port=port,
                     workdir=str(TESTS_DIR), timeout=30) as emu:
                emu.press("1 + 2", interval=0)
                events = emu._mcp.call_tool("get_key_events")["events"]
            pressed = [(e["code"], e["pressed"]) for e in events]
            self.assertEqual(pressed, [
                (0x00, True), (0x00, False),   # 1
                (0x30, True), (0x30, False),   # +
                (0x10, True), (0x10, False),   # 2
            ])

    def test_press_sequence_common_names(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(rom, exe=self.fake_exe, env=env, port=port,
                     workdir=str(TESTS_DIR), timeout=30) as emu:
                emu.press("shift 9 = ac", interval=0)
                events = emu._mcp.call_tool("get_key_events")["events"]
            down_codes = [e["code"] for e in events if e["pressed"]]
            self.assertEqual(down_codes, [0x07, 0x22, 0x60, 0x42])

    def test_resolve_precedence(self):
        """通俗表示优先于 model 按钮表: 旧 config 里 0x30 被命名为 '='，
        但按 CNX 键码矩阵它是 '+'，press('=') 必须按真正的 = (0x60)"""
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            model = make_model_dir(rom, Path(tmp) / "model", buttons=[
                {"kiko": 0x30, "keyname": "=", "rect": {"x": 0, "y": 0, "w": 1, "h": 1}},
                {"kiko": 0x60, "keyname": "Return", "rect": {"x": 0, "y": 0, "w": 1, "h": 1}},
            ])
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(model_dir=str(model), exe=self.fake_exe, env=env,
                     port=port, workdir=str(TESTS_DIR), timeout=30) as emu:
                self.assertEqual(emu._resolve("="), 0x60)
                self.assertEqual(emu._resolve("+"), 0x30)
                # model 独有的键名仍可用（兜底）
                self.assertEqual(emu._resolve("Return"), 0x60)
                emu.press("=", interval=0)
                events = emu._mcp.call_tool("get_key_events")["events"]
            down = [e["code"] for e in events if e["pressed"]]
            self.assertEqual(down, [0x60])

    def test_headless_env(self):
        """headless=True 时给模拟器进程注入 SDL dummy 驱动环境变量"""
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(rom, exe=self.fake_exe, env=env, port=port,
                     workdir=str(TESTS_DIR), timeout=30, headless=True) as emu:
                got = emu._mcp.call_tool("get_env")["env"]
            self.assertEqual(got.get("SDL_VIDEODRIVER"), "dummy")
            self.assertEqual(got.get("SDL_RENDER_DRIVER"), "software")
            # 用户显式传入的 env 优先
            port2 = free_port()
            env2 = {"CEM_FAKE_PORT": str(port2), "SDL_VIDEODRIVER": "x11"}
            with Emu(rom, exe=self.fake_exe, env=env2, port=port2,
                     workdir=str(TESTS_DIR), timeout=30, headless=True) as emu:
                got2 = emu._mcp.call_tool("get_env")["env"]
            self.assertEqual(got2.get("SDL_VIDEODRIVER"), "x11")

    def test_kill(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            emu = Emu(
                rom,
                exe=self.fake_exe,
                env=env,
                port=port,
                workdir=str(TESTS_DIR),
                timeout=30,
            )
            self.assertTrue(emu.running)
            emu.kill()
            self.assertFalse(emu.running)
            with self.assertRaises(Exception):
                emu.read(0, 1)
            emu.kill()  # 重复 kill 安全

    def test_attach(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            first = Emu(
                rom,
                exe=self.fake_exe,
                env=env,
                port=port,
                workdir=str(TESTS_DIR),
                timeout=30,
            )
            try:
                from cem.exceptions import PortBusyError

                with self.assertRaises(PortBusyError):
                    Emu(rom, exe=self.fake_exe, env=env, port=port,
                        workdir=str(TESTS_DIR))
                attached = Emu(rom, exe=self.fake_exe, env=env, port=port,
                               workdir=str(TESTS_DIR), attach=True)
                self.assertEqual(attached.status()["model_name"], "FAKE-570ES-PLUS")
                attached.kill()  # attach 模式不持有进程
            finally:
                first.kill()


class TestBraille(unittest.TestCase):
    """盲文渲染: 对齐 Screen.cpp (192x63, 每行24字节, MSB 先左)"""

    def make_frame(self, fills=()):
        frame = bytearray(FRAME_SIZE)
        for (row, col) in fills:
            byte_idx = row * ROW_SIZE + col // 8
            frame[byte_idx] |= 0x80 >> (col % 8)
        return bytes(frame)

    def test_dimensions(self):
        text = render_braille(b"\x00" * FRAME_SIZE)
        lines = text.split("\n")
        self.assertEqual(len(lines), (N_ROW + 3) // 4)   # 16 行
        self.assertEqual(len(lines[0]), (ROW_SIZE_DISP * 8) // 2)  # 96 字符宽

    def test_single_pixel_dots(self):
        """单个像素点亮 -> 对应盲文点"""
        # 点阵从第 1 行起: 像素(1,0) -> 字符(0,0) 的 dot1 (0x2801)
        frame = self.make_frame([(1, 0)])
        self.assertEqual(render_braille(frame).split("\n")[0][0], "\u2801")
        # 像素(1,1) -> 同字符右列 dot4 (0x2808)
        frame = self.make_frame([(1, 1)])
        self.assertEqual(render_braille(frame).split("\n")[0][0], "\u2808")
        # 像素(1,3) -> 字符(0,1) 右列 dot4 (2列/字符)
        frame = self.make_frame([(1, 3)])
        self.assertEqual(render_braille(frame).split("\n")[0][1], "\u2808")
        # 像素(2,0) -> dot2 (0x2802)
        frame = self.make_frame([(2, 0)])
        self.assertEqual(render_braille(frame).split("\n")[0][0], "\u2802")
        # 像素(4,0) -> dot7 (0x2840)
        frame = self.make_frame([(4, 0)])
        self.assertEqual(render_braille(frame).split("\n")[0][0], "\u2840")

    def test_full_line(self):
        """第 1 行全部 192 像素点亮: 每字符 2 点 (dot1+dot4), 96 字符"""
        frame = bytearray(FRAME_SIZE)
        frame[1 * ROW_SIZE : 1 * ROW_SIZE + ROW_SIZE_DISP] = b"\xFF" * ROW_SIZE_DISP
        text = render_braille(bytes(frame))
        line = text.split("\n")[0]
        self.assertEqual(len(line), 96)
        self.assertEqual(line, "\u2809" * 96)   # dot1(0x01) + dot4(0x08)

    def test_status_line(self):
        # 每个状态图标 = 帧内偏移字节的第 0 位 (Screen.cpp sprite_bitmap)
        frame = bytearray(FRAME_SIZE)
        frame[0x05] = 0x01    # MATH
        frame[0x06] = 0x01    # D (DEG)
        frame[0x06] |= 0x08   # 高位是点阵像素, 不影响状态
        self.assertEqual(render_status(bytes(frame)), "MATH D")
        self.assertEqual(render_status(bytes(FRAME_SIZE)), "-")

    def test_msb_first(self):
        """每字节 MSB 为最左像素: 0x80 -> 列0, 0x01 -> 列7"""
        f1 = self.make_frame([(1, 0)])
        f2 = self.make_frame([(1, 7)])
        self.assertEqual(render_braille(f1).split("\n")[0][0], "\u2801")
        self.assertNotEqual(render_braille(f2).split("\n")[0][0], "\u2801")


class TestScreenView(unittest.TestCase):
    """ScreenView 异步采样 (假模拟器)"""

    fake_exe = str(TESTS_DIR / "fake_emulator.sh")

    def test_async_sampling(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            with Emu(rom, exe=self.fake_exe, env=env, port=port,
                     workdir=str(TESTS_DIR), timeout=30) as emu:
                sv = emu.start_screen(interval=0.05)
                self.assertTrue(sv.running)
                # 假模拟器显存初始全 0 -> 第一帧盲文全空格
                v0 = sv.version
                self.assertTrue(emu.screen.wait_change(timeout=5))
                self.assertEqual(emu.screen.text().split("\n")[0], "\u2800" * 96)
                # 写显存 -> 画面变化 -> wait_change 返回
                emu.write(offset=0xF800, byte="80 00 00 00")
                self.assertTrue(emu.screen.wait_change(timeout=5))
                self.assertGreater(sv.version, v0)
                # 渲染: 帧字节第 1 行第 1 字节 0x80 -> 盲文 dot1
                sv.stop()
                self.assertFalse(sv.running)

    def test_kill_stops_screen(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            emu = Emu(rom, exe=self.fake_exe, env=env, port=port,
                      workdir=str(TESTS_DIR), timeout=30)
            emu.start_screen(interval=0.05)
            emu.kill()
            self.assertFalse(emu.screen.running)


class TestScreenTUI(unittest.TestCase):
    """终端 TUI: 异步反复打印 + 不阻塞其他调用"""

    fake_exe = str(TESTS_DIR / "fake_emulator.sh")

    def test_showscreen_async(self):
        import io

        port = free_port()
        with tempfile.TemporaryDirectory() as tmp:
            rom = Path(tmp) / "fake.bin"
            rom.write_bytes(b"\x00" * 16)
            env = {"CEM_FAKE_PORT": str(port)}
            buf = io.StringIO()
            with Emu(rom, exe=self.fake_exe, env=env, port=port,
                     workdir=str(TESTS_DIR), timeout=30) as emu:
                tui = emu.showscreen(interval=0.05, out=buf)
                self.assertTrue(tui.running)
                # 等首帧打印
                self.assertTrue(emu.screen.wait_change(timeout=5))
                import time

                deadline = time.monotonic() + 5
                while "状态栏" not in buf.getvalue() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertIn("状态栏", buf.getvalue())
                # 画面变化 -> 自动重绘
                v0 = buf.getvalue()
                emu.write(offset=0xF800, byte="80 00 00 00")
                deadline = time.monotonic() + 5
                while buf.getvalue() == v0 and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertNotEqual(buf.getvalue(), v0)
                # TUI 运行期间 press 不被阻塞
                emu.press("1", interval=0)
                tui.stop()
                self.assertFalse(tui.running)
            self.assertFalse(emu.screen.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
