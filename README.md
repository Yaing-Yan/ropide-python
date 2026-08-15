# RopIDE-Python

> English

Based on the RopIDE created by Tieba user @wlyibo, this is a Python port that can somewhat solve the frustrations of being unable to upload files due to browser issues and not being able to conveniently write ROP programs without an internet connection.

## Features

* Create/open ROP project folders and manage `main.rin`, `gadgets.json`, and `config.json`
* Compile `.rop` files (assembly DSL → hexadecimal strings), with hexdump preview and one-click copying
* Convert between `.rop` files and project folders
* Built-in CASIO fx-991 CN X VerF / VerC two gadget presets
* Program Square (online program fetching/uploading, requires internet access)
* Companion Neovim plugin: `.rin` syntax highlighting + gadget completion

## Installation

Requires **Python 3.10+** (tested successfully on Python 3.14):

```bash
pip install rich hexdump2 pick pyperclip requests
```

* Clipboard support depends on system utilities: Linux requires `xclip` or `xsel`; macOS and Windows have them built in. If unavailable, the program will display a "copy failed" message.
* Windows users need to additionally install curses support (required by the `pick` menu):

```bash
pip install windows-curses
```

* All file I/O uses UTF-8 encoding. When reading files, it automatically supports GBK-encoded files created by older versions on Chinese Windows systems.

## Usage

```bash
python main.py    # Try python3 if python is unavailable
```

Compile a single file from the command line:

```bash
python compiler.py path/to/file.rop
```

## Build executables

Build standalone executables for the **current platform** with `make`:

```bash
make                          # build both: dist/main + dist/install_nvim_plugin
make main                     # build only main
make install_nvim_plugin      # build only install_nvim_plugin
make clean                    # remove build/ dist/ __pycache__
make help                     # show help
```

`make` automatically installs PyInstaller and any missing third-party dependencies, then builds every root-level `*.spec` into `dist/`. Use a specific interpreter with `make PYTHON=python3.12`.

> `build.sh` is still available for multi-platform releases (Linux x86-64/x86-32/arm64, Windows x86-64/x86-32 via Docker/Wine).

## Project Folder Structure

```
Project Root/
├── main.rin       # ROP assembly source code (the input field of .rop)
├── gadgets.json   # Gadget list, JSON array
└── config.json    # Configuration file
```

> This program only provides file management functionality. It **does not include a built-in editor** and should be used with terminal-based code editors (such as vim/nvim).
> Do not rename files inside the project folder!
> The `.rin` syntax is the same as RopIDE.

## Neovim Plugin

Run the following script to enable `.rin` syntax highlighting and gadget completion:

```bash
python3 install_nvim_plugin.py
```

It automatically detects lazy.nvim or installs via symlink. Supports parameters such as `--repo`, `--dry-run`, and `--uninstall`. See the script documentation for details.

## About Vibe Coding

The `compiler.compiler()` migration took 2 hours. Of that time, about 1.75 hours were spent frantically fixing bugs, while 0.25 hours were spent giving up and using Vibe Coding. Almost everything else was done through human coding, except for some `try...except` blocks where AI generated error messages. I also used DeepSeek-v4-flash-0731 to investigate some bugs.

(Thanks to @Liangsheng for open-sourcing this project!)

## Acknowledgements

* Original RopIDE: Tieba user @wlyibo
  Web version: [https://ropide.pages.dev](https://ropide.pages.dev)
* Emulator foundation: CasioEmuMsvc source project by Tieba user @噶么prince (the built-in emulator `u8emu_py` is a Python port of it)

> 简体中文(SC)

基于贴吧@wlyibo制作的 RopIDE 的 Python 移植版本，可以一定程度上解决浏览器抽风上传不了文件、没有网的时候无法方便地写 ROP 程序的痛苦。## 功能

- 创建/打开 ROP 项目文件夹，管理 `main.rin`、`gadgets.json`、`config.json`
- 编译 `.rop` 文件（汇编 DSL → 十六进制字符串），支持 hexdump 预览与一键复制
- `.rop` 文件与项目文件夹互转
- 内置 CASIO fx-991 CN X VerF / VerC 两套 gadgets 预设
- 程序广场（在线获取/上传程序，需联网）
- 配套 Neovim 插件：`.rin` 语法高亮 + gadgets 补全

## 安装

需要 **Python 3.10+**（在 3.14 上测试通过）：

```bash
pip install rich hexdump2 pick pyperclip requests
```

- 剪贴板复制依赖系统工具：Linux 需要 `xclip` 或 `xsel`，macOS/Windows 自带。缺少时程序会提示"复制失败"。
- Windows 用户需额外安装 curses 支持（`pick` 菜单依赖）：`pip install windows-curses`
- 所有文件读写统一使用 UTF-8；读取时会自动兼容旧版本在中文 Windows 上写出的 GBK 文件。

## 使用

```bash
python main.py    # 找不到 python 就试 python3
```


命令行编译单个文件：

```bash
python compiler.py path/to/file.rop
```

## 构建可执行文件

用 `make` 为**当前平台**构建独立可执行文件：

```bash
make                          # 构建全部: dist/main + dist/install_nvim_plugin
make main                     # 只构建 main
make install_nvim_plugin      # 只构建 install_nvim_plugin
make clean                    # 清理 build/ dist/ __pycache__
make help                     # 查看帮助
```

`make` 会自动安装 PyInstaller 及缺失的第三方依赖，然后把根目录每个 `*.spec` 构建到 `dist/`。指定解释器：`make PYTHON=python3.12`。

> 多平台发布仍可用 `build.sh`（Linux x86-64/x86-32/arm64、Windows x86-64/x86-32，走 Docker/Wine）。

## 项目文件夹构成

```
项目根目录/
├── main.rin       # ROP 汇编源码（即 .rop 的 input 字段）
├── gadgets.json   # gadgets 列表，JSON 数组
└── config.json    # 配置文件
```

> 本程序仅提供文件操作功能，**无内置编辑器**，需配合终端代码编辑器（如 vim/nvim）使用。
> 请勿更改项目文件夹里的文件名！
> .rin 语法（与 RopIDE 相同）

## Neovim 插件

运行以下脚本可获得 `.rin` 语法高亮与 gadgets 补全：

```bash
python3 install_nvim_plugin.py
```

自动检测 lazy.nvim 或直接软链安装，支持 `--repo`、`--dry-run`、`--uninstall` 等参数，详见脚本内文档。

## 关于Vibe Coding
`compiler.compiler()`花了2个小时移植，其中的1.75小时在疯狂改bug，0.25小时在放弃并使用Vibe-coding 其他的基本上都是human-coding，除了一些`try……except`块是AI写的错误提示然后还用了一下deepseek-v4-flash-0731查了下bug（感谢梁圣开源喵！）

## 致谢

- 原版 RopIDE：贴吧@wlyibo，网页版 https://ropide.pages.dev
- 模拟器基础：贴吧@噶么prince 的 CasioEmuMsvc 源码项目（内置模拟器 `u8emu_py` 为其 Python 移植版）
