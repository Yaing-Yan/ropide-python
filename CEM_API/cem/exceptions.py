"""CEM-API 异常定义"""


class CemError(Exception):
    """所有 CEM-API 异常的基类"""


class McpError(CemError):
    """与 MCP 服务器通信失败（网络 / JSON-RPC 层）"""


class ToolError(McpError):
    """MCP 工具调用被模拟器拒绝"""

    def __init__(self, message, tool=None):
        super().__init__(message)
        self.tool = tool


class EmulatorNotFound(CemError):
    """找不到 CasioEmuMsvc 可执行文件"""


class EmulatorStartFailed(CemError):
    """模拟器启动失败（进程退出或 MCP 服务未就绪）"""


class EmulatorNotRunning(CemError):
    """模拟器进程已退出"""


class InvalidKeyError(CemError):
    """无效的键码 / 键名"""


class PortBusyError(CemError):
    """MCP 端口已被其他进程占用"""


class ModelConfigError(CemError):
    """model 目录 / config.json 无效"""
