from rich.console import Console
from rich.table import Table
from rich.text import Text
from hexdump2 import hexdump
from pathlib import Path
import compiler, package, json
import pyperclip as clip
import os
import pick as p
import requests
import sys

ROPIDE_VERSION = 100
BASE_URL = "https://ropide.pages.dev"  # 怎么颇有点调用AI模型的感觉
items = None


def _prompt_address(prompt: str, console: Console) -> str:
    while True:
        console.print(prompt, end="")
        addr = input().upper().removeprefix("0X")
        if addr and len(addr) <= 5 and all(c in "0123456789ABCDEF" for c in addr):
            return addr
        console.print(
            "[black on red] ERROR [/black on red] 地址必须是十六进制数字（例如 E9E0），请重新输入。"
        )


def cmp(a, b):
    pass


def main():
    console = Console()
    console.print(
        "[black bold on cyan] 版本号 [/black bold on cyan] RopIDE-Python version-010826"
    )
    console.print(
        "[black on yellow bold] 简介 [/black on yellow bold] [italic]这是基于贴吧@wlyibo制作的RopIDE：Python移植版本，一定程度上可以解决浏览器抽风上传不了文件/没有网的时候无法方便地写ROP程序的痛苦。[/italic]"
    )
    console.print(
        "[black on red bold] 网页版 [/black on red bold] [italic u]ropide.pages.dev[/italic u]"
    )

    print()
    console.print(
        "[b]欢迎使用RopIDE[black on blue]Pyt[/black on blue][black on yellow]hon[/black on yellow]！\n[/b]本程序应与终端代码编辑器配合使用。本程序仅提供文件操作功能，无内置编辑器。"
    )

    while True:
        print("Continue with Enter ……")
        title = "用 j/k 键选择菜单（方向键也许可用在Windows 11, Linux发行版），Enter/Return 以选中。"
        input()

        optns = [
            "创建新的项目文件夹",
            "编译已有的.rop文件",
            "打开项目文件夹",
            "转换已有的项目文件夹为.rop文件",
            "转换.rop文件为项目文件夹",
            "程序广场",
            "退出",
        ]
        optn, idx = p.pick(options=optns, indicator="", title=title)
        if idx == 0:
            console.print(f"[black on white] LOG [/black on white] 选择了 {optn}。")
            console.print(
                "[black on cyan bold] 输入项目根路径名（e.g. path/to/box/name） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            fpath = Path(input()).expanduser().resolve()
            try:
                os.makedirs(fpath)
            except FileExistsError:
                console.print(
                    f"[black on red] ERROR [/black on red] 路径 {fpath} 已存在。"
                )
                continue
            except PermissionError:
                console.print(
                    f"[black on red] ERROR [/black on red] 无法创建 {fpath}：权限不够"
                )
                continue
            console.print(f"[black on white] LOG [/black on white] 成功创建 {fpath}。")

            title = "选择gaegets预设，或者上传一个自定义gadgets，或者使用空gadgets。"
            optns = [
                "CASIO fx-991 CN X VerF",
                "CASIO fx-991 CN X VerC",
                "上传.json gadgets文件",
                "使用空gadgets",
            ]
            optn, idx = p.pick(options=optns, indicator="", title=title)
            with open(f"{fpath}/main.rin", "w", encoding="utf-8") as f:
                f.write("// main.rin")
                f.close()
            console.print(
                f"[black on white] LOG [/black on white] 成功创建 {fpath}/main.rin。"
            )
            if idx == 0:
                BASE = Path(__file__).resolve().parent
                gadgets = package.get_text(BASE / "gadgets" / "VerF gadgets.json")
                with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                    f.write(gadgets)
                    f.close()
            elif idx == 1:
                BASE = Path(__file__).resolve().parent
                gadgets = package.get_text(BASE / "gadgets" / "VerC gadgets.json")
                with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                    f.write(gadgets)
                    f.close()
            elif idx == 2:
                console.print(
                    "[black on cyan bold] 输入gadgets路径（e.g. path/to/gadgets.json） [/black on cyan bold][cyan][/cyan]",
                    end="",
                )
                gpath = input()
                try:
                    gadgets = package.get_text(gpath)
                except:
                    console.print(
                        f"[black on red] ERROR [/black on red] 找不到 {gpath}。"
                    )
                    continue
                with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                    f.write(gadgets)
                    f.close()

            else:
                with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                    f.write("[]")
                    f.close()
            console.print(
                f"[black on white] LOG [/black on white] 成功创建 {fpath}/gadgets.json。"
            )
            leftaddr = _prompt_address(
                "[black on cyan bold] 输入左侧地址（e.g. E9E0） [/black on cyan bold][cyan][/cyan]",
                console,
            )
            rightaddr = _prompt_address(
                "[black on cyan bold] 输入右侧地址（e.g. D710） [/black on cyan bold][cyan][/cyan]",
                console,
            )
            with open(f"{fpath}/config.json", "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "leftStartAddress": leftaddr,
                            "rightStartAddress": rightaddr,
                            "ideVersion": ROPIDE_VERSION,
                        },
                        ensure_ascii=False,
                    )
                )
                f.close()
            console.print(
                f"[black on white] LOG [/black on white] 成功创建 {fpath}/config.json。"
            )
            console.print(f"请[b]不要[/b]更改{fpath}里面的文件名！")

        elif idx == 1:
            console.print(f"[black on white] LOG [/black on white] 选择了 {optn}。")
            console.print(
                "[black on cyan bold] 输入.rop文件路径（e.g. path/to/rop/name.rop） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            rop_path = input()
            try:
                context = package.get_data(rop_path)
            except FileNotFoundError:
                console.print(
                    f"[black on red] ERROR [/black on red] 找不到 {rop_path}。"
                )
                continue
            except PermissionError:
                console.print(
                    f"[black on red] ERROR [/black on red] 无法读取 {rop_path}：权限不够。"
                )
                continue
            except (json.JSONDecodeError, UnicodeDecodeError):
                console.print(
                    f"[black on red] ERROR [/black on red] {rop_path} 不是合法的 .rop（JSON）文件。"
                )
                continue
            console.print(
                f"[black on white] LOG [/black on white] 成功加载 {rop_path}。"
            )

            required = {"input", "gadgets", "leftStartAddress", "rightStartAddress"}
            if (
                not isinstance(context, dict)
                or not required.issubset(context)
                or not isinstance(context["input"], str)
                or not isinstance(context["gadgets"], list)
                or not isinstance(context["leftStartAddress"], str)
                or not isinstance(context["rightStartAddress"], str)
            ):
                console.print(
                    f"[black on red] ERROR [/black on red] {rop_path} 缺少必需字段（input/gadgets/leftStartAddress/rightStartAddress）。"
                )
                continue
            try:
                int(context["leftStartAddress"], 16)
                int(context["rightStartAddress"], 16)
            except ValueError:
                console.print(
                    f"[black on red] ERROR [/black on red] {rop_path} 中的地址字段不是合法的十六进制。"
                )
                continue

            target = "launch"
            cnt = 0
            linne = None
            for line in context["input"].splitlines():
                cnt += 1
                if target.lower() in line.lower():  # 不区分大小写
                    console.print(
                        f"[black on white] LOG [/black on white] 似乎在 行{cnt} 找到了有关launcher的信息。"
                    )
                    linne = line
                    break

            opt = compiler.compiler(context)
            console.print(
                f"[black on white] LOG [/black on white] 完成编译。总共 {opt['totalnum']} bytes，{opt['error_count']} errors。"
            )
            console.print(f"左侧起始地址：[black on yellow]0x{opt['leftaddr']}")
            console.print(
                f"可能带有launcher信息的行：\n [yellow]{linne}[/yellow]."
                if linne != None
                else "未找到launcher相关信息"
            )

            if len(opt["hex_chars"]) % 2 == 1:
                console.print(
                    f"[black on red] ERROR [/black on red] 编译结果含奇数个十六进制字符（共 {len(opt['hex_chars'])} 个），无法以字节形式显示。请检查代码中的裸十六进制字符是否成对出现。"
                )
            else:
                hexbytes = bytes.fromhex(opt["hex_chars"])
                start_addr = int("0x" + opt["leftaddr"], 0)
                hexdump(hexbytes, offset=start_addr)
            console.print("要复制吗[Y/n]", end="")
            shouldcopyornot = input()
            if not (shouldcopyornot.lower() == "n"):
                try:
                    clip.copy(opt["hex_chars"])
                except Exception:
                    console.print(
                        "[black on red] ERROR [/black on red] 复制失败：未找到可用的剪贴板工具（需要 xclip/xsel/pbcopy 等）。"
                    )

        elif idx == 2:
            console.print(f"[black on white] LOG [/black on white] 选择了 {optn}。")
            console.print(
                "[black on cyan bold] 输入项目根路径名（e.g. path/to/box/name） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            fpath = Path(input()).expanduser().resolve()
            try:
                config = json.loads(package.get_text(f"{fpath}/config.json"))
            except FileNotFoundError:
                console.print(
                    f"[black on red] ERROR [/black on red] 找不到 {fpath}/config.json。"
                )
                continue
            except json.JSONDecodeError:
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/config.json 不是合法的 JSON 文件。"
                )
                continue
            if not isinstance(config, dict) or not {
                "leftStartAddress",
                "rightStartAddress",
            }.issubset(config):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/config.json 缺少 leftStartAddress/rightStartAddress 字段。"
                )
                continue
            console.print(
                f"[black on blue] 左侧地址 [/black on blue] 0x{config['leftStartAddress']}，[black on blue] 右侧地址 [/black on blue] 0x{config['rightStartAddress']}"
            )
            gadgets = Table(title="[black on green] gadgets [/black on green]")
            gadgets.add_column("名称")
            gadgets.add_column("地址")
            gadgets.add_column("描述")
            # gadgets.add_column("标签")
            # 过于先进，无法展示
            try:
                raw_gadgets = package.get_text(f"{fpath}/gadgets.json")
                gadgets_list = json.loads(raw_gadgets) if raw_gadgets.strip() else []
            except FileNotFoundError:
                console.print(
                    f"[black on red] ERROR [/black on red] 找不到 {fpath}/gadgets.json。"
                )
                continue
            except json.JSONDecodeError:
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/gadgets.json 不是合法的 JSON 文件。"
                )
                continue
            if not isinstance(gadgets_list, list):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/gadgets.json 的内容不是数组。"
                )
                continue
            for i in gadgets_list:
                gadgets.add_row(
                    f"[i]{i.get('name', '?')}[/i]",
                    i.get("addr", "?"),
                    i.get("desc", ""),
                )
            console.print(gadgets)
            while True:
                console.print(
                    "[black on cyan bold] 希望操作什么？（[u]g[/u]adgets [u]s[/u]howGadgets [u]l[/u]eftStartAddress [u]r[/u]ightStartAddress [red][u]q[/u]uit[/red]） [/black on cyan bold][cyan][/cyan]",
                    end="",
                )
                ans = input()
                if ans.lower() == "l":
                    leftaddr = _prompt_address(
                        "[black on cyan bold] 输入左侧地址（e.g. E9E0） [/black on cyan bold][cyan][/cyan]",
                        console,
                    )
                    context = json.loads(package.get_text(f"{fpath}/config.json"))
                    with open(f"{fpath}/config.json", "w", encoding="utf-8") as f:
                        tmp = json.dumps(
                            {
                                "leftStartAddress": leftaddr,
                                "rightStartAddress": context["rightStartAddress"],
                                "ideVersion": ROPIDE_VERSION,
                            }
                        )
                        f.write(tmp)
                        f.close()

                elif ans.lower() == "r":
                    rightaddr = _prompt_address(
                        "[black on cyan bold] 输入右侧地址（e.g. D710） [/black on cyan bold][cyan][/cyan]",
                        console,
                    )
                    context = json.loads(package.get_text(f"{fpath}/config.json"))
                    with open(f"{fpath}/config.json", "w", encoding="utf-8") as f:
                        tmp = json.dumps(
                            {
                                "leftStartAddress": context["leftStartAddress"],
                                "rightStartAddress": rightaddr,
                                "ideVersion": ROPIDE_VERSION,
                            }
                        )
                        f.write(tmp)
                        f.close()
                elif ans.lower() == "g":
                    console.print(
                        "[black on cyan bold] 输入gadgets名（e.g. pop-xr12） [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    name = input()
                    console.print(
                        "[black on cyan bold] 输入地址（e.g. 1D52C） [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    addr = input()
                    console.print(
                        "[black on cyan bold] 输入描述（e.g. 赋值XR12） [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    desc = input()
                    context = json.loads(package.get_text(f"{fpath}/gadgets.json"))
                    with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                        context.append(
                            {"name": name, "addr": addr, "desc": desc, "tags": []}
                        )
                        f.write(json.dumps(context, ensure_ascii=False))
                elif ans.lower() == "s":
                    gadgets = Table(title="[black on green] gadgets [/black on green]")
                    gadgets.add_column("名称")
                    gadgets.add_column("地址")
                    gadgets.add_column("描述")
                    # gadgets.add_column("标签")
                    # 过于先进，无法展示
                    try:
                        raw_gadgets = package.get_text(f"{fpath}/gadgets.json")
                        gadgets_list = (
                            json.loads(raw_gadgets) if raw_gadgets.strip() else []
                        )
                    except FileNotFoundError:
                        console.print(
                            f"[black on red] ERROR [/black on red] 找不到 {fpath}/gadgets.json。"
                        )
                        continue
                    except json.JSONDecodeError:
                        console.print(
                            f"[black on red] ERROR [/black on red] {fpath}/gadgets.json 不是合法的 JSON 文件。"
                        )
                        continue
                    if not isinstance(gadgets_list, list):
                        console.print(
                            f"[black on red] ERROR [/black on red] {fpath}/gadgets.json 的内容不是数组。"
                        )
                        continue
                    for i in gadgets_list:
                        gadgets.add_row(
                            f"[i]{i.get('name', '?')}[/i]",
                            i.get("addr", "?"),
                            i.get("desc", ""),
                        )
                    console.print(gadgets)
                elif ans.lower() == "q":
                    break

        elif idx == 3:
            console.print(f"[black on white] LOG [/black on white] 选择了 {idx}。")
            console.print(
                "[black on cyan bold] 输入项目根路径名（e.g. path/to/box/name） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            fpath = Path(input()).expanduser().resolve()
            try:
                context = package.get_text(f"{fpath}/main.rin")
                raw_gadgets = package.get_text(f"{fpath}/gadgets.json")
                tmp = json.loads(package.get_text(f"{fpath}/config.json"))
            except FileNotFoundError:
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath} 缺少 main.rin / gadgets.json / config.json。"
                )
                continue
            except json.JSONDecodeError:
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath} 中的 gadgets.json 或 config.json 不是合法的 JSON 文件。"
                )
                continue
            if not isinstance(tmp, dict) or not {
                "leftStartAddress",
                "rightStartAddress",
            }.issubset(tmp):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/config.json 缺少 leftStartAddress/rightStartAddress 字段。"
                )
                continue
            leftaddr = tmp["leftStartAddress"]
            rightaddr = tmp["rightStartAddress"]
            try:
                int(leftaddr, 16)
                int(rightaddr, 16)
            except ValueError:
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/config.json 中的地址不是合法的十六进制。"
                )
                continue
            gadgets = json.loads(raw_gadgets) if raw_gadgets.strip() else []
            if not isinstance(gadgets, list):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath}/gadgets.json 的内容不是数组。"
                )
                continue
            try:
                with open(f"{fpath}/output.rop", "w", encoding="utf-8") as f:
                    f.write(
                        package.package(
                            context, gadgets, leftaddr, rightaddr, ROPIDE_VERSION
                        )
                    )
                    f.close()
            except (PermissionError, OSError):
                console.print(
                    f"[black on red] ERROR [/black on red] 无法写入 {fpath}/output.rop：权限不够或磁盘错误。"
                )
                continue
            console.print(
                f"[black on white] LOG [/black on white]已创建{fpath}/output.rop。"
            )

        elif idx == 4:
            console.print(f"[black on white] LOG [/black on white] 选择了 {idx}。")
            console.print(
                "[black on cyan bold] 输入.rop路径（e.g. path/to/box/name） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            fpath = Path(input()).expanduser().resolve()
            try:
                context = package.get_data(fpath)
            except FileNotFoundError:
                console.print(f"[black on red] ERROR [/black on red] 找不到 {fpath}。")
                continue
            except PermissionError:
                console.print(
                    f"[black on red] ERROR [/black on red] 无法读取 {fpath}：权限不够。"
                )
                continue
            except (json.JSONDecodeError, UnicodeDecodeError):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath} 不是合法的 .rop（JSON）文件。"
                )
                continue
            required = {"input", "gadgets", "leftStartAddress", "rightStartAddress"}
            if (
                not isinstance(context, dict)
                or not required.issubset(context)
                or not isinstance(context["input"], str)
                or not isinstance(context["gadgets"], list)
            ):
                console.print(
                    f"[black on red] ERROR [/black on red] {fpath} 缺少必需字段（input/gadgets/leftStartAddress/rightStartAddress）。"
                )
                continue
            console.print(context)
            console.print(
                "[black on cyan bold] 输入项目根路径名（e.g. path/to/box/name） [/black on cyan bold][cyan][/cyan]",
                end="",
            )
            fpath = Path(input()).expanduser().resolve()
            try:
                os.makedirs(fpath)
            except FileExistsError:
                console.print(
                    f"[black on red] ERROR [/black on red] 路径 {fpath} 已存在。"
                )
                continue
            except PermissionError:
                console.print(
                    f"[black on red] ERROR [/black on red] 无法创建 {fpath}：权限不够。"
                )
                continue
            console.print(f"[black on white] LOG [/black on white] 成功创建 {fpath}。")
            with open(f"{fpath}/main.rin", "w", encoding="utf-8") as f:
                f.write(context["input"])
                f.close()
            with open(f"{fpath}/gadgets.json", "w", encoding="utf-8") as f:
                f.write(json.dumps(context["gadgets"], ensure_ascii=False))
                console.print(json.dumps(context["gadgets"], ensure_ascii=False))
                f.close()
            with open(f"{fpath}/config.json", "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "leftStartAddress": context["leftStartAddress"],
                            "rightStartAddress": context["rightStartAddress"],
                        },
                        ensure_ascii=False,
                    )
                )
                f.close()
        elif idx == 5:
            console.print("[black on green] 程序广场 [/black on green]")
            while True:
                console.print(
                    "[black on cyan bold] 输入想要进行的操作（[u]G[/u]ET程序列表并做操作 [u]P[/u]OST程序至程序广场 [u]q[/u]uit） [/black on cyan bold][cyan][/cyan]",
                    end="",
                )
                opera = input()

                if opera.lower() == "g":
                    console.print(
                        "[black on white] LOG [/black on white] 尝试获取程序列表。"
                    )
                    try:
                        r = requests.get(f"{BASE_URL}/api/market", timeout=10)
                        r.raise_for_status()
                        items = r.json()
                    except requests.RequestException as e:
                        console.print(
                            f"[black on red] ERROR [/black on red] [black on blue] GET [/black on blue] {BASE_URL}/api/market 失败：{e}"
                        )
                        continue
                    except (json.JSONDecodeError, ValueError):
                        console.print(
                            f"[black on red] ERROR [/black on red] [black on blue] GET [/black on blue] {BASE_URL}/api/market 返回了非 JSON 内容。"
                        )
                        continue
                    if not isinstance(items, list):
                        console.print(
                            f"[black on red] ERROR [/black on red] {BASE_URL}/api/market 返回的数据不是列表。"
                        )
                        continue
                    console.print(
                        f"[black on white] LOG [/black on white] [black on blue] GET [/black on blue] {BASE_URL}/api/market [green]{r.status_code} {r.reason}[/green] 耗时 {r.elapsed.total_seconds() * 1000}ms 喵。"
                    )
                    items = sorted(items, key=lambda x: x["id"], reverse=True)
                    table_itmes = Table(title="程序广场", show_lines=True)
                    table_itmes.add_column("编号", no_wrap=False)
                    table_itmes.add_column(
                        "名称", style="bold", no_wrap=False, width=20
                    )
                    table_itmes.add_column("作者", no_wrap=False, width=20)
                    table_itmes.add_column("机型", no_wrap=False, width=20)
                    table_itmes.add_column(
                        "描述", style="yellow italic", no_wrap=False, width=20
                    )
                    for i in items:
                        table_itmes.add_row(
                            str(i["id"]),
                            Text(i["name"]).wrap(console, width=20),
                            Text(i["author"]).wrap(console, width=20),
                            Text(i["model"]).wrap(console, width=20),
                            Text(i["description"]).wrap(console, width=20),
                        )
                    console.print(table_itmes)
                    while True:
                        console.print(
                            "[black on cyan bold] 输入想要操作的程序编号（[u]q[/u]uit） [/black on cyan bold][cyan][/cyan]",
                            end="",
                        )
                        id = input()
                        if id.lower() == "q":
                            break
                        if not id.isdigit():
                            continue
                        opera = None
                        for i in items:
                            if i["id"] == int(id):
                                opera = i
                                break
                        if opera == None:
                            console.print(
                                f"[black on red] ERROR [/black on red] 找不到编号为{id}的程序。"
                            )
                            continue
                        try:
                            resp = requests.get(
                                f"{BASE_URL}/api/market",
                                params={"id": int(id)},
                                timeout=10,
                            )
                            resp.raise_for_status()
                            context = json.loads(resp.json()["data"])
                            console.print(
                                f"[black on white] LOG [/black on white] [black on blue] GET [/black on blue] {BASE_URL}/api/market?id={id} [green]{resp.status_code} {resp.reason}[/green] 耗时 {resp.elapsed.total_seconds() * 1000}ms 喵。"
                            )
                        except requests.RequestException as e:
                            console.print(
                                f"[black on red] ERROR [/black on red] [black on blue] GET [/black on blue] {BASE_URL}/api/market?id={id} 失败：{e}"
                            )
                            continue
                        except (KeyError, json.JSONDecodeError, TypeError):
                            console.print(
                                f"[black on red] ERROR [/black on red] [black on blue] GET [/black on blue] {BASE_URL}/api/market?id={id} 返回的数据格式异常。"
                            )
                            continue
                        while True:
                            console.print(
                                "[black on cyan bold] 我们该进行什么操作？（提取[u]g[/u]adgets 下载.[u]r[/u]op文件 [u]q[/u]uit） [/black on cyan bold][cyan][/cyan]",
                                end="",
                            )
                            ans = input()
                            if ans.lower() == "g":
                                console.print(
                                    "[black on cyan bold] 输入gadgets.json导出路径（e.g. path/to/gadgets.json） [/black on cyan bold][cyan][/cyan]",
                                    end="",
                                )
                                fpath = Path(input()).expanduser().resolve()
                                parent = os.path.dirname(fpath)
                                if parent:
                                    os.makedirs(parent, exist_ok=True)
                                try:
                                    with open(fpath, "w", encoding="utf-8") as f:
                                        f.write(
                                            json.dumps(
                                                context["gadgets"], ensure_ascii=False
                                            )
                                        )
                                except (PermissionError, OSError):
                                    console.print(
                                        f"[black on red] ERROR [/black on red] 无法写入 {fpath}：权限不够或路径无效。"
                                    )
                            elif ans.lower() == "r":
                                console.print(
                                    "[black on cyan bold] 输入.rop导出路径（e.g. path/to/output.rop） [/black on cyan bold][cyan][/cyan]",
                                    end="",
                                )
                                fpath = Path(input()).expanduser().resolve()
                                parent = os.path.dirname(fpath)
                                if parent:
                                    os.makedirs(parent, exist_ok=True)
                                try:
                                    with open(fpath, "w", encoding="utf-8") as f:
                                        f.write(json.dumps(context, ensure_ascii=False))
                                except (PermissionError, OSError):
                                    console.print(
                                        f"[black on red] ERROR [/black on red] 无法写入 {fpath}：权限不够或路径无效。"
                                    )
                            elif ans.lower() == "q":
                                break
                elif opera.lower() == "p":
                    console.print(
                        "[black on cyan bold] 输入.rop文件路径 [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    fpath = Path(input()).expanduser().resolve()
                    try:
                        with open(fpath, "r") as f:
                            data = f.read()
                            f.close()
                    except:
                        console.print(
                            f"[black on red] ERROR [/black on red] 找不到文件 {fpath}。"
                        )
                        continue

                    console.print(
                        "[black on cyan bold] 输入程序名 [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    name = input()
                    console.print(
                        "[black on cyan bold] 输入作者 [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    author = input()
                    console.print(
                        "[black on cyan bold] 输入机型 [/black on cyan bold][cyan][/cyan]",
                        end="",
                    )
                    model = input()
                    lines = []
                    console.print(
                        '[black on cyan bold] 输入 [/black on cyan bold] 程序描述，仅含"EOD"的一行为结束标识符。'
                    )
                    while True:
                        line = input()
                        if line == "EOD":
                            break
                        lines.append(line)

                    description = "\n".join(lines)
                    try:
                        resp = requests.post(
                            f"{BASE_URL}/api/market",
                            json={
                                "name": name,
                                "author": author,
                                "model": model,
                                "description": description,
                                "data": data,
                            },
                            timeout=10,
                        )
                        resp.raise_for_status()
                        console.print(
                            f"[black on white] LOG [/black on white] [black on green] POST [/black on green] {BASE_URL}/api/market [green]{resp.status_code} {resp.reason}[/green] 耗时 {resp.elapsed.total_seconds() * 1000}ms 喵。"
                        )
                    except requests.RequestException as e:
                        console.print(
                            f"[black on red] ERROR [/black on red] [black on green] POST [/black on green] {BASE_URL}/api/market 失败：{e}"
                        )
                        continue
                elif opera.lower() == "q":
                    break

        elif idx == 6:
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        Console().print("\n[black on yellow] 已通过 Ctrl+C 退出。[/black on yellow]")
        sys.exit(130)
    except Exception as e:
        Console().print(f"\n[black on red] ERROR [/black on red] 发生未预期的错误：{e}")
        raise
