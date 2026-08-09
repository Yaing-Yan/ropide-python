# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
import argparse, os, sys
from .models import MODELS, ModelConfig
from .emulator import Emulator
from . import tui


def main():
    p = argparse.ArgumentParser("u8emu", description="nX-U8/100 TUI emulator (Python port of CasioEmuMsvc)")
    p.add_argument("rom", nargs="?", help="ROM 二进制")
    p.add_argument("-m", "--model", default="generic", choices=list(MODELS))
    p.add_argument("--config", help="机型 JSON 配置（可由 CasioEmu 的 config.lua 转换而来）")
    p.add_argument("--style", default="braille", choices=["braille", "half", "ascii"])
    p.add_argument("--hscale", type=int, default=1)
    p.add_argument("--vscale", type=int, default=1, help="纵向 N 像素合成 1 点；=2 时一个字符=2x8 像素")
    p.add_argument("--invert", action="store_true")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--speed", type=float, default=1.0, help="相对实机速度倍率")
    p.add_argument("--hold", type=float, default=0.05,
                   help="按键保持时长(秒)。默认按【模拟时间】计(与宿主速度无关)；"
                        "25~50ms 即足够 ROM 扫描+防抖（CasioEmuMsvc 最短 25ms），"
                        "过长会触发固件长按连发")
    p.add_argument("--hold-unit", choices=["emu", "wall"], default="emu",
                   help="emu=按模拟周期计时(推荐)；wall=按真实时间")
    p.add_argument("--gap", type=float, default=0.05,
                   help="连击时两键之间的间隔(秒, 模拟时间), 默认 0.05")
    p.add_argument("--keylog", action="store_true", help="启动即开启键盘事件日志")
    p.add_argument("--plugin", action="append", default=[])
    p.add_argument("--plugin-dir",
                   default=os.path.expanduser("~/.config/u8emu/plugins"))
    p.add_argument("--rpc", type=int, default=0, help="开启 JSON-RPC 端口")
    p.add_argument("--strict", action="store_true", help="遇未知指令抛异常")
    p.add_argument("--trace-sfr", action="store_true")
    p.add_argument("--headless", action="store_true", help="无 TUI，仅 RPC")
    p.add_argument("--qquit", action="store_true", default=True)
    a = p.parse_args()

    cfg = ModelConfig.load(a.config) if a.config else MODELS[a.model]
    emu = Emulator(cfg, a.rom)
    emu.cpu.strict = a.strict
    emu.sfr.trace = a.trace_sfr

    if a.headless:
        from .plugin import EmuAPI, PluginManager, RpcServer
        import threading, time
        api = EmuAPI(emu); pm = PluginManager(api)
        pm.load_dir(a.plugin_dir)
        for f in a.plugin: pm.load_file(f)
        lock = threading.RLock()
        if a.rpc: RpcServer(api, port=a.rpc, lock=lock).start()
        try:
            while True:
                with lock:
                    emu.run(int(cfg.freq / 60)); api._tick_frame()
                time.sleep(1 / 60)
        except KeyboardInterrupt:
            pass
        return
    tui.start(emu, a)


if __name__ == "__main__":
    main()
