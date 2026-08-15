#!/usr/bin/env bash
# 假模拟器包装脚本: 忽略 Emu 传入的 model/paused 参数，启动假 MCP 服务器。
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${PYTHON:-python3}" "$DIR/fake_emulator.py"
