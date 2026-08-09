#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# u8emu-py — derived from CasioEmuMsvc (GPL-3.0)
"""从 CasioEmuMsvc 的 Instructions.cpp（或 Lua 编码表）重新生成指令表。

上游编码表是权威来源（本仓库 isa.py 里标了 # VERIFY 的项都需要它来校正）。
解析器是"宽容式"的，不依赖上游的确切排版，支持两种行内顺序：

    OP_xxx, 0xMMMM, 0xCCCC        # 处理器名在前
    0xMMMM, 0xCCCC, OP_xxx        # 处理器名在后（允许 &CPU:: 前缀）

掩码/编码判定规则：由于 match 恒为 mask 的子集，按 set-bit 数判定——
位数多的是掩码（相等取前者）。行内若带格式字符串则一并提取，否则
退化为助记符占位。

用法:
  python3 tools/import_isa.py <CasioEmuMsvc>/Instructions.cpp [-o u8emu/isa_auto.py]
  python3 tools/import_isa.py <CasioEmuMsvc>/opcodes.lua --lua [-o u8emu/isa_auto.py]

生成的是与 u8emu/isa.py 的 TABLE 同构的列表；(mask, code) 冲突时保留
"固定位更多"的一条，与 isa.build_tables 的后填充覆盖语义一致。把结果
合并进 u8emu/isa.py 即可，或临时用 isa_auto.TABLE 整体替换。
"""
from __future__ import annotations
import argparse, re, sys

HEX = r"0[xX][0-9A-Fa-f]+"
LINE_A = re.compile(rf"OP_([a-z0-9_]+)\s*,\s*({HEX})\s*,\s*({HEX})")
LINE_B = re.compile(rf"({HEX})\s*,\s*({HEX})\s*,\s*&?\s*(?:CPU::)?OP_([a-z0-9_]+)")
FMT_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def norm(a, b):
    """判定 (mask, code) 顺序。

    match 恒为 mask 的子集，(a|b)==a 与 (a|b)==b 两个方向都能成立，
    无法用 OR 判序；改用 popcount：位数多的是掩码，相等时取前者。
    """
    a, b = int(a, 16), int(b, 16)
    if a.bit_count() >= b.bit_count():
        return a, b
    return b, a


def parse_cpp(text):
    """-> [(line_no, name, mask, code, fmt)]"""
    entries = []
    for ln, line in enumerate(text.splitlines(), 1):
        pair = None
        m = LINE_A.search(line)
        if m:
            nm = norm(m.group(2), m.group(3))
            if nm:
                pair = (m.group(1), *nm)
        if pair is None:
            m = LINE_B.search(line)
            if m:
                nm = norm(m.group(1), m.group(2))
                if nm:
                    pair = (m.group(3), *nm)
        if pair is None:
            continue
        name, mask, code = pair
        fm = FMT_RE.search(line)
        fmt = fm.group(1) if fm else name
        entries.append((ln, name, mask, code, fmt))
    return entries


LUA_NAME = re.compile(r"name\s*=\s*[\"']([\w]+)[\"']")
LUA_MASK = re.compile(r"mask\s*=\s*(0x[0-9A-Fa-f]+)")
LUA_CODE = re.compile(r"code\s*=\s*(0x[0-9A-Fa-f]+)")


def _lua_blocks(text):
    """配对计数返回所有平衡的花括号块内容（含外层表）。
    格式串里的 {n} 占位符会被当成子块，但子块没有 name/mask/code，
    解析时自然被跳过；外层表块的 name/mask/code 取块内首个，恰好对应
    表内第一条。"""
    out = []
    stack = []
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(i)
        elif ch == "}" and stack:
            out.append(text[stack.pop() + 1:i])
    return out


def parse_lua(text):
    """-> [(line_no, name, mask, code, fmt)]"""
    entries = []
    for s in _lua_blocks(text):
        name_m = LUA_NAME.search(s)
        mask_m = LUA_MASK.search(s)
        code_m = LUA_CODE.search(s)
        if not (name_m and mask_m and code_m):
            continue
        mask, code = norm(mask_m.group(1), code_m.group(1))
        entries.append((0, name_m.group(1), mask, code, name_m.group(1)))
    return entries


def dedup(entries):
    """同名编码冲突时保留固定位更多的；同一 (mask, code) 优先带格式串的"""
    by_key = {}
    for ln, name, mask, code, fmt in entries:
        key = (mask, code)
        old = by_key.get(key)
        if old is None:
            by_key[key] = (name, mask, code, fmt)
        else:
            if bin(mask).count("1") > bin(old[1]).count("1"):
                by_key[key] = (name, mask, code, fmt)
            elif (fmt != name) and (old[3] == old[0]):
                by_key[key] = (name, mask, code, fmt)
    return list(by_key.values())


def emit(path, src, entries, lua):
    lines = [
        "# SPDX-License-Identifier: GPL-3.0-or-later",
        "# 本文件由 tools/import_isa.py 自动生成，请勿手改。",
        f"# 来源: {src} ({'lua' if lua else 'cpp'} 模式)",
        "# 条目格式与 u8emu/isa.py 的 TABLE 相同:",
        "#   (mask, match, handler_name, disasm_fmt, extra_words)",
        "# extra_words 无法从上游推导，统一置 0，请按需补。",
        "TABLE = [",
    ]
    for name, mask, code, fmt in sorted(entries, key=lambda e: (e[1], e[2])):
        lines.append(f"    (0x{mask:04X}, 0x{code:04X}, {name!r}, {fmt!r}, 0),")
    lines.append("]")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="CasioEmuMsvc 的 Instructions.cpp 或 opcodes.lua")
    ap.add_argument("--lua", action="store_true", help="按 Lua 表格式解析")
    ap.add_argument("-o", "--output", default="u8emu/isa_auto.py")
    a = ap.parse_args()

    try:
        text = open(a.source, encoding="utf-8", errors="replace").read()
    except OSError as e:
        sys.exit(f"cannot read {a.source}: {e}")

    entries = parse_lua(text) if a.lua else parse_cpp(text)
    if not entries:
        sys.exit(f"no entries parsed from {a.source}; "
                 f"请确认文件路径/格式（或改用 --lua）")

    # 统计冲突
    by_code = {}
    for _, name, mask, code, _ in entries:
        by_code.setdefault(code, []).append((mask, name))
    conflicts = [c for c, lst in by_code.items() if len(set(m for m, _ in lst)) > 1]
    if conflicts:
        print(f"WARN: {len(conflicts)} 个 code 存在多条不同掩码（冲突者取更具体的一条）:",
              file=sys.stderr)
        for c in conflicts[:20]:
            print(f"  {c:04X}: {by_code[c]}", file=sys.stderr)

    final = dedup(entries)
    emit(a.output, a.source, final, a.lua)
    print(f"parsed {len(entries)} entries, dedup -> {len(final)}")
    print(f"written: {a.output}  (合并进 u8emu/isa.py 即可生效)")


if __name__ == "__main__":
    main()
