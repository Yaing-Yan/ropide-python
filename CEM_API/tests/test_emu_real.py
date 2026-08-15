"""真实模拟器端到端测试（可选）: 需要 CasioEmuMsvc + MCP 插件。

用法::

    CASIOEMU_EXE=/path/to/CasioEmuMsvc python -m unittest tests.test_emu_real -v
    CASIOEMU_MODEL=/path/to/model_dir   # 可选，默认 fx991cnx

注意: nX-U8 机型上 MCP 的 PC/寄存器读取的是未执行的 JIT CPU（上游插件
限制），因此本测试用显存(0xF800)与内存往返来验证，不用 PC。
"""

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cem import Emu, Key

PORT = 3001
MODEL_DIR = os.environ.get(
    "CASIOEMU_MODEL",
    "/home/yanshangxuan/casioemu/models/models/fx991cnx",
)


@unittest.skipUnless(
    os.environ.get("CASIOEMU_REAL") or os.environ.get("CASIOEMU_EXE"),
    "需要真实模拟器: 设置 CASIOEMU_REAL=1 或 CASIOEMU_EXE 后运行",
)
class TestRealEmulator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = os.environ.get("CASIOEMU_EXE")
        if not cls.exe:
            raise unittest.SkipTest("CASIOEMU_EXE 未设置")
        from cem.exceptions import PortBusyError

        try:
            cls.emu = Emu(MODEL_DIR, exe=cls.exe, port=PORT, paused=False, timeout=60)
        except PortBusyError:
            cls.emu = Emu(MODEL_DIR, exe=cls.exe, port=PORT, paused=False, attach=True)
        cls.emu.power_on(hold=1.0)
        cls.emu.wait_boot()

    @classmethod
    def tearDownClass(cls):
        if cls.emu and not cls.emu.attach:
            cls.emu.kill()

    def test_memory_roundtrip(self):
        self.emu.write(offset=0xE9E0, byte="11 45 14 19")
        self.assertEqual(self.emu.read(offset=0xE9E0, byte=4), "11 45 14 19")

    def test_press_keys(self):
        self.emu.press(Key.KEY_ACON)
        self.emu.press("1")
        self.emu.press(Key.KEY_ADD)
        self.emu.press("2")
        self.emu.key_down(Key.KEY_EXE)
        self.emu.key_up(Key.KEY_EXE)
        self.emu.release_all_keys()

    def test_press_changes_screen(self):
        """按键应改变屏幕显存内容（证明按键在开机后真实生效）"""
        before = self.emu.screen_buffer()
        for key in ("1", Key.KEY_ADD, "2"):
            self.emu.press(key)
            time.sleep(0.3)
        after = self.emu.screen_buffer()
        self.assertNotEqual(before, after)

    def test_wait_boot(self):
        self.assertTrue(self.emu.wait_boot(timeout=20))

    def test_register_tool_does_not_crash(self):
        # PC/寄存器工具在 nX-U8 上返回不可靠值，但调用本身不应报错
        self.emu.status()
        self.emu.registers()


if __name__ == "__main__":
    unittest.main(verbosity=2)
