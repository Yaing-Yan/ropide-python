#!/usr/bin/env python3
"""testing.py —— 演示 cem API 库的用法（手动运行，非测试）

流程: 启动模拟器 -> 电源键开机 -> 等待引导完成 -> 按键(通俗表示, 带间隔)
      -> 保持运行不退出。

运行: python testing.py [model目录或ROM] [--exe 路径]
      （按回车键关闭模拟器；或直接关掉模拟器窗口）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 非终端(stdout 被管道/IDE 捕获)时 print 会积压不显示，改成行缓冲
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

from cem import Emu, Key

DEFAULT_ROM = "/home/yanshangxuan/casioemu/models/fx991cnxfVirtual"
DEFAULT_EXE = "/home/yanshangxuan/casioemu/CasioEmuMsvc-mcp/CasioEmuMsvc"


def main():
    args = sys.argv[1:]
    rom = args[0] if args else DEFAULT_ROM
    exe = args[args.index("--exe") + 1] if "--exe" in args else DEFAULT_EXE

    print(f">> 启动模拟器: {exe}")
    print(f">> 加载模型: {rom}")

    # paused=False: CPU 自由运行（模拟器启动后即处于待机/关机状态）
    with Emu(rom, exe=exe, paused=False, timeout=40, headless=True) as emu:
        print(f"模型: {emu.status().get('model_name')}")
        print(f"可用键名: {sorted(emu.buttons)[:12]} ...")

        # ---- 1. 开机 ----
        print(">> 按下电源键 (0xFF) 开机...")
        try:
            input("   确认已看到模拟器窗口后按回车继续...")
        except EOFError:
            pass
        emu.showscreen(interval=0.15)

        emu.power_on(hold=1.0)

        # ---- 2. 等待引导完成（否则按键会被开机过程吞掉）----
        print(">> 等待系统引导完成（显存稳定）...")
        print("   引导完成" if emu.wait_boot() else "   [警告] 等待超时")

        # ---- 3. 按键（通俗表示：空格分隔的连续按键；开机后真实显示在屏幕上）----
        emu.press(
            "shift 9 3 = ac menu 2 shift menu 1 3 1 shift 8 down 2 7 = up left shift 8 down 2 1 left del left log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log log = ac left",
            interval=0.1,
        )
        time.sleep(5)
        emu.press("left right del", interval=0.1)
        time.sleep(2)
        emu.press("=")
        # ---- 4. 保持运行，不退出 ----
        print("\n模拟器运行中，可以看屏幕操作。")
        try:
            input("按回车键关闭模拟器...")
        except EOFError:
            print("(非交互模式) 等待模拟器退出...")
            while emu.running:
                time.sleep(1)

    print("模拟器已关闭")


if __name__ == "__main__":
    main()
