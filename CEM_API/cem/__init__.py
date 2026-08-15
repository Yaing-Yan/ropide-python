"""CEM-API: CasioEmuMsvc Python 控制库

基于 CasioEmuMsvc 的 MCP 调试插件 (McpPlugin) 提供的
Streamable HTTP JSON-RPC 接口 (127.0.0.1:3001/mcp) 封装而成。

用法::

    from cem import Emu, Key

    emu = Emu("fx570esplus")          # 传入 model 目录或裸 ROM 文件
    emu.press(Key.KEY_ACON)           # 按下 AC/ON
    emu.write(offset=0xE9E0, byte="11 45 14 19")
    print(emu.read(offset=0xE9E0, byte=4))   # -> "11 45 14 19"
    emu.kill()
"""

from .exceptions import (
    CemError,
    EmulatorNotFound,
    EmulatorNotRunning,
    EmulatorStartFailed,
    InvalidKeyError,
    McpError,
    ModelConfigError,
    PortBusyError,
    ToolError,
)
from .emu import Emu
from .keys import Key
from .screen import ScreenTUI, ScreenView, render_braille, render_status

__version__ = "1.0.0"

__all__ = [
    "Emu",
    "Key",
    "ScreenView",
    "ScreenTUI",
    "render_braille",
    "render_status",
    "CemError",
    "McpError",
    "ToolError",
    "EmulatorNotFound",
    "EmulatorStartFailed",
    "EmulatorNotRunning",
    "InvalidKeyError",
    "PortBusyError",
    "ModelConfigError",
    "__version__",
]
