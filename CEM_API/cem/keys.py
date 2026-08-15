"""CEM 标准键码表 (kiko 编码)

CasioEmuMsvc / 原版 CEM 家族 (LBPHacker/CasioEmu -> CasioEmuMsvc) 使用
统一的 kiko 键码: ``code = (KO << 4) | KI``，即键盘矩阵输出行与输入列的
编码。这些取值在 ES PLUS / ClassWiz / fx-9860G 家族中保持一致。

以下常量取自已核实的两个独立模型配置:

* 原版 CEM ``models/fx570esplus/model.lua``
* CasioEmuX ``models/fx991cnx/model.lua`` (ClassWiz)

0xFF 是电源键 (POWER)，在部分模型配置里它也叫 "F4"。

按键名 (如 "AC/ON") 是与具体 model 目录里的 config.json 的 buttons 表
绑定的，运行时可通过 ``emu.buttons`` 查看、直接用名字调用 ``press``。
"""

from .exceptions import InvalidKeyError


class Key:
    # ---- 数字小键盘 ----
    KEY_1 = 0x00
    KEY_2 = 0x10
    KEY_3 = 0x20
    KEY_4 = 0x01
    KEY_5 = 0x11
    KEY_6 = 0x21
    KEY_7 = 0x02
    KEY_8 = 0x12
    KEY_9 = 0x22
    KEY_0 = 0x64
    KEY_DOT = 0x63       # '.'
    KEY_EXP = 0x62       # 'E' / EXP

    # ---- 运算键 ----
    KEY_ADD = 0x30       # '+' (原配置中以 SDL 名 '=' 记录)
    KEY_SUB = 0x40       # '-'
    KEY_MUL = 0x31       # '×'
    KEY_DIV = 0x41       # '÷'
    KEY_EXE = 0x60       # '='  EXE / Return
    KEY_ACON = 0x42      # AC/ON (原配置中以 SDL 名 'Space' 记录)
    KEY_DEL = 0x32       # DEL (原配置中以 SDL 名 'Backspace' 记录)

    # ---- 方向键 ----
    KEY_UP = 0x27
    KEY_DOWN = 0x36
    KEY_LEFT = 0x26
    KEY_RIGHT = 0x37

    # ---- F 键 / 电源 ----
    KEY_F1 = 0x07
    KEY_F2 = 0x17
    KEY_F3 = 0x47
    KEY_F4 = 0xFF       # 部分模型 (fx991cnx) 中 0xFF 名为 F4
    KEY_F5 = 0x06
    KEY_F6 = 0x16
    KEY_F7 = 0x46
    KEY_F8 = 0x56
    KEY_POWER = 0xFF

    # ---- fx-991CN X 通俗表示 (CWZ.N) ----
    # 来源: 用户提供的《fx-991CN X 键码矩阵》(document.tex)，
    # 16 位键码 = 0xKO:KI (KI=行扫描, KO=列返回)；换算为 kiko:
    #   kiko = (KO 列号 << 4) | KI 行号
    # 按键名取自 CWZ.N→ASCII 转换器 (index.html)。
    # 注: CNX 上 F1..F8 实际为 SHIFT/ALPHA/MENU/电源/OPTN/CALC/INT/X。
    KEY_SHIFT = 0x07     # 'q'
    KEY_ALPHA = 0x17     # 'Q'
    KEY_MENU = 0x47      # 't'
    KEY_OPTN = 0x06      # 'T'
    KEY_CALC = 0x16      # 'r'
    KEY_INT = 0x46       # 'y'
    KEY_X = 0x56         # '['
    KEY_FRAC = 0x05      # 'a'
    KEY_SQRT = 0x15      # 's'
    KEY_SQ = 0x25        # 'd' (x²)
    KEY_EXP = 0x35       # '^' (乘方)
    KEY_LOG = 0x45       # 'i'
    KEY_LN = 0x55        # 'h'
    KEY_NEGA = 0x04      # 'z' (负号)
    KEY_DMS = 0x14       # 'x'
    KEY_RECI = 0x24      # 'u' (倒数 x⁻¹)
    KEY_SIN = 0x34       # 'j'
    KEY_COS = 0x44       # 'k'
    KEY_TAN = 0x54       # 'l'
    KEY_STO = 0x03       # 'J'
    KEY_ENG = 0x13       # 'b'
    KEY_LPAREN = 0x23    # '('
    KEY_RPAREN = 0x33    # ')'
    KEY_S2D = 0x43       # 'n' (S↔D)
    KEY_MPLUS = 0x53     # 'm' (M+)
    KEY_X10 = 0x62       # 'K' (×10ˣ; 旧 config 中名为 'E')
    KEY_ANS = 0x61       # 'M'

    _NAME_TO_CODE = {}

    # 通俗表示 -> 码值（符号 / 别名，resolve 时大小写不敏感）
    # 别名取自 CWZ.N→ASCII 转换器 (index.html) 的 MAP 表
    _SPECIALS = {
        "M+": 0x53,
        "AC": 0x42, "AC/ON": 0x42, "ON": 0xFF, "POWER": 0xFF,
        "×": 0x31, "*": 0x31, "TIMES": 0x31, "CHENG": 0x31,
        "÷": 0x41, "/": 0x41, "CHU": 0x41,
        "+": 0x30, "PLUS": 0x30, "JIA": 0x30,
        "-": 0x40, "−": 0x40, "SUB": 0x40, "JIAN": 0x40,
        "=": 0x60,
        "^": 0x35, "(": 0x23, ")": 0x33,
        ".": 0x63, "DOT": 0x63,
        "10^X": 0x62, "10X": 0x62,
        # CWZ.N 别名: 与主名同键
        "JF": 0x46,      # int
        "FS": 0x05,      # frac
        "GH": 0x15,      # sqrt
        "PF": 0x25,      # sq
        "CF": 0x35,      # exp
        "FU": 0x04,      # nega
        "DFM": 0x14,     # dms
        "DS": 0x24,      # reci
    }

    @classmethod
    def _build(cls):
        if cls._NAME_TO_CODE:
            return
        for name in dir(cls):
            if not name.startswith("KEY_"):
                continue
            value = getattr(cls, name)
            if not isinstance(value, int):
                continue
            cls._NAME_TO_CODE.setdefault(name, value)

    @classmethod
    def resolve(cls, key):
        """把 int / 常量名 / 'KEY_X' / 'X' / 通俗表示 统一解析为 0-255 的 kiko 码

        通俗表示示例: "POWER" "sin" "SHIFT" "M+" "AC" "×" "(" 等，
        大小写不敏感。
        """
        cls._build()
        if isinstance(key, int):
            if not 0 <= key <= 255:
                raise InvalidKeyError(f"键码必须在 0-255 之间: {key!r}")
            return key
        if isinstance(key, str):
            name = key.strip()
            if not name:
                raise InvalidKeyError("键名为空")
            if name.lower().startswith("0x"):
                try:
                    value = int(name, 16)
                except ValueError as exc:
                    raise InvalidKeyError(f"无效的十六进制键码: {key!r}") from exc
                if not 0 <= value <= 255:
                    raise InvalidKeyError(f"键码必须在 0-255 之间: {key!r}")
                return value
            code = cls._NAME_TO_CODE.get(name)
            if code is None:
                upper = name.upper()
                code = cls._NAME_TO_CODE.get(upper)
            if code is None:
                code = cls._NAME_TO_CODE.get("KEY_" + name.upper())
            if code is None:
                code = cls._SPECIALS.get(name)
            if code is None:
                code = cls._SPECIALS.get(name.upper())
            if code is not None:
                return code
            raise InvalidKeyError(
                f"未知键名: {key!r}（可用 Key.KEY_* 常量、通俗表示如 "
                f"'POWER'/'sin'/'M+'，或 model 的键名）"
            )
        raise InvalidKeyError(f"键必须是 int 或 str，收到 {type(key).__name__}")

    @classmethod
    def name_of(cls, code):
        """返回码值对应的常量名（不存在时返回 None）"""
        cls._build()
        for name, value in cls._NAME_TO_CODE.items():
            if value == code:
                return name
        return None


# 兼容别名: resolve_key(x) == Key.resolve(x)
resolve_key = Key.resolve
