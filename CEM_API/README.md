# CEM-API

**CasioEmuMsvc 的 Python 控制库** —— 在 Python 中启动 / 关闭 Casio 计算器模拟器、
按键、读写内存，全部接口对齐 [telecomadm1145/CasioEmuMsvc](https://github.com/telecomadm1145/CasioEmuMsvc)
的官方 **MCP 调试插件**（`McpPlugin`）。

```python
from cem import Emu, Key

emu = Emu("fx570esplus_emu")                 # model 目录或裸 ROM
emu.press(Key.KEY_ACON)                       # 按 AC/ON
emu.write(offset=0xE9E0, byte="11 45 14 19")
emu.read(offset=0xE9E0, byte=4)               # -> "11 45 14 19"
emu.kill()
```

零第三方依赖（仅 Python 标准库），支持 Python 3.8+。

---

## 目录

- [背景：CasioEmuMsvc 研究结论](#背景casioemumsvc研究结论)
- [工作原理](#工作原理)
- [安装与准备](#安装与准备)
- [快速开始](#快速开始)
- [API 参考](#api-参考)
- [键码表（kiko 编码）](#键码表kiko-编码)
- [model 目录与 ROM 打包](#model-目录与-rom-打包)
- [测试](#测试)
- [局限性与注意事项](#局限性与注意事项)

---

## 背景：CasioEmuMsvc 研究结论

`CasioEmuMsvc`（[GitHub](https://github.com/telecomadm1145/CasioEmuMsvc)）是面向
卡西欧 **nX-U8/100 与 nX-U16/100** MCU 系列（fx-ES PLUS、ClassWiz、fx-9860G、
fx-5800P 等）的高性能模拟器与逆向工程工作台，继承自 LBPHacker 的 CEM 项目。
核心特性：

| 模块 | 说明 |
| --- | --- |
| `CasioEmuMsvc/src/Chipset/` | nX-U8 / nX-U16 指令集模拟（CPU / MMU / 中断） |
| `CasioEmuMsvc/src/Peripheral/` | 键盘、LCD、定时器、RTC、UART、Flash 等外设 |
| `CasioEmuMsvc/src/Plugin/` | 插件系统：Windows 加载 `CasioEmuMsvc.Plugin.*.dll` |
| `McpPlugin/` | **MCP 调试插件**：把完整调试器暴露为 HTTP JSON-RPC |
| `PythonPlugin/` | 官方 Python 调试脚本插件（编译进模拟器） |

### MCP 插件协议（本库的通信基础）

`McpPlugin` 在模拟器进程内启动一个只绑定 `127.0.0.1` 的 HTTP 服务器：

- `POST http://127.0.0.1:3001/mcp` —— Streamable HTTP **MCP**（JSON-RPC 2.0）
- `GET  http://127.0.0.1:3001/health` —— 健康检查
- `GET  http://127.0.0.1:3001/sse` —— 旧版 SSE 端点

工具调用形如：

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call",
 "params":{"name":"read_memory","arguments":{"address":59872,"size":4}}}
```

本库只依赖 `initialize` + `tools/call` 两个方法，工具清单（源码
`McpPlugin/dllmain.cpp` 的 `ToolDefinitions()`）：

| 工具 | 用途 | 本库封装 |
| --- | --- | --- |
| `keyboard_code` | 按原始 kiko 码按键（按下/松开） | `press()` / `key_down()` / `key_up()` |
| `keyboard_key` | 按 KI/KO 矩阵坐标按键 | `keyboard_matrix()` |
| `keyboard_release_all` | 松开所有键 | `release_all_keys()` |
| `read_memory` | MMU 数据空间读字节 | `read()` / `read_bytes()` |
| `write_memory` | MMU 数据空间写字节 | `write()` / `write_bytes()` |
| `read_code` / `write_code` | ROM 代码空间读写 | `read_code()` / `write_code()` |
| `get_status` | 模型 / ROM / 暂停状态 / PC / 时钟 | `status()` |
| `pause` / `resume` / `reset` | 暂停 / 恢复 / 复位 | `pause()` / `resume()` / `reset()` |
| `step_into` / `step_over` / `step_out` | 单步调试 | `step_into()` 等 |
| `list_registers` / `read_register` / `write_register` | 寄存器 | `registers()` 等 |
| `disassemble` | 反汇编（与调试器窗口同源） | `disassemble()` |
| `list_labels` | 标签搜索 | `labels()` |
| `save_snapshot` / `load_snapshot` / `delete_snapshot` | 快照 | `save_snapshot()` 等 |
| `add_memory_breakpoint` 等 | 内存监视 / 断点 | `add_memory_breakpoint()` 等 |
| `set_cycles_per_second` / `raise_interrupt` / `hot_reload_rom` | 硬件控制 | 同名方法 |

> 注意：MCP 插件在 `CMakeLists.txt` 中仅对 **Windows** 构建启用
> （`if(WIN32 AND BUILD_EXECUTABLE AND BUILD_MCP_PLUGIN)`），且桌面 Linux
> 版的 `LoadPlugins()` 为空实现。因此本库面向 **Windows 发行版**
> （`CasioEmuMsvc.exe` + `CasioEmuMsvc.Plugin.McpPlugin.dll`）。

### 模拟器启动方式

`CasioEmuMsvc.exe` 接受 `key=value` 命令行参数（源码 `casioemu.cpp`）：

```text
CasioEmuMsvc.exe <model目录> paused=1
```

`paused=1` 表示启动后暂停 CPU（适合调试 / 脚本化使用）。MCP 官方冒烟测试
（`McpPlugin/test_mcp.ps1`）即用此方式启动 `models\fx-JP900CW_emu`。

---

## 工作原理

```
┌───────────────────────┐   JSON-RPC 2.0 (HTTP, 127.0.0.1:3001)   ┌──────────┐
│  CasioEmuMsvc.exe     │ ◄──────────────────────────────────────► │  cem 库   │
│  ├ model 目录          │        /mcp  tools/call                   │  Emu      │
│  └ McpPlugin.dll (MCP)│                                          │  Key      │
└───────────────────────┘                                          └──────────┘
```

`Emu` 实例化时：

1. 解析可执行文件（`exe=` 参数 → `CASIOEMU_EXE` 环境变量 → 当前目录 / PATH）
2. 解析 model：传入目录 → 直接使用；传入裸 ROM 文件 → 自动打包成 model 目录
   （`~/.cache/cem-api/models/<sha1>-<name>/`）
3. 以 `model=<目录> paused=1` 启动模拟器进程
4. 轮询 `/health` 直到 MCP 服务就绪
5. `initialize` 建立 MCP 会话
6. 读取 model 的 `config.json` 按钮表（支持按键名调用）

---

## 安装与准备

### 1. 获取模拟器

Windows 上从 [GitHub Releases](https://github.com/telecomadm1145/CasioEmuMsvc/releases)
下载 `windows-x64-*.zip`，解压出 `CasioEmuMsvc.exe` 与
`CasioEmuMsvc.Plugin.McpPlugin.dll`（二者必须同目录），或用仓库自带脚本：

```bash
python tools/fetch_release.py            # 自动下载到 CEM-API/bin/
python tools/fetch_release.py --tag stable-20260808170455-9a586c3
```

### 2. 准备 model 目录

`Emu` 接受两种输入：

- **model 目录**：包含 `config.json`（或 `config.bin`）+ ROM + `interface.png`。
  官方模型（`fx-JP900CW_emu` 等）随模拟器发行包提供；
- **裸 ROM 文件**（`.bin`）：自动合成 model 目录，默认按 ES PLUS/ClassWiz
  通用布局生成按钮表与空白外观图。

### 3. 本库

```bash
pip install -e .        # 可选；也可以直接把 CEM-API 目录加入 PYTHONPATH
```

无需任何第三方依赖。

---

## 快速开始

```python
from cem import Emu, Key

with Emu("fx570esplus_emu", paused=False) as emu:
    # 开机并等待引导完成
    emu.power_on(hold=1.0)
    emu.wait_boot()

    # 内存写入 / 读取（核心 API）
    emu.write(offset=0xE9E0, byte="11 45 14 19")
    data = emu.read(offset=0xE9E0, byte=4)
    assert data == "11 45 14 19"

    # 按键：支持 键码(int) / Key 常量 / model 键名(str)
    emu.press(Key.KEY_ACON)      # AC/ON
    emu.press("1")
    emu.press(Key.KEY_ADD)
    emu.press("2")
    emu.press(Key.KEY_EXE)

    # 读取屏幕显存判断界面状态
    buf = emu.screen_buffer()

    # 挂接已运行的模拟器（端口被占用时）
# 退出 with 块自动 kill()
```

指定可执行文件：

```python
emu = Emu("fx570esplus_emu", exe=r"D:\emu\CasioEmuMsvc.exe")
# 或设置环境变量 CASIOEMU_EXE
```

---

## API 参考

### `Emu(rom_file, ...)`

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `rom_file` | 必填 | model 目录 或 裸 ROM 文件 |
| `exe` | 自动查找 | 模拟器可执行文件路径 |
| `port` | `3001` | MCP 端口 |
| `paused` | `True` | 启动后暂停 CPU |
| `hold` | `0.08` | `press()` 按住时长（秒） |
| `timeout` | `60.0` | 等待 MCP 就绪超时 |
| `attach` | `False` | 端口已被占用时挂接现有实例 |
| `logfile` | `None` | 模拟器输出重定向文件 |
| `env` / `workdir` | — | 子进程环境 / 工作目录 |

**核心 API（与需求规格一一对应）**

```python
Emu(rom_file)                          # 创建并启动模拟器
emu.kill()                             # 关闭模拟器
emu.press(keycode)                     # 按一下键（可传 Key.KEY_* 或 int）
emu.write(offset=0xE9E0, byte="11 45 14 19")   # 写入字节
emu.read(offset=0xE9E0, byte=4) -> "11 45 14 19"  # 读取并返回 hex 字符串
```

**按键**

| 方法 | 说明 |
| --- | --- |
| `press(keys, hold=None, interval=0.1)` | 按一下键；支持空格分隔序列 `"shift 9 3 = ac"` |
| `key_down(key)` / `key_up(key)` | 按住 / 松开 |
| `release_all_keys()` | 松开所有键 |
| `keyboard_matrix(ki, ko, pressed)` | KI/KO 矩阵坐标按键 |

**开机 / 运行状态**

| 方法 | 说明 |
| --- | --- |
| `power_on(hold=1.0, wait=True)` | 按电源键 (0xFF) 开机；`wait=True` 时顺带等待引导 |
| `wait_boot(timeout=30)` | 轮询显存直到引导完成（适合按键/注入前调用） |
| `screen_buffer(size=None)` | 读取屏幕显存（0xF800）原始字节 |

**屏幕（异步采样 / 盲文 TUI）**

| 方法 | 说明 |
| --- | --- |
| `start_screen(interval=0.15)` | 后台线程异步采样显存，返回 `ScreenView` |
| `emu.screen.text()` | 最新帧的盲文渲染文本（192×63 → 96×16 字符） |
| `emu.screen.status()` | 状态栏文本（DEG/MATH/SUN...，帧内偏移字节第 0 位） |
| `emu.screen.wait_change(timeout)` | 等待画面变化 |
| `showscreen(interval=0.15, out=None)` | **终端 TUI**：异步循环重绘屏幕，**不阻塞** press/write 等调用，返回 `ScreenTUI`（`.stop()` 停止） |
| `hidescreen()` | 停止 TUI 打印（采样线程保留） |

盲文渲染对齐 CasioEmuMsvc 的 `Screen.cpp`：点阵 63 行（第 0 行为状态栏），
每行 32 字节只显示前 24 字节（192 像素），每字节 MSB 为最左像素；
每个盲文字符 = 2 列 × 4 行像素（U+2800 系列 8 点）。headless 模式下同样可用。

状态栏：每个状态图标 = 0xF800 帧内某字节（偏移 0x00..0x16）的第 0 位
（对齐 `Screen.cpp` 的 `sprite_bitmap`），例如 `D`=DEG(0x06)、`MATH`(0x05)、
`SUN`(0x16)、`A`=ALPHA(0x01)、`M`(0x02)、`STO`(0x03) 等。

**内存**

| 方法 | 说明 |
| --- | --- |
| `read(offset, byte=4)` | 读 `byte` 字节 → `"11 45 14 19"` |
| `read_bytes(offset, size)` | 读 → `bytes` |
| `write(offset, byte="")` | 写 hex 字符串 / `bytes` / int 列表 |
| `write_bytes(offset, data)` | 写 `bytes` |
| `read_code(offset, count)` | 读代码空间 16-bit 指令字 |
| `write_code(offset, byte)` | 向 ROM 打补丁 |

**调试**

`status()` · `pause()` · `resume()` · `reset()` · `step_into()/step_over()/step_out()`
· `registers()` · `read_register(name)` · `write_register(name, value)` ·
`disassemble(address, count)` · `backtrace()` · `labels(query)`

**断点 / 快照 / 硬件**

`add_execution_breakpoint(addr)` · `add_memory_breakpoint(addr, write, break_when_hit)`
· `remove_memory_breakpoint(addr, write)` · `clear_memory_breakpoints()` ·
`list_snapshots()` · `save_snapshot(label)` · `load_snapshot(id)` ·
`delete_snapshot(id)` · `set_cycles_per_second(cps)` · `raise_interrupt(index)` ·
`hot_reload_rom()`

**属性**

| 属性 | 说明 |
| --- | --- |
| `emu.buttons` | model 按钮表 `{键名: kiko码}`（来自 config.json 或 config.bin） |
| `emu.running` | 进程是否存活 |
| `emu.model_dir` / `emu.exe` / `emu.port` | 基本信息 |

> **attach 模式**：`Emu(attach=True)` 挂接已在运行的模拟器，无需提供
> `rom_file`；此时按键名表为空，`press()` 请使用键码 / `Key` 常量，
> 或同时传入 `model_dir=` 以加载按钮表。

**异常**（`cem.exceptions`）

`CemError`（基类）→ `McpError` / `ToolError` / `EmulatorNotFound` /
`EmulatorStartFailed` / `EmulatorNotRunning` / `InvalidKeyError` /
`PortBusyError` / `ModelConfigError`

---

## 键码表（kiko 编码）

CasioEmuMsvc / 原版 CEM 家族使用统一的 **kiko** 键码：
`code = (KO << 4) | KI`（键盘矩阵输出行 × 输入列）。取值在
ES PLUS / ClassWiz / fx-9860G 家族中一致，来自两个独立模型配置的核实
（原版 CEM `models/fx570esplus/model.lua` 与 CasioEmuX `models/fx991cnx/model.lua`）。

```python
from cem import Key

Key.KEY_0    # 0x64   Key.KEY_1~KEY_9   # 0x00 0x10 0x20 0x01 0x11 0x21 0x02 0x12 0x22
Key.KEY_DOT  # 0x63   Key.KEY_EXP       # 0x35 ('^' 乘方)   Key.KEY_X10 # 0x62 (×10ˣ)
Key.KEY_ADD  # 0x30   Key.KEY_SUB       # 0x40   Key.KEY_MUL # 0x31   Key.KEY_DIV # 0x41
Key.KEY_EXE  # 0x60   Key.KEY_ACON      # 0x42   Key.KEY_DEL # 0x32
Key.KEY_UP   # 0x27   Key.KEY_DOWN      # 0x36   Key.KEY_LEFT# 0x26   Key.KEY_RIGHT # 0x37
Key.KEY_F1..KEY_F8                      # 0x07 0x17 0x47 0xFF 0x06 0x16 0x46 0x56
Key.KEY_POWER                            # 0xFF（部分模型名为 F4）
```

### 通俗表示（fx-991CN X / CWZ.N）

按键可直接用**通俗名字符串**调用，大小写不敏感，并支持**空格分隔的连续按键**：

```python
emu.press("POWER")                # 开机键 (0xFF)
emu.press("sin")                  # 三角函数
emu.press("M+")                   # 存储
emu.press("SHIFT")                # 上档键
emu.press("×")                    # 乘号（也接受 "*" "/" "+" "-" "=" "(" ")"）
emu.press("shift 9 3 = ac")       # 空格分隔，依次按下每个键
emu.press("sin ( 1 + 2 )", interval=0.4)   # interval: 键间间隔（秒）
```

键码表来自 fx-991CN X 键码矩阵（16 位键码 `0xKO:KI`，KI=行扫描、KO=列返回；
换算为 kiko：`列号<<4 | 行号`），按键名取自 CWZ.N→ASCII 转换器：

| 通俗名 | 常量 | kiko | 键码矩阵 |
| --- | --- | --- | --- |
| POWER / ON | `KEY_POWER` | 0xFF | 电源键 |
| SHIFT | `KEY_SHIFT` | 0x07 | 80 01 |
| ALPHA | `KEY_ALPHA` | 0x17 | 80 02 |
| MENU | `KEY_MENU` | 0x47 | 80 10 |
| OPTN | `KEY_OPTN` | 0x06 | 40 01 |
| CALC | `KEY_CALC` | 0x16 | 40 02 |
| INT | `KEY_INT` | 0x46 | 40 10 |
| X | `KEY_X` | 0x56 | 40 20 |
| FRAC | `KEY_FRAC` | 0x05 | 20 01 |
| SQRT | `KEY_SQRT` | 0x15 | 20 02 |
| SQ (x²) | `KEY_SQ` | 0x25 | 20 04 |
| EXP (^) | `KEY_EXP` | 0x35 | 20 08 |
| LOG | `KEY_LOG` | 0x45 | 20 10 |
| LN | `KEY_LN` | 0x55 | 20 20 |
| NEGA (±) | `KEY_NEGA` | 0x04 | 10 01 |
| DMS | `KEY_DMS` | 0x14 | 10 02 |
| RECI (x⁻¹) | `KEY_RECI` | 0x24 | 10 04 |
| SIN | `KEY_SIN` | 0x34 | 10 08 |
| COS | `KEY_COS` | 0x44 | 10 10 |
| TAN | `KEY_TAN` | 0x54 | 10 20 |
| STO | `KEY_STO` | 0x03 | 08 01 |
| ENG | `KEY_ENG` | 0x13 | 08 02 |
| ( | `KEY_LPAREN` | 0x23 | 08 04 |
| ) | `KEY_RPAREN` | 0x33 | 08 08 |
| S↔D | `KEY_S2D` | 0x43 | 08 10 |
| M+ | `KEY_MPLUS` | 0x53 | 08 20 |
| ×10ˣ | `KEY_X10` | 0x62 | 04 40 |
| ANS | `KEY_ANS` | 0x61 | 02 40 |

**CWZ.N 别名**（与主名同键，大小写不敏感）：`dfm`=dms、`jf`=int、
`fs`=frac、`gh`=sqrt、`pf`=sq、`cf`=exp、`fu`=nega、`ds`=reci、
`times`/`cheng`=×、`chu`=÷、`plus`/`jia`=+、`sub`/`jian`=−、
`dot`=.、`del`=DEL、`ac`=AC、`on`/`power`=开机、`x10`=×10ˣ、`ans`=ANS。

> **解析优先级**：字符串键先查通俗表示表（`Key`，如 `"="`、`"sin"`、`"POWER"`），
> 查不到再查 model 按钮表。部分旧版 model 配置用 SDL 键名（如 0x30 记为 `'='`、
> 0x42 记为 `'Space'`），与真实键位不符，因此以通俗表示为准；model 独有的键名
> （如 `"AC/ON"`、`"F1"`）仍可直接使用。
> 注：CNX 上 `KEY_F1..F8` 实际对应 SHIFT/ALPHA/MENU/电源/OPTN/CALC/INT/X；
> ES PLUS 等其它型号的按键名以 model 的 config 按钮表为准（`emu.buttons`）。

---

## model 目录与 ROM 打包

`CasioEmuMsvc` 通过 `config.json` 描述模型（字段要求来自源码
`ModelConfig.cpp` 的 `RequireBaseModelFields` / `RequireSpriteModelFields`）：

```json
{
  "format": "CasioEmuMsvc.ModelInfo",
  "model_name": "fx-570ES PLUS",
  "hardware_id": 3,
  "csr_mask": 1,
  "real_hardware": false,
  "pd_value": 0,
  "interface_path": "interface.png",
  "rom_path": "rom.bin",
  "flash_path": "",
  "ink_color": {"r": 30, "g": 52, "b": 90},
  "enable_new_screen": false,
  "is_sample_rom": false,
  "legacy_ko": false,
  "u16_mode": false,
  "large_model": false,
  "ml620_mirroring": false,
  "buttons": [{"kiko": 0, "keyname": "1", "rect": {"x": 46, "y": 658, "w": 58, "h": 41}}],
  "sprites": {
    "rsd_interface": {"src": {"x": 0, "y": 0, "w": 410, "h": 810},
                      "dest": {"x": 0, "y": 0, "w": 410, "h": 810}}
  }
}
```

- `hardware_id`：3=ES PLUS、4=ClassWiz、5=ClassWiz II、6=fx-5800P、8=Solarn II
- `rom.bin` 为固件镜像；`flash_path` 可为空（ES PLUS 家族）
- `interface.png` 是 GUI 渲染用的外观图（可空白）
- 裸 ROM 文件传入 `Emu()` 时，`cem.romfile.make_model_dir()` 自动完成上述打包；
  也可直接调用该函数手动生成：`make_model_dir("rom.bin", "out/model")`
- **注意**：裸 ROM 合成默认按 ES PLUS（`hardware_id=3`）打包。ROM 的硬件平台
  必须与 `hardware_id` 匹配（例如 ClassWiz ROM 需要 `hardware_id=4`，且通常
  还需要 flash），否则内存映射会错乱或启动失败。**优先使用官方 model 目录**，
  裸 ROM 合成适用于没有配置文件的场景。
- 旧版 model 目录（只有 `config.bin`）同样支持：按钮表可从二进制的
  `ModelInfo v52` 格式解析（`cem.romfile.parse_config_bin`），
  已用真实 fx-991CNX 模型验证。

---

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖：hex 字符串解析、键码表核实、model 目录生成（含 PNG 校验）、
config.bin 二进制按钮表解析、MCP 客户端生命周期 / 内存往返 / 工具错误，
以及用**假模拟器进程**跑完整 `Emu` 生命周期（启动 → health → 按键 → 读写 →
attach → kill）。

有真实模拟器时（Windows 发行版，或本仓库打上 POSIX 插件加载补丁后自行构建）
还可运行真实端到端测试：

```bash
CASIOEMU_EXE=/path/to/CasioEmuMsvc python -m unittest tests.test_emu_real -v
# 可选的模型目录: CASIOEMU_MODEL=/path/to/model_dir
```

本库已在真实 CasioEmuMsvc（Linux 构建 + McpPlugin.so）上完成验证：
fx-991CN X 模型的内存写入/读取往返、按键（码/常量/键名/hex 字符串）、
寄存器读写、单步执行、反汇编均通过。

---

## 无窗口（headless）运行

不弹模拟器窗口，但 MCP 操控、显存读取、内存读写全部照常：

```python
emu = Emu("fx991cnx", exe="...", headless=True)   # 不弹窗口
emu.power_on(); emu.wait_boot()
emu.press("sin ( 1 + 2 )", interval=0.4)
```

**原理**：给模拟器进程注入 SDL 环境变量 `SDL_VIDEODRIVER=dummy` +
`SDL_RENDER_DRIVER=software`，SDL 在无显示环境下运行。已在 Linux 真机验证：
开机、引导检测（显存 0xF800）、按键、内存读写全部正常。

注意事项：

- Linux / macOS：直接可用。
- Windows：SDL 2.0.22+ 支持 dummy 驱动，理论上可用，需实测（若渲染器创建
  失败会启动报错，此时去掉 `headless=True` 即可，或改用 Xvfb 类方案）。
- 无窗口时看不到屏幕，但 `screen_buffer()`（显存）与 `wait_boot()` 不受影响。
- 用户显式传入的 `env=` 参数优先于 headless 注入的变量。

---

## 局限性与注意事项

1. **平台**：MCP 插件仅随 Windows 构建发布（`McpPlugin` 使用 winsock，
   `CMakeLists.txt` 仅对 `WIN32` 添加）；桌面 Linux/macOS 版无插件加载器。
   本库的 `McpClient` / `Emu` 协议层与平台无关，可在任意平台编写脚本，
   实际运行需 Windows 模拟器。
2. **单实例**：McpPlugin 固定监听 `127.0.0.1:3001`（源码硬编码），同一时刻
   只能运行一个模拟器实例；再启动第二个会得到 `PortBusyError`，可用
   `attach=True` 挂接第一个。
3. **`paused` 参数特性（重要）**：CasioEmuMsvc 源码
   （`Emulator.cpp`）只要 argv 中**存在** `paused` 参数就会暂停 CPU，
   `paused=0` 无效。因此本库在 `paused=False` 时**不传**该参数，
   在 `paused=True` 时传 `paused=1`。
4. **nX-U8 机型上 PC/寄存器不可靠**：MCP 插件的 `get_status`/`registers`
   读取的是从未执行的 JIT CPU（`ePSCPU`，仅 EPS6800 使用），数值是无效的。
   按键/内存/暂停/复位/断点/快照不受影响。判断运行状态请用
   `screen_buffer()`（显存 0xF800）或内存读写。
5. **开机流程**：模拟器启动后 CPU 立即运行（从复位向量引导）。
   推荐先 `power_on()`（按电源键 0xFF，触发 `chipset.Reset()` 开机），
   再 `wait_boot()`（轮询显存直到引导完成），最后注入/按键 ——
   否则引导期间的输入会被系统初始化过程吞掉。
6. **键码按模型**：kiko 码在 ES PLUS / ClassWiz 家族一致，但个别型号可能不同；
   以 `emu.buttons`（来自 model config）为准。
7. `press()` 是"按下-停留-松开"的一次点击；连续输入建议使用 `key_down/up`
   自己控制时序，或适当加大 `hold`，并在按键之间留出间隔。
8. ROM 版权：请只使用你拥有权利的固件。

## 相关链接

- CasioEmuMsvc: https://github.com/telecomadm1145/CasioEmuMsvc
- 原版 CEM (LBPHacker): https://github.com/LBPHacker/CasioEmu
- CasioEmuX (含多种 model 配置): https://github.com/coder114514/CasioEmuX-win
- MCP 协议: https://modelcontextprotocol.io
