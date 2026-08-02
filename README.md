*懒得写README了，用AI写了*
# RopIDE-Python

基于贴吧@wlyibo制作的 RopIDE 的 Python 移植版本，可以一定程度上解决浏览器抽风上传不了文件、没有网的时候无法方便地写 ROP 程序的痛苦。

## 总述

- `main.py` -> 整合所有部分，提供终端交互界面（本程序仅提供文件操作功能，无内置编辑器，需配合终端代码编辑器使用）。
- `compiler.py` -> 编译 `.rop` 文件，将汇编 DSL（`main.rin`）输出为原始十六进制字符串。
- `package.py` -> 格式处理：将代码文件、gadgets 文件、配置文件打包成 `.rop` 文件，或将 `.rop` 文件解包成这些文件。

## 安装

需要 Python 3.10+（在 3.14 上测试通过），依赖：

```bash
pip install rich hexdump2 pick pyperclip
```

复制到剪贴板功能依赖系统剪贴板工具（Linux 需要 `xclip` 或 `xsel`，macOS 自带 `pbcopy`，Windows 自带）。缺少时会提示"复制失败"!!!

## 使用

```bash
python main.py
# 找不到python，尝试python3。无python环境自己下
```

## 项目文件夹构成

```
项目根目录/
├── main.rin       # 主代码文件（即 .rop 的 input 字段）
├── gadgets.json   # gadgets 列表，JSON 数组
└── config.json    # 配置文件
```

- `main.rin`：ROP 汇编源码（见下节语法）。
- `gadgets.json` 格式示例：

```json
[{"name": "pop-er0", "addr": "121A8", "desc": "赋值 ER0", "tags": []}]
```

- `config.json` 格式：

```json
{"leftStartAddress": "E9E0", "rightStartAddress": "D710", "ideVersion": 100}
```

> 请勿更改项目文件夹里的文件名！
> 程序广场暂未开通。
> .rin的语法格式和RopIDE相同！

## Vibe-coding 情况
`compiler.compiler()`花了2个小时移植，其中的1.75小时在疯狂改bug，0.25小时在放弃并使用Vibe-coding
其他的基本上都是human-coding，除了一些`try……except`块是AI写的错误提示
然后还用了一下deepseek-v4-flash-0731查了下bug（感谢梁圣开源喵！）

## 插件

可运行`install_nvim_plugin.py`以获得nvim的.rin语法高亮喵！

## 致谢

- 原版 RopIDE：贴吧@wlyibo，网页版 https://ropide.pages.dev

