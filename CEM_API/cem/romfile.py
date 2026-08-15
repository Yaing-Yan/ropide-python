"""model 目录构建: 裸 ROM 文件 -> CasioEmuMsvc 可加载的 model 目录

CasioEmuMsvc 通过命令行 ``CasioEmuMsvc.exe <model_dir> paused=1`` 加载
模型。model 目录至少包含:

* ``config.json`` —— 模型描述 (硬件 ID、rom/flash/interface 路径、按钮表)
* ``rom.bin`` —— 固件镜像
* ``interface.png`` —— 计算器外观图 (GUI 渲染需要，可空白)

config.json 字段要求来自 CasioEmuMsvc 源码 ``ModelConfig.cpp`` 的
``RequireBaseModelFields`` / ``RequireSpriteModelFields``。
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

from .exceptions import ModelConfigError

MODEL_CONFIG_JSON = "config.json"
MODEL_CONFIG_BIN = "config.bin"

# --------------------------------------------------------------------- #
# 默认按钮表 (取自原版 CEM models/fx570esplus/model.lua 的布局与码值)
# --------------------------------------------------------------------- #
DEFAULT_INTERFACE_SIZE = (410, 810)


def _button(kiko, keyname, rect):
    x, y, w, h = rect
    return {
        "kiko": kiko,
        "keyname": keyname,
        "rect": {"x": x, "y": y, "w": w, "h": h},
    }


def default_buttons():
    """ES PLUS / ClassWiz 家族通用的按钮表 (kiko 码 + 键名)"""
    buttons = []
    # 数字小键盘 5x4
    grid = {
        (0, 0): (0x02, "7"), (1, 0): (0x12, "8"), (2, 0): (0x22, "9"),
        (3, 0): (0x32, "DEL"), (4, 0): (0x42, "AC/ON"),
        (0, 1): (0x01, "4"), (1, 1): (0x11, "5"), (2, 1): (0x21, "6"),
        (3, 1): (0x31, "x"), (4, 1): (0x41, "div"),
        (0, 2): (0x00, "1"), (1, 2): (0x10, "2"), (2, 2): (0x20, "3"),
        (3, 2): (0x30, "+"), (4, 2): (0x40, "-"),
        (0, 3): (0x64, "0"), (1, 3): (0x63, "."), (2, 3): (0x62, "EXP"),
        (3, 3): (0x61, ""), (4, 3): (0x60, "EXE"),
    }
    for (col, row), (code, name) in grid.items():
        buttons.append(_button(code, name, (46 + col * 65, 544 + row * 57, 58, 41)))
    # F 键 / 方向键
    for code, name, rect in [
        (0x07, "F1", (44, 290, 49, 39)),
        (0xFF, "POWER", (317, 290, 49, 39)),
        (0x17, "F2", (100, 298, 48, 38)),
        (0x47, "F3", (262, 298, 48, 38)),
        (0x06, "F5", (40, 359, 48, 31)),
        (0x16, "F6", (94, 359, 48, 31)),
        (0x46, "F7", (268, 359, 48, 31)),
        (0x56, "F8", (322, 359, 48, 31)),
        (0x26, "Left", (155, 319, 33, 32)),
        (0x37, "Right", (222, 319, 33, 32)),
        (0x27, "Up", (188, 289, 34, 30)),
        (0x36, "Down", (188, 351, 34, 30)),
    ]:
        buttons.append(_button(code, name, rect))
    return buttons


# --------------------------------------------------------------------- #
# 最小 PNG 写入 (纯标准库)
# --------------------------------------------------------------------- #
def _png_chunk(tag, data):
    chunk = tag + data
    return (
        struct.pack(">I", len(data))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    )


def write_blank_png(path, width, height, color=(255, 255, 255, 255)):
    """生成纯色 RGBA PNG（供 interface.png 使用）"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    scanline = b"\x00" + bytes(color) * width
    raw = scanline * height
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)
    return path


# --------------------------------------------------------------------- #
# config.json 读写
# --------------------------------------------------------------------- #
def default_config(
    rom_path="rom.bin",
    flash_path="",
    interface_path="interface.png",
    model_name="CEM-API Model",
    hardware_id=3,
    buttons=None,
    interface_size=DEFAULT_INTERFACE_SIZE,
    csr_mask=0x0001,
    real_hardware=False,
    pd_value=0,
    enable_new_screen=False,
    is_sample_rom=False,
    legacy_ko=False,
    u16_mode=False,
    ml620_mirroring=False,
    large_model=False,
    ink_color=(30, 52, 90),
    **extra,
):
    """生成 CasioEmuMsvc 要求的 config.json 内容"""
    width, height = interface_size
    config = {
        "format": "CasioEmuMsvc.ModelInfo",
        "version": 1,
        "model_name": model_name,
        "hardware_id": hardware_id,
        "csr_mask": csr_mask,
        "real_hardware": real_hardware,
        "pd_value": pd_value,
        "interface_path": interface_path,
        "rom_path": rom_path,
        "flash_path": flash_path,
        "ink_color": {"r": ink_color[0], "g": ink_color[1], "b": ink_color[2]},
        "enable_new_screen": enable_new_screen,
        "is_sample_rom": is_sample_rom,
        "legacy_ko": legacy_ko,
        "u16_mode": u16_mode,
        "large_model": large_model,
        "ml620_mirroring": ml620_mirroring,
        "buttons": buttons if buttons is not None else default_buttons(),
        "sprites": {
            "rsd_interface": {
                "src": {"x": 0, "y": 0, "w": width, "h": height},
                "dest": {"x": 0, "y": 0, "w": width, "h": height},
            }
        },
    }
    config.update(extra)
    return config


def is_model_dir(path):
    """目录内存在 config.json 或 config.bin 即视为 model 目录"""
    path = Path(path)
    return path.is_dir() and (
        (path / MODEL_CONFIG_JSON).is_file() or (path / MODEL_CONFIG_BIN).is_file()
    )


def load_config(model_dir):
    """读取 model 目录的 config.json（不存在时返回 None）"""
    path = Path(model_dir) / MODEL_CONFIG_JSON
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelConfigError(f"config.json 解析失败 {path}: {exc}") from exc


# --------------------------------------------------------------------- #
# config.bin (ModelInfo 二进制 v52) 解析
# 格式来自 CasioEmuMsvc 源码 ModelInfo.h 的 Binary 序列化:
#   标量 = 原始内存 (x86 小端); std::string/vector/map = u64 长度 + 元素;
#   bool = 1 字节
# --------------------------------------------------------------------- #
class _BinReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def _take(self, n):
        if self.pos + n > len(self.data):
            raise ModelConfigError("config.bin 数据不完整 (意外 EOF)")
        value = self.data[self.pos:self.pos + n]
        self.pos += n
        return value

    def u64(self):
        return struct.unpack("<Q", self._take(8))[0]

    def u16(self):
        return struct.unpack("<H", self._take(2))[0]

    def u8(self):
        return self._take(1)[0]

    def i32(self):
        return struct.unpack("<i", self._take(4))[0]

    def f64(self):
        return struct.unpack("<d", self._take(8))[0]

    def boolean(self):
        return self._take(1)[0] != 0

    def string(self):
        length = self.u64()
        if length > 1 << 30:
            raise ModelConfigError("config.bin 字符串长度异常")
        return self._take(length).decode("utf-8", "replace")

    def rect(self):
        return {"x": self.i32(), "y": self.i32(), "w": self.i32(), "h": self.i32()}

    def buttons(self):
        count = self.u64()
        result = []
        for _ in range(count):
            rect = self.rect()
            kiko = self.i32()
            keyname = self.string()
            result.append({"kiko": kiko, "keyname": keyname, "rect": rect})
        return result

    def skip_string_map(self):
        count = self.u64()
        for _ in range(count):
            self.string()
            self.string()


def parse_config_bin(model_dir):
    """解析 config.bin，返回 {keyname: kiko} 按钮表（解析失败抛 ModelConfigError）"""
    path = Path(model_dir) / MODEL_CONFIG_BIN
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ModelConfigError(f"无法读取 {path}: {exc}") from exc
    reader = _BinReader(data)
    header = reader.string()          # "\n\nnx-U16/U8 Emulator Configuration file v52..."
    if "Configuration file" not in header and "nx-U" not in header:
        raise ModelConfigError(f"config.bin 头部不识别: {header[:60]!r}")
    reader.u16()                      # csr_mask
    reader.u16()                      # hardware_id
    reader.boolean()                  # real_hardware
    reader.u8()                       # pd_value
    buttons = reader.buttons()        # buttons
    # 其余字段跳过（sprites / ink_color / 各路径 / extra / svg 等）
    skip = reader
    count = skip.u64()
    for _ in range(count):            # sprites: map<string, SpriteInfo(2 rect)>
        skip.string()
        skip.rect()
        skip.rect()
    for _ in range(3):                # ink_color (3 x i32)
        skip.i32()
    for _ in range(4):                # interface/rom/flash_path, model_name
        skip.string()
    return {b["keyname"]: b["kiko"] for b in buttons if b["keyname"]}


def load_buttons(model_dir):
    """返回 {键名: kiko码}，供 press() 按键名调用。

    优先解析 config.json 的 buttons 数组；只有 config.bin 时解析二进制格式
    （ModelInfo v52）。
    """
    config = load_config(model_dir)
    if config:
        result = {}
        for button in config.get("buttons", []) or []:
            name = button.get("keyname")
            kiko = button.get("kiko")
            if name and kiko is not None:
                result.setdefault(str(name), int(kiko))
        return result
    bin_path = Path(model_dir) / MODEL_CONFIG_BIN
    if bin_path.is_file():
        return parse_config_bin(model_dir)
    return {}


def make_model_dir(
    rom_file,
    dest_dir=None,
    *,
    model_name=None,
    hardware_id=3,
    flash_file=None,
    interface_file=None,
    interface_size=DEFAULT_INTERFACE_SIZE,
    buttons=None,
    keep_rom_name=True,
    **config_extra,
):
    """把裸 ROM 文件打包成 CasioEmuMsvc 可加载的 model 目录。

    :param rom_file: ROM 固件文件路径
    :param dest_dir: 输出目录；默认 ~/.cache/cem-api/models/<rom-sha1>/
    :param model_name: 模型名，默认取 ROM 文件名
    :param hardware_id: CasioEmuMsvc HardwareId (3=ES PLUS, 4=ClassWiz,
        5=ClassWiz II, 6=fx-5800P, 8=Solarn II)
    :param flash_file: 可选的 flash 镜像
    :param interface_file: 可选的外观图（默认生成空白 PNG）
    :param buttons: 按钮表，默认使用标准 ES PLUS/ClassWiz 布局
    :return: 生成的 model 目录 Path
    """
    rom_file = Path(rom_file)
    if not rom_file.is_file():
        raise ModelConfigError(f"ROM 文件不存在: {rom_file}")

    if dest_dir is None:
        sha = hashlib.sha1(rom_file.read_bytes()).hexdigest()[:16]
        dest_dir = Path.home() / ".cache" / "cem-api" / "models" / f"{sha}-{rom_file.stem}"
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    rom_dest = dest_dir / "rom.bin"
    if not rom_dest.exists() or rom_dest.stat().st_size != rom_file.stat().st_size:
        rom_dest.write_bytes(rom_file.read_bytes())

    flash_path = ""
    if flash_file:
        flash_dest = dest_dir / "flash.bin"
        flash_dest.write_bytes(Path(flash_file).read_bytes())
        flash_path = "flash.bin"

    interface_path = "interface.png"
    if interface_file:
        interface_dest = dest_dir / interface_path
        interface_dest.write_bytes(Path(interface_file).read_bytes())
    else:
        write_blank_png(dest_dir / interface_path, *interface_size)

    if model_name is None:
        model_name = rom_file.stem.replace("_", "-")

    config = default_config(
        rom_path="rom.bin",
        flash_path=flash_path,
        interface_path=interface_path,
        model_name=model_name,
        hardware_id=hardware_id,
        buttons=buttons if buttons is not None else default_buttons(),
        interface_size=interface_size,
        **config_extra,
    )
    (dest_dir / MODEL_CONFIG_JSON).write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return dest_dir
