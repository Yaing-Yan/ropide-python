"""模拟 CasioEmuMsvc 的假模拟器: 作为测试用 "exe" 被 Emu 启动。

行为与真实 McpPlugin 一致:
- GET  /health  -> {"status":"ok", ...}
- POST /mcp     -> JSON-RPC: initialize / tools/list / tools/call
- 工具: get_status, pause, resume, keyboard_code, read_memory, write_memory

用法: CEM_FAKE_PORT=<port> python fake_emulator.py
进程不退出，直到被终止 (kill)。
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("CEM_FAKE_PORT", "3001"))


class State:
    def __init__(self):
        self.memory = bytearray(0x100000)
        self.key_events = []
        self.paused = True
        self.pc = 0x0F0000
        self.env = {k: v for k, v in os.environ.items()
                    if k.startswith("SDL_") or k.startswith("CEM_")}


STATE = State()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body=b"", content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, json.dumps({
                "status": "ok",
                "server": "casioemu-mcp",
                "version": "0.2.0",
                "mcp_endpoint": f"http://127.0.0.1:{PORT}/mcp",
            }).encode())
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/mcp":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length))
        if "id" not in request:
            self._send(202, b"")
            return
        response = self._handle(request)
        if request.get("method") == "initialize":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("MCP-Session-Id", "fake-session-1234")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        else:
            self._send(200, response)

    def _handle(self, request):
        method = request.get("method")
        rid = request.get("id")
        if method == "initialize":
            return json.dumps({
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "casioemu-mcp-fake", "version": "0.0.1"},
                },
            }).encode()
        if method == "tools/list":
            return json.dumps({
                "jsonrpc": "2.0", "id": rid,
                "result": {"tools": [{"name": "get_status"}]},
            }).encode()
        if method == "tools/call":
            params = request.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            return self._call_tool(rid, name, args)
        return json.dumps({
            "jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "Method not found"},
        }).encode()

    def _tool_result(self, rid, value, is_error=False):
        result = {
            "content": [{"type": "text", "text": json.dumps(value)}],
            "structuredContent": value,
        }
        if is_error:
            result["isError"] = True
        return json.dumps({"jsonrpc": "2.0", "id": rid, "result": result}).encode()

    def _call_tool(self, rid, name, args):
        if name == "get_status":
            return self._tool_result(rid, {
                "model_name": "FAKE-570ES-PLUS",
                "rom_path": "rom.bin",
                "paused": STATE.paused,
                "program_counter": STATE.pc,
                "cycles_per_second": 8000000,
            })
        if name == "pause":
            STATE.paused = True
            return self._tool_result(rid, {"success": True, "paused": True})
        if name == "resume":
            STATE.paused = False
            return self._tool_result(rid, {"success": True, "paused": False})
        if name == "keyboard_code":
            STATE.key_events.append(
                {"code": args["code"], "pressed": args["pressed"]}
            )
            return self._tool_result(rid, {"success": True})
        if name == "get_key_events":
            return self._tool_result(rid, {"events": list(STATE.key_events)})
        if name == "get_env":
            return self._tool_result(rid, {"env": STATE.env})
        if name == "read_memory":
            address = args["address"]
            size = args["size"]
            raw = STATE.memory[address:address + size]
            return self._tool_result(rid, {"address": address, "bytes": list(raw)})
        if name == "write_memory":
            address = args["address"]
            for i, value in enumerate(args["bytes"]):
                STATE.memory[address + i] = value
            return self._tool_result(rid, {
                "success": True, "written": len(args["bytes"])
            })
        if name == "list_registers":
            return self._tool_result(rid, {"registers": [
                {"name": "r0", "value": 0x12, "hex": "0x12", "bit_width": 8},
            ]})
        if name == "read_register":
            return self._tool_result(rid, {"name": args["name"], "value": 0x12, "bit_width": 8})
        if name == "keyboard_key":
            return self._tool_result(rid, {"success": True})
        return self._tool_result(
            rid, {"error": f"Unknown tool: {name}"}, is_error=True
        )


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"fake emulator ready on {PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
