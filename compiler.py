import json
import os
from rich.console import Console
import argparse as arg
import re
import package

console = Console()


def loadfile():
    console.print(
        "[black bold on cyan] 输入ROP文件路径喵 [/black bold on cyan][cyan][/cyan]",
        end="",
    )
    try:
        context = json.loads(package.get_text(input()))
    except (json.JSONDecodeError, UnicodeDecodeError):
        console.print(
            "\n[black bold on red] ERROR [/black bold on red] 这貌似[b red]不是[/b red]一个ROP（json-based）文件喵……请重新上传！"
        )
        context = loadfile()
    except (FileNotFoundError, PermissionError, OSError):
        console.print(
            "\n[black bold on red] ERROR [/black bold on red] 文件上传失败喵……请重新上传！"
        )
        context = loadfile()
    return context


# 此函数为Vibe-Coding产物
def compiler(context):
    """
    编译 ROP 文件，将汇编 DSL 转为最终 hex 字节串。
    参数 context: {"input": str, "leftStartAddress": str, "rightStartAddress": str, "gadgets": list}
    返回 dict
    """
    # ==================== 校验 ====================
    required_keys = {"input", "leftStartAddress", "rightStartAddress", "gadgets"}
    if not isinstance(context, dict) or not required_keys.issubset(context.keys()):
        raise TypeError(f"参数不是合法的 ROP 对象，需包含 {required_keys}")
    mainrop = context["input"]
    left = int(context["leftStartAddress"], 16)
    right = int(context["rightStartAddress"], 16)
    gadgets = context["gadgets"]  # [{name: "pop-er0", addr: "121A8"}, ...]
    # ==================== 去注释 ====================
    splitstr = mainrop.splitlines()
    for i in range(len(splitstr)):
        comment_pos = splitstr[i].find("//")
        if comment_pos != -1:
            splitstr[i] = splitstr[i][:comment_pos]
    # ==================== 初始化 ====================
    hex_chars = ""  # 最终 hex 字符串 (纯十六进制大写)
    constants = {}  # {name: int_value}
    deferred_patches = []  # 延迟回填队列 [{hex_pos, expression, line_no}]
    count_block = 0  # [表达式] 数量
    gadget_block = 0  # #gadget; 数量
    addrnum = 0  # <锚点> 数量
    error_count = 0  # 错误计数
    HEX_SET = set("0123456789abcdefABCDEF")

    # ==================== 辅助函数 ====================
    def encode_gadget_addr(addr_str, allow_00):
        """将 5 位 hex 地址 (如 "121A8") 编码为 8 位 hex 字符串"""
        if len(addr_str) < 5:
            addr_str = addr_str.zfill(5)
        h1 = addr_str[3:5]
        if h1 == "00" and not allow_00:
            h1 = "01"
        h2 = addr_str[1:3]
        h3 = ("0" if allow_00 else "3") + addr_str[0]
        h4 = "00" if allow_00 else "30"
        return (h1 + h2 + h3 + h4).upper()

    def eval_expression(inner, constants, allow_deferred=False):
        """
        计算 [...] 内的表达式，如 "$base + 10" 或 "1234"
        返回 {"value": int, "error": bool, "deferred": bool}
        """
        value = 0x0000
        symbol = "+"  # 当前待处理运算符: "+" / "-" / "" (无)
        has_error = False
        deferred = False
        parts = inner.strip().split()
        for part in parts:
            # --- $常量引用 ---
            if part.startswith("$"):
                name = part[1:]
                if name in constants:
                    if symbol == "+":
                        value += constants[name]
                    elif symbol == "-":
                        value -= constants[name]
                    else:
                        has_error = True
                        break
                else:
                    # 常量未定义
                    if allow_deferred:
                        deferred = True
                        if symbol == "+":
                            value += 0
                        elif symbol == "-":
                            value -= 0
                        else:
                            has_error = True
                            break
                    else:
                        has_error = True
                        break
                symbol = ""
            # --- 运算符 ---
            elif part in ("+", "-"):
                if symbol == "":
                    symbol = part
                else:
                    has_error = True
                    break
            # --- 字面 hex 值 ---
            else:
                if not re.match(r"^-?[0-9a-fA-F]+$", part):
                    has_error = True
                    break
                v = int(part, 16)
                if symbol == "+":
                    value += v
                elif symbol == "-":
                    value -= v
                else:
                    has_error = True
                    break
                symbol = ""
        if symbol != "":
            has_error = True
        elif not (allow_deferred and deferred):
            if value > 0xFFFF or value < -0x8000:
                has_error = True
            if value < 0:
                value = 0xFFFF + value + 1  # 负数转补码
        return {"value": value, "error": has_error, "deferred": deferred}

    # ==================== PASS 1: 逐行扫描 ====================
    line = 0
    for current_line in splitstr:
        line += 1
        i = 0
        while i < len(current_line):
            ch = current_line[i]
            # ------ 2a. $常量定义: $name = hex; ------
            if ch == "$":
                semicolon = current_line.find(";", i)
                if semicolon == -1:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量定义缺少分号")
                    error_count += 1
                    break
                body = current_line[i + 1 : semicolon].replace(" ", "")
                parts = body.split("=")
                if len(parts) != 2:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量定义格式错误")
                    error_count += 1
                    i = semicolon + 1
                    continue
                name = parts[0]
                if not name:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量名不能为空")
                    error_count += 1
                    i = semicolon + 1
                    continue
                if name in constants:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量 '{name}' 重复定义")
                    error_count += 1
                    i = semicolon + 1
                    continue
                val_str = parts[1]
                if not re.match(r"^-?[0-9a-fA-F]+$", val_str):
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量值 '{val_str}' 非法")
                    error_count += 1
                else:
                    int_val = int(val_str, 16)
                    if int_val > 0xFFFF or int_val < -0x8000:
                        console.print(f"[black on red] ERROR [/black on red] 行{line}: 常量值 '{val_str}' 超出范围")
                        error_count += 1
                    else:
                        if int_val < 0:
                            int_val = 0xFFFF + int_val + 1
                        constants[name] = int_val
                i = semicolon + 1
                continue
            # ------ 2b. #gadget引用: #name; 或 #-name; ------
            if ch == "#":
                semicolon = current_line.find(";", i)
                if semicolon == -1:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: gadget 引用缺少分号")
                    error_count += 1
                    break
                name_body = current_line[i + 1 : semicolon]
                allow_00 = True
                if name_body.startswith("-"):
                    allow_00 = False
                    name_body = name_body[1:]
                found = next((g for g in gadgets if g.get("name") == name_body), None)
                if found is None:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: gadget '{name_body}' 未找到")
                    error_count += 1
                else:
                    encoded = encode_gadget_addr(found.get("addr", ""), allow_00)
                    hex_chars += encoded
                    gadget_block += 1
                i = semicolon + 1
                continue
            # ------ 2c. [数值块]: [表达式] ------
            if ch == "[":
                bracket = current_line.find("]", i)
                if bracket == -1:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 方括号未闭合")
                    error_count += 1
                    break
                inner = current_line[i + 1 : bracket]
                result = eval_expression(inner, constants, allow_deferred=True)
                if result["error"]:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 表达式 '[{inner}]' 无效")
                    error_count += 1
                elif result["deferred"]:
                    # 前向引用: 仅记录位置, 不加占位符 (锚点计算依赖精确的hex_chars长度)
                    deferred_patches.append(
                        {
                            "hex_pos": len(hex_chars),
                            "expression": inner,
                            "line_no": line,
                        }
                    )
                else:
                    val_hex = f"{result['value']:04X}"
                    little_endian = val_hex[2:4] + val_hex[0:2]
                    hex_chars += little_endian
                    count_block += 1
                i = bracket + 1
                continue
            # ------ 2d. <地址锚点>: <name> 或 <-name> ------
            if ch == "<":
                close = current_line.find(">", i)
                if close == -1:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 尖括号未闭合")
                    error_count += 1
                    break
                anchor_body = current_line[i + 1 : close]
                use_left = False
                if anchor_body.startswith("-"):
                    use_left = True
                    anchor_body = anchor_body[1:]
                if not anchor_body:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 锚点名不能为空")
                    error_count += 1
                elif anchor_body in constants:
                    console.print(f"[black on red] ERROR [/black on red] 行{line}: 锚点名 '{anchor_body}' 重复")
                    error_count += 1
                else:
                    # 计算当前真实偏移: 已产生字节数 + 前面已排队的延迟块字节数
                    deferred_offset = 0
                    for p in deferred_patches:
                        if p["hex_pos"] <= len(hex_chars):
                            deferred_offset += 2  # 每个延迟块占 2 字节
                    base_addr = left if use_left else right
                    addr_value = base_addr + len(hex_chars) // 2 + deferred_offset
                    constants[anchor_body] = addr_value
                    addrnum += 1
                i = close + 1
                continue
            # ------ 2e. 裸十六进制字符 ------
            if ch in HEX_SET:
                hex_chars += ch.upper()
                i += 1
                continue
            # ------ 2f. 其他字符 (空格、标点等) ------
            i += 1
    # ==================== PASS 2: 回填延迟数值块 ====================
    deferred_patches.sort(key=lambda p: p["hex_pos"])
    offset_shift = 0  # 已插入的 hex 字符总数, 每次插入后累加
    for patch in deferred_patches:
        result = eval_expression(patch["expression"], constants, allow_deferred=False)
        if result["error"]:
            console.print(
                f"[black on red] ERROR [/black on red] 行{patch['line_no']}: 延迟表达式 '[{patch['expression']}]' 最终求值失败"
            )
            error_count += 1
            continue
        val_hex = f"{result['value']:04X}"
        little_endian = val_hex[2:4] + val_hex[0:2]
        insert_pos = patch["hex_pos"] + offset_shift
        hex_chars = hex_chars[:insert_pos] + little_endian + hex_chars[insert_pos:]
        offset_shift += len(little_endian)
    # ==================== 返回结果 ====================
    bitnum = len(hex_chars)  # hex 字符总数
    trulybytenum = len(hex_chars) // 2  # 总字节数
    return {
        "hex_chars": hex_chars,
        "leftaddr": f"{left:04X}",
        "rightaddr": f"{right:04X}",
        "count_block": count_block,
        "gadget_block": gadget_block,
        "addrnum": addrnum,
        "bitnum": bitnum,
        "totalnum": trulybytenum,
        "error_count": error_count,
        "constants": {k: f"0x{v:04X}" for k, v in constants.items()},
    }


def main():
    prs = arg.ArgumentParser(
        description="根据贴吧@wlyibo制作的RopIDE，用Python移植编译程序，compiler函数用Vibe-Coding转写。（喵）"
    )
    prs.add_argument("file", type=str, nargs="?", default=None, help="ROP文件路径")
    args = prs.parse_args()
    if args.file == None:
        context = loadfile()
    else:
        try:
            context = json.loads(package.get_text(args.file))
        except (json.JSONDecodeError, UnicodeDecodeError):
            console.print(
                "\n[black bold on red] ERROR [/black bold on red] 这貌似[b red]不是[/b red]一个ROP（json-based）文件喵……请重新上传！"
            )
            os._exit(0)
        except (FileNotFoundError, PermissionError, OSError):
            console.print(
                "\n[black bold on red] ERROR [/black bold on red] 文件上传失败喵……请重新上传！"
            )
            os._exit(0)

    console.print(compiler(context))


if __name__ == "__main__":
    main()
