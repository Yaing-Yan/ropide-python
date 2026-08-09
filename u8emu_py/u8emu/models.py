# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
import json
from dataclasses import dataclass, field, asdict


@dataclass
class ModelConfig:
    name: str = "generic-u8"
    rom_size: int = 0x100000
    real_hardware: bool = True
    # 数据空间 ROM 映射: (data_base, rom_base, size)
    rom_segments: list = field(default_factory=lambda: [(0x00000, 0x00000, 0x8000)])
    ram: tuple = (0x08000, 0x1000)
    sfr_base: int = 0xF000
    # LCD
    lcd_base: int = 0xF800
    lcd_w: int = 96
    lcd_h: int = 31
    lcd_stride: int = 16
    lcd_row_skip: int = 1        # 像素行从 buffer 第 N 行开始（第 0 行=状态符号）
    lcd_disp_bytes: int = 12     # 每行可写字节数（ES PLUS=12, ClassWiz=24）
    lcd_layout: str = "row_msb"  # row_msb | row_lsb | page
    # 中断
    freq: int = 2_097_152        # CLASSWIZ = 2MHz；ES_PLUS = 128K
    # 键盘矩阵 name -> (ko_bit_idx, ki_bit_idx)；POWER 特殊
    keys: dict = field(default_factory=dict)
    # 终端按键 -> 键名
    bindings: dict = field(default_factory=dict)

    # ---- 键盘参数 ----
    ko_count: int = 7                 # KO 线数（决定合法键码上界 0x67）
    ki_count: int = 8                 # KI 线数
    power_key: str = "POWER"          # 该键名映射到特殊码 0xFF
    ki_vector: int = 0x000A           # 键盘中断向量（= idx5*2，实测）
    ki_active_low: bool = False       # KI 读回低有效（fx-991CN X 为 True）
    ki_all_when_ko_zero: bool = True  # KO 全 0 时返回任意键按下（待机检测）
    keylog_size: int = 512

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        if "ram" in d:
            d["ram"] = tuple(d["ram"])
        if "rom_segments" in d:
            d["rom_segments"] = [tuple(x) for x in d["rom_segments"]]
        if "keys" in d:
            d["keys"] = {k: tuple(v) for k, v in d["keys"].items()}
        return ModelConfig(**d)

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


# ---- fx-991CN X 键盘矩阵（实测 keylog：KI位 × KO位，低有效）----
# 键名 = ROM 实测 ID；括号里是上游 model.lua 键码 (ko<<4|ki) 的对应位置
_CNX_KEYS = {
    # KI 01 行
    "1": (0, 0), "2": (1, 0), "3": (2, 0), "+": (3, 0),
    "p": (4, 0), "=": (6, 0),
    # KI 02 行
    "4": (0, 1), "5": (1, 1), "6": (2, 1), "O": (3, 1),
    "P": (4, 1), "M": (6, 1),
    # KI 04 行
    "7": (0, 2), "8": (1, 2), "9": (2, 2), "o": (3, 2),
    "C": (4, 2), "K": (6, 2),
    # KI 08 行
    "J": (0, 3), "b": (1, 3), "(": (2, 3), ")": (3, 3),
    "n": (4, 3), "m": (5, 3), ".": (6, 3),
    # KI 10 行
    "z": (0, 4), "x": (1, 4), "u": (2, 4), "j": (3, 4),
    "k": (4, 4), "l": (5, 4), "0": (6, 4),
    # KI 20 行
    "a": (0, 5), "s": (1, 5), "d": (2, 5), "^": (3, 5),
    "i": (4, 5), "h": (5, 5),
    # KI 40 行
    "T": (0, 6), "r": (1, 6), "!": (2, 6), "R": (3, 6),
    "y": (4, 6), "[": (5, 6),
    # KI 80 行
    "q": (0, 7), "Q": (1, 7), "E": (2, 7), "$": (3, 7),
    "t": (4, 7),
    # 特殊键（0xFF，不在矩阵内）
    "POWER": (7, 7),
}

_CNX_BINDINGS = {
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
    "+": "+", "-": "p",          # 减号键实测 ID = p
    "*": "O", "/": "P",          # × ÷ 键实测 ID = O / P
    ".": ".", "(": "(", ")": ")",
    "=": "=", "\n": "=",         # EXE 键实测 ID = "="（01,40）
    " ": "C",                    # AC = C
    "S": "q", "A": "Q", "M": "t",  # SHIFT / ALPHA / MENU（大写保留）
    "s": "q",                    # SHIFT = s
    "a": "Q",                    # ALPHA = a
    "c": "C",                    # AC = c
    "`": "r",                    # CALC = `
    "p": "POWER",                # 开关(ON) = p
    "o": "T",                    # OPTN（F5 位）
}

# 键名（CWZ.N 字符/ASCII 表示）→ 通俗表示（按键面标注）
_CNX_NAMES = {
    "q": "SHIFT", "Q": "ALPHA", "t": "MENU", "|": "ON",
    "E": "▲Up", "R": "▼Down", "!": "◀Left", "$": "▶Right",
    "T": "OPTN", "r": "CALC", "y": "INT", "[": "X",
    "a": "FRAC", "s": "SQRT", "d": "SQ", "^": "EXP",
    "i": "LOG", "h": "LN", "z": "NEG", "x": "DMS",
    "u": "RECI", "j": "SIN", "k": "COS", "l": "TAN",
    "J": "STO", "b": "ENG", "n": "S2D", "m": "M+",
    "o": "DEL", "C": "AC", "O": "TIMES", "P": "DIV",
    "+": "PLUS", "p": "SUB", ".": "DOT", "K": "X10",
    "M": "ANS", "=": "=",
}

# 通俗名（小写，大小写不敏感）→ 键名，用于 :optn / :key 等命令
_CNX_COMMON = {
    "shift": "q", "alpha": "Q", "menu": "t", "on": "POWER",
    "power": "POWER", "up": "E", "down": "R", "left": "!", "right": "$",
    "optn": "T", "calc": "r",
    "int": "y", "jf": "y", "xv": "[",
    "frac": "a", "fs": "a", "sqrt": "s", "gh": "s",
    "sq": "d", "pf": "d", "exp": "^", "cf": "^",
    "log": "i", "ln": "h", "nega": "z", "fu": "z",
    "dms": "x", "dfm": "x", "reci": "u", "ds": "u",
    "sin": "j", "cos": "k", "tan": "l",
    "sto": "J", "eng": "b",
    "s2d": "n", "m+": "m",
    "del": "o", "ac": "C",
    "times": "O", "cheng": "O", "div": "P", "chu": "P",
    "plus": "+", "jia": "+", "sub": "p", "jian": "p",
    "x10": "K", "ans": "M", "exe": "=",
}

# 简易占位矩阵（fx-991ES PLUS 等未适配机型）
_ESP_KEYS = {f"K{ko}{ki}": (ko, ki) for ko in range(8) for ki in range(8)}
_DEFAULT_BINDINGS = {
    "0": "K00", "1": "K01", "2": "K02", "3": "K03",
    "4": "K04", "5": "K05", "6": "K06", "7": "K07",
    "8": "K10", "9": "K11", "+": "K12", "-": "K13",
    "*": "K14", "/": "K15", "\n": "K16", ".": "K17",
    "\x1b": "K20",
}

MODELS = {
    "generic": ModelConfig(keys=_ESP_KEYS, bindings=_DEFAULT_BINDINGS),
    "fx991esplus": ModelConfig(
        name="fx-991ES PLUS", freq=128 * 1024,
        rom_segments=[(0x00000, 0x00000, 0x08000),
                      (0x10000, 0x10000, 0x10000),
                      (0x80000, 0x00000, 0x10000)],
        ram=(0x08000, 0x0E00), lcd_w=96, lcd_h=31, lcd_stride=16,
        lcd_row_skip=1, lcd_disp_bytes=12,
        keys=_ESP_KEYS, bindings=_DEFAULT_BINDINGS),
    "fx991cnx": ModelConfig(
        name="fx-991CN X", freq=2_097_152,
        rom_segments=[(0x00000, 0x00000, 0x0D000),
                      (0x10000, 0x10000, 0x10000),
                      (0x20000, 0x20000, 0x10000),
                      (0x30000, 0x30000, 0x10000),
                      (0x50000, 0x00000, 0x10000)],
        ram=(0x0D000, 0x2000), lcd_w=192, lcd_h=63, lcd_stride=32,
        lcd_row_skip=1, lcd_disp_bytes=24,
        ki_active_low=True,
        keys=_CNX_KEYS, bindings=_CNX_BINDINGS,
),
    "fx991cnxf": ModelConfig(
        name="fx-991CN X VerF", freq=2_097_152,
        rom_segments=[(0x00000, 0x00000, 0x0D000),
                      (0x10000, 0x10000, 0x10000),
                      (0x20000, 0x20000, 0x10000),
                      (0x30000, 0x30000, 0x10000),
                      (0x50000, 0x00000, 0x10000)],
        ram=(0x0D000, 0x2000), lcd_w=192, lcd_h=63, lcd_stride=32,
        lcd_row_skip=1, lcd_disp_bytes=24,
        ki_active_low=True,
        keys=_CNX_KEYS, bindings=_CNX_BINDINGS,
),
}
