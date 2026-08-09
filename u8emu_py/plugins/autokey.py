# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""自动按键脚本（宏）：启动后顺序敲 1 + 2 ="""


def register(api):
    api.type_keys(["1", "+", "2", "="], hold_ms=1500, gap_ms=300)
    api.log("autokey: type_keys(1 + 2 =)")
