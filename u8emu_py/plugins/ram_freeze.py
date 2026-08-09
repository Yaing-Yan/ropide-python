# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""演示：RAM 访问 + 即时覆写 + 自定义面板 + 自定义命令"""


def register(api):
    STATE = {"addr": 0x8000, "hits": 0}

    api.freeze(0x8123, 0x42)                    # 锁死一个字节

    def on_w(addr, v):
        STATE["hits"] += 1
    api.on_write(0x8000, on_w)                  # 写监视

    def on_pc(cpu):
        api.log(f"hit 0:1234, R0={cpu.r[0]:02X}")
    api.on_exec(0, 0x1234, on_pc)               # 执行断点回调

    def panel(w, h):
        return [f"watch 0x8000 hits: {STATE['hits']}",
                f"R0 = {api.get_reg('r0'):02X}",
                "frozen: " + ", ".join(f"{a:05X}" for a in api.frozen_list())]
    api.add_panel("MYPLUG", panel)

    def cmd_dump(addr, n="32"):
        data = api.read_bytes(int(addr, 16), int(n))
        api.log(data.hex(" "))
    api.register_command("dump", cmd_dump, "dump <hexaddr> [len]")

    api.log("ram_freeze plugin ready")
