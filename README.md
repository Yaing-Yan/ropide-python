*依旧AI写README*
# RopIDE-Python

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

`gadgets.json` 格式示例：

```json
[{"name": "pop-er0", "addr": "121A8", "desc": "赋值 ER0", "tags": []}]
```

`config.json` 格式：

```json
{"leftStartAddress": "E9E0", "rightStartAddress": "D710", "ideVersion": 100}
```

## 程序广场

**我们终于适配了程序广场！**

程序广场对接网页版 RopIDE 的 API（`https://ropide.pages.dev/api/market`），需要联网。进入后有三种操作（输入首字母，如 `g` / `p` / `q`）：

**G — 获取程序列表**
- 请求 `GET /api/market`，按 id 倒序排列，以表格展示：编号、名称、作者、机型、描述
- 输入程序编号可下载单个程序（`GET /api/market?id=<编号>`），下载后可选：
  - `g` — 提取 gadgets，导出为 gadgets.json 文件
  - `r` — 导出整个 `.rop` 文件
  - `q` — 返回
- 导出时可输入任意路径，自动创建缺失的父目录

**P — 上传程序**
- 输入本地 `.rop` 文件路径，再依次输入程序名、作者、机型
- 描述为多行输入，单独一行 `EOD` 作为结束标识
- 通过 `POST /api/market` 提交（字段：`name` / `author` / `model` / `description` / `data`）

**q — 退出**，返回主菜单

所有请求均有 10 秒超时，网络失败、非 JSON 响应、数据格式异常都会打印错误提示并返回，不会中断程序。

## Neovim 插件

运行以下脚本可获得 `.rin` 语法高亮与 gadgets 补全：

```bash
python3 install_nvim_plugin.py
```

自动检测 lazy.nvim 或直接软链安装，支持 `--repo`、`--dry-run`、`--uninstall` 等参数，详见脚本内文档。

## 开发说明

- `main.py`：终端交互主程序（菜单、文件操作、程序广场）
- `compiler.py`：核心编译器，将 `.rin` 汇编 DSL 编译为十六进制字符串
- `package.py`：`.rop` 文件的打包/解包与文本读取（UTF-8/GBK 兼容）

## 关于Vibe Coding
`compiler.compiler()`花了2个小时移植，其中的1.75小时在疯狂改bug，0.25小时在放弃并使用Vibe-coding 其他的基本上都是human-coding，除了一些`try……except`块是AI写的错误提示然后还用了一下deepseek-v4-flash-0731查了下bug（感谢梁圣开源喵！）

## 致谢

- 原版 RopIDE：贴吧@wlyibo，网页版 https://ropide.pages.dev
