# rin.nvim

Neovim syntax highlighting and gadget completion for **RopIDE `.rin` scripts**
(fx-991CNX 计算器 ROP 程序).

高亮配色与 [rop-ide](https://ropide.pages.dev) 网页版一致
（`/home/yanshangxuan/rop-ide`，`parser.js` + `InputPanel.module.scss`）；
gadget 补全数据来自 `.rin` 项目目录下的 `gadgets.json`
（由 [ropide-python](https://github.com/human-coding/ropide-python) 生成的项目文件夹）。

## 功能

- 语法高亮：注释、常量 `$a = 1234;`、gadget `#pop-er0;`、数值块 `[expr]`、锚点 `<x>` / `<-x>`、裸 hex 字节
- 未知 gadget（不在 `gadgets.json` 中）自动标记为警告（波浪下划线），与网页版行为一致
- 补全（与 Python 补全相同的自动弹出体验）：输入 `#` 后自动弹出候选，支持 `#-` 前缀自动生成禁止 00 字节的 `#-name;` 形式
  - 自动适配 **blink.cmp**（LazyVim 默认）与 **nvim-cmp**，无需额外配置；两者均未安装时退回 `<C-x><C-o>` 全能补全
- 自动在 `.rin` 文件所在目录（及向上各级父目录）查找 `gadgets.json`
- `:RinReload` 重新加载 `gadgets.json` 并刷新高亮
- 配色自动适配主题：浅色主题按 rop-ide 网页版配色；深色主题下有效块使用接近黑色的深色底 + 亮色前景

## 要求

- Neovim 0.8+（或 Vim 8.2+）
- 需要 `filetype plugin on`（绝大多数配置默认开启）

## 安装

### lazy.nvim（推荐）

```lua
-- ~/.config/nvim/lua/plugins/rin.lua
return {
  "yourname/rin.nvim",           -- 替换为实际 GitHub 仓库地址
  ft = "rin",
  event = "VeryLazy",
  config = function() end,
}
```

或本地路径（上传 GitHub 之前）：

```lua
return {
  dir = "/home/yanshangxuan/human-coding/ropide-python/nvim",
  name = "rin",
  ft = "rin",
  config = function() end,
}
```

### vim-plug

```vim
Plug 'yourname/rin.nvim'
```

### 手动（仅加入 runtimepath）

```vim
" init.vim / init.lua
set runtimepath+=/path/to/rin.nvim
filetype plugin on
```

## 使用

打开任意 `*.rin` 文件即自动启用（文件类型自动识别，补全源自动注册）。

补全（自动弹出，与 Python 补全一致）：

1. 输入 `#` 即自动弹出 gadget 候选列表（显示 `0x地址` 与描述）
2. 输入部分名字过滤，如 `#po`
3. `<C-n>` / `<C-p>` 选择，回车插入 `#pop-er0;`
4. 前缀 `-`（输入 `#-po`）自动生成禁止 00 字节的 `#-pop-er0;`

未安装 blink.cmp / nvim-cmp 时仍可用 `<C-x><C-o>` 触发同款补全。

`gadgets.json` 修改后，在 `.rin` 缓冲区中执行：

```vim
:RinReload
```

## 高亮组

配色直接取自 rop-ide 的 `InputPanel.module.scss`，可在 colorscheme 中覆盖：

| 组 | 含义 | 颜色 |
|---|---|---|
| `rinComment` | `// 注释` | #888 斜体 |
| `rinConstantName` | 常量名 `$a` | #0b7285 |
| `rinConstantEqual` | `=` | #343a40 |
| `rinConstantValue` | 常量值 `1234` | #5c940d |
| `rinConstantWarning` | 非法常量 | + 波浪线 #d29200 |
| `rinGadgetClosed` | `#已知gadget;` | #1864ab，底色 #e7f5ff |
| `rinGadgetWarning` | `#未知gadget;` | #1864ab + 波浪线 |
| `rinGadget` | 未闭合 `#name` | #1864ab |
| `rinValueClosed` | `[表达式]` | #e67700，底色 #fff9db |
| `rinValueWarning` | `[非法内容]` | #e67700 + 波浪线 |
| `rinValue` | 未闭合 `[` | #e67700 |
| `rinAnchorClosed` | `<x>` / `<-x>` | #087f5b，底色 #e6fcf5 |
| `rinAnchor` | 未闭合 `<x` | #087f5b |
| `rinHex` | 裸 hex 字节 | 浅色主题 #000（加粗）/ 深色主题跟随 Normal |

深色主题（`&background=dark`）下自动使用深色变体：有效块底色接近黑色
（如 gadget #101f33、value #211a10、anchor #10241d），前景改用亮色
（如 #4dabf7 / #ffa94d / #63e6be），确保可读性。

## 目录结构

```
rin.nvim/
├── ftdetect/rin.vim          *.rin → filetype rin
├── syntax/rin.vim            语法定义与高亮组（浅色/深色两套配色）
├── ftplugin/rin.vim          omnifunc、commentstring、:RinReload、注册补全源
├── lua/rin/completion.lua    补全源分发（自动识别 blink.cmp / nvim-cmp）
├── lua/rin/blink.lua         blink.cmp 补全源（LazyVim 默认）
├── lua/rin/cmp.lua           nvim-cmp 补全源
└── autoload/rin/gadgets.vim  gadgets.json 解析与补全逻辑
```

## 说明

- 插件根目录为 `nvim/` 本身（即本 README 所在目录），可直接 `git init` 作为仓库上传
- 高亮为静态正则近似，常量/锚点的前向引用（`[$c + 10]` 中未定义常量）不会标警告，与网页版延迟求值略有差异
