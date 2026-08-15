#!/usr/bin/env python3
"""CEM-API 示例: 启动模拟器 -> 电源键开机 -> 等待引导 -> 注入内存 -> 按键 -> 关闭

用法::

    python examples/demo.py [model_dir_or_rom] [--exe 路径]

不带参数时使用当前目录下的 model 目录或 CASIOEMU_EXE 环境变量。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cem import Emu, Key

DEMO_OFFSET = 0xE9E0


def main():
    args = sys.argv[1:]
    rom = args[0] if args else None
    exe = None
    if "--exe" in args:
        exe = args[args.index("--exe") + 1]

    if rom is None:
        for candidate in ("models/fx570esplus_emu", "models"):
            if Path(candidate).is_dir():
                rom = candidate
                break
    if rom is None:
        print("请指定 model 目录或 ROM 文件，例如: python examples/demo.py models/fx570esplus_emu")
        sys.exit(1)

    # paused=False: CPU 自由运行（不传 paused 参数——上游行为是只要参数存在就会暂停）
    with Emu(rom, exe=exe, paused=False) as emu:
        print(f"模型: {emu.status().get('model_name')}")
        print(f"可用键名: {sorted(emu.buttons)[:12]} ...")

        # 1. 开机 + 等待引导完成（用显存内容判断，PC/寄存器在 nX-U8 上不可靠）
        print(">> 按下电源键 (0xFF) 开机...")
        emu.power_on(hold=1.0)
        print(">> 等待系统引导完成...")
        print("   引导完成" if emu.wait_boot() else "   [警告] 等待超时")

        # 2. 内存写入 + 读取（核心 API）
        emu.write(offset=DEMO_OFFSET, byte="11 45 14 19")
        data = emu.read(offset=DEMO_OFFSET, byte=4)
        print(f"read(0x{DEMO_OFFSET:X}, 4) -> {data!r}")
        assert data == "11 45 14 19"

        # 3. 按键（带间隔，开机后输入会显示在屏幕上）
        for key in ("1", Key.KEY_ADD, "2", Key.KEY_EXE):
            emu.press(key)
            time.sleep(0.4)

        # 4. 方向键 / 功能键
        for key in (Key.KEY_UP, Key.KEY_DOWN, Key.KEY_LEFT, Key.KEY_RIGHT, Key.KEY_F1):
            emu.press(key)
            time.sleep(0.3)

        # 5. 截取屏幕内容（显存 0xF800，可用于判断界面状态）
        buf = emu.screen_buffer()
        print(f"屏幕显存: {len(buf)} 字节, 非零 {sum(1 for b in buf if b)}")

        # 保持运行，按回车关闭
        try:
            input("模拟器运行中，按回车关闭...")
        except EOFError:
            while emu.running:
                time.sleep(1)

    # with 语句退出时自动 kill()
    print("模拟器已关闭")


if __name__ == "__main__":
    main()
