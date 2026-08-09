# u8emu-py

A lightweight Python port of **CasioEmuMsvc** — an nX-U8/100 calculator emulator.
Pure curses TUI (no SDL/ImGui), LCD rendered with Braille block characters, keyboard
directly mapped to calculator keys, with a first-class plugin interface
(RAM read/write, freeze/patch, hooks, key sequences, JSON-RPC).

Thanks to Tieba user **@噶么prince** for open-sourcing **CasioEmuMsvc** — the
foundation of this emulator (and of the built-in emulator used by
[RopIDE-Python](https://github.com/human-coding/ropide-python) for debugging).


## Features

- Models: fx-991CN X **VerF / VerC** (verified: boots to main screen, key input, standby, RPC/plugin), fx-991ES PLUS (structural, key matrix placeholder), generic
- LCD rendering: braille / half-block / ASCII styles
- TUI commands: memory read/write, RAM freeze & patch panel (F4), breakpoints, snapshots, key logging
- KeySequencer: timed key sequences (`keys 1 + 2 =`, repeats, waits, raw keycodes)
- Plugin API + JSON-RPC line protocol, headless mode
- Performance: CPython ~1.15 MIPS / PyPy ~10.8 MIPS (real device 2.097 MHz)

## Installation

Requires **Python 3.9+**. No third-party dependencies (stdlib + curses; Windows needs `pip install windows-curses`).

```bash
cd u8emu_py
pip install .           # installs the `u8emu` command
# or run from source without installing:
python3 -m u8emu ...
```

## Usage

```bash
python3 -m u8emu path/to/rom.bin -m fx991cnxf --vscale 2
# PyPy is much faster (~10 MIPS): ~/pypy3/bin/pypy3 -m u8emu path/to/rom.bin -m fx991cnxf
```

Basic keys: `1`-`9`, `+ - / . =` input, `Enter` = EXE, `Esc` = DEL, `Space` = AC, `S`/`A`/`M` = SHIFT/ALPHA/MENU, `q` quit. TUI shortcuts: `F1` pause · `F2` step · `F4` RAM patch panel · `:` command line (`r 8000` read, `w 8000 12 34` write, `freeze`/`unfreeze`, `keys 1 + 2 =`).

Use as a library (the API RopIDE uses for debugging):

```python
from u8emu.cnxemu import Cnxemu
cnx = Cnxemu().load("rom.bin")
cnx.write(off=0xE9E0, byte="11 45 14 19")
cnx.press("1 + 2 =")
print(cnx.showram(0xD180, 16))
cnx.kill()
```

Full CLI options: `python3 -m u8emu --help`.

## Acknowledgements

- Original project: **CasioEmuMsvc** by Tieba user @噶么prince (GPL-3.0)

> 简体中文(SC)

**CasioEmuMsvc** 的 Python 轻量移植版 —— nX-U8/100 计算器模拟器。
纯 curses TUI（无 SDL/ImGui），LCD 用盲文点阵字符渲染；键盘直接映射计算器按键；
插件接口（RAM 读写 / 即时覆写 / Hook / 键码按键 / JSON-RPC）为一级公民。

感谢贴吧 **@噶么prince** 开源 **CasioEmuMsvc** —— 本模拟器（以及
[RopIDE-Python](https://github.com/human-coding/ropide-python) 内置调试模拟器）的基础。
## 特性

- 机型：fx-991CN X **VerF / VerC**（已验证：冷启动进主屏、按键输入、待机唤醒、RPC/插件全链路）、fx-991ES PLUS（结构正确，键盘矩阵为占位）、generic
- LCD 渲染：盲文 / 半块 / ASCII 三种风格
- TUI 命令：内存读写、RAM 即时覆写与补丁面板（F4）、断点、快照、按键日志
- KeySequencer：按键序列（`keys 1 + 2 =`、重复、等待、裸键码）
- 插件 API + JSON-RPC 行协议，支持 headless 模式
- 性能：CPython ~1.15 MIPS / PyPy ~10.8 MIPS（实机 2.097MHz）

## 安装

需要 **Python 3.9+**。无第三方依赖（仅标准库 + curses；Windows 需 `pip install windows-curses`）。

```bash
cd u8emu_py
pip install .           # 安装 u8emu 命令
# 或直接源码运行：
python3 -m u8emu ...
```

## 使用

```bash
python3 -m u8emu path/to/rom.bin -m fx991cnxf --vscale 2
# PyPy 快得多（~10 MIPS）：~/pypy3/bin/pypy3 -m u8emu path/to/rom.bin -m fx991cnxf
```

基础按键：`1`-`9`、`+ - / . =` 输入，`Enter`=EXE，`Esc`=DEL，`Space`=AC，`S`/`A`/`M`=SHIFT/ALPHA/MENU，`q` 退出。TUI 快捷键：`F1` 暂停 · `F2` 单步 · `F4` RAM 补丁面板 · `:` 命令行（`r 8000` 读、`w 8000 12 34` 写、`freeze`/`unfreeze`、`keys 1 + 2 =`）。

作为库使用（即 RopIDE 调试所用 API）：

```python
from u8emu.cnxemu import Cnxemu
cnx = Cnxemu().load("rom.bin")
cnx.write(off=0xE9E0, byte="11 45 14 19")
cnx.press("1 + 2 =")
print(cnx.showram(0xD180, 16))
cnx.kill()
```

完整命令行参数：`python3 -m u8emu --help`。

## 致谢

- 原项目：贴吧@噶么prince 的 **CasioEmuMsvc**（GPL-3.0）
