"""CasioEmuMsvc McpPlugin 的 Streamable HTTP MCP 客户端（纯标准库）"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .exceptions import McpError, ToolError

MCP_PROTOCOL_VERSION = "2025-11-25"


class McpClient:
    """对 http://127.0.0.1:3001/mcp 的极简 JSON-RPC 2.0 客户端。

    只依赖标准库 urllib。调用 ``tools/call`` 时返回工具的
    ``structuredContent``（若缺失则回退解析 content[0].text）。
    """

    def __init__(self, host="127.0.0.1", port=3001, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._next_id = 0
        self.session_id = None
        self.server_info = None

    # ------------------------------------------------------------------ #
    # 基础 HTTP
    # ------------------------------------------------------------------ #
    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    def _post(self, payload):
        """POST JSON-RPC 消息，返回 (http_status, headers, parsed_json)"""
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        request = urllib.request.Request(
            f"{self.base_url}/mcp", data=data, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", "replace")
                return response.status, response.headers, body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise McpError(f"MCP 服务器返回 HTTP {exc.code}: {body[:200]}") from exc
        except urllib.error.URLError as exc:
            raise McpError(f"无法连接 MCP 服务器 {self.base_url}: {exc.reason}") from exc
        except OSError as exc:
            raise McpError(f"MCP 通信失败: {exc}") from exc

    def _request(self, method, params=None):
        """发送一条带 id 的请求并返回响应 JSON 对象"""
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        status, headers, body = self._post(payload)
        if status == 202:
            raise McpError(f"MCP 服务器对 {method} 返回 202 (无响应体)")
        if not body:
            raise McpError(f"MCP 服务器对 {method} 返回空响应 (HTTP {status})")
        try:
            response = json.loads(body)
        except json.JSONDecodeError as exc:
            raise McpError(f"MCP 响应不是合法 JSON: {body[:200]!r}") from exc
        if not isinstance(response, dict):
            raise McpError(f"MCP 响应格式异常: {body[:200]!r}")
        if "error" in response and response["error"] is not None:
            error = response["error"]
            raise McpError(
                f"JSON-RPC 错误 {error.get('code')}: {error.get('message')}"
            )
        if "result" not in response:
            raise McpError(f"MCP 响应缺少 result: {body[:200]!r}")
        return response["result"]

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def health(self):
        """GET /health；不可达或非 200 时返回 None"""
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/health", timeout=2.0
            ) as response:
                if response.status != 200:
                    return None
                return json.loads(response.read().decode("utf-8", "replace"))
        except Exception:
            return None

    def wait_ready(self, timeout=60.0, interval=0.25):
        """轮询 /health 直到就绪；超时抛 McpError"""
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = self.health()
            if last is not None and last.get("status") == "ok":
                return last
            time.sleep(interval)
        raise McpError(f"MCP 服务器 {self.base_url} 在 {timeout:.0f}s 内未就绪")

    def initialize(self):
        """初始化会话，返回 MCP Session-Id 与服务器信息"""
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "cem-api", "version": "1.0.0"},
            },
        }
        status, headers, body = self._post(payload)
        try:
            response = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise McpError(f"initialize 响应异常: {body[:200]!r}") from exc
        if "error" in response and response["error"] is not None:
            error = response["error"]
            raise McpError(f"initialize 失败 {error.get('code')}: {error.get('message')}")
        session = headers.get("MCP-Session-Id")
        if session:
            self.session_id = session
        result = response.get("result", {})
        self.server_info = result.get("serverInfo")
        return session

    # ------------------------------------------------------------------ #
    # 工具调用
    # ------------------------------------------------------------------ #
    def call_tool(self, name, arguments=None):
        """调用 MCP 工具，返回 structuredContent（dict）"""
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        result = self._request("tools/call", params)
        if not isinstance(result, dict):
            raise McpError(f"工具 {name} 返回格式异常: {result!r}")

        if result.get("isError"):
            message = _extract_tool_message(result) or "未知工具错误"
            raise ToolError(message, tool=name)

        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        # 回退: content[0].text 是 JSON
        text = _extract_tool_message(result)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text}
        raise McpError(f"工具 {name} 返回内容为空: {result!r}")


def _extract_tool_message(result):
    """从 MCP ToolResult 中取出 content[0].text（可能为 JSON 字符串）"""
    content = result.get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            return item.get("text")
    return None
