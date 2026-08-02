#!/usr/bin/env python3
"""在 ropide-python 项目下安装 rin.nvim 插件（.rin 语法高亮 + gadgets 补全）。

自动检测 Neovim 配置目录与插件管理器：

1. lazy.nvim / LazyVim（存在 <config>/lua/plugins/）：
   写入 <config>/lua/plugins/rin.lua 规格文件（默认指向本地 nvim/ 目录，
   可用 --repo 改用 GitHub 仓库地址）。
2. 其他情况（无插件管理器）：
   将插件目录软链到 <config>/rin.nvim，并在 init.lua/init.vim 中追加
   runtimepath 配置（没有 init 文件时自动创建 init.lua）。

用法:
  python3 install_nvim_plugin.py                 # 自动检测并安装（本地路径）
  python3 install_nvim_plugin.py --repo human-coding/rin.nvim   # 使用 GitHub 仓库
  python3 install_nvim_plugin.py -y              # 已存在时静默覆盖
  python3 install_nvim_plugin.py --dry-run       # 仅预览将要执行的操作
  python3 install_nvim_plugin.py --uninstall     # 卸载（移除规格/软链/rtp 行）
"""

import argparse
import os
import platform
import shutil
import sys
from pathlib import Path

PLUGIN_NAME = "rin"
LUA_SPEC_REL = Path("lua/plugins/rin.lua")

LUA_SPEC_TEMPLATE = """\
return {{
  {source} = "{target}",
  name = "{name}",
  ft = "rin",
  event = "VeryLazy",
  config = function() end,
}}
"""

RTP_LINE_VIM = 'set runtimepath+=~/.config/nvim/rin.nvim\n'
RTP_LINE_LUA = 'vim.opt.runtimepath:append(vim.fn.stdpath("config") .. "/rin.nvim")\n'


def log(msg: str) -> None:
    print(f"[rin-install] {msg}")


def confirm(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}] ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def find_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    candidates = []
    if xdg:
        candidates.append(Path(xdg) / "nvim")
    candidates.append(Path.home() / ".config" / "nvim")
    for d in candidates:
        if d.is_dir():
            return d
    return candidates[0]


def plugin_dir() -> Path:
    return Path(__file__).resolve().parent / "nvim"


def is_lazyvim(config_dir: Path) -> bool:
    return (config_dir / "lua" / "plugins").is_dir()


def install_lazy_spec(config_dir: Path, repo: str, dry_run: bool, force: bool) -> None:
    target = repo if repo else str(plugin_dir())
    source = "repo" if repo else "dir"
    spec = LUA_SPEC_TEMPLATE.format(source=source, target=target, name=PLUGIN_NAME)
    spec_path = config_dir / LUA_SPEC_REL

    if spec_path.exists() and not force:
        log(f"已存在 {spec_path}，跳过（使用 -y 覆盖）。")
        return

    log(f"{'[dry-run] ' if dry_run else ''}写入规格文件 {spec_path}")
    if not dry_run:
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec, encoding="utf-8")

    use = "GitHub 仓库" if repo else "本地目录"
    log(f"lazy.nvim 规格使用{use}: {target}")


def install_rtp(config_dir: Path, dry_run: bool, force: bool) -> None:
    link = config_dir / "rin.nvim"
    source = plugin_dir()

    if link.exists() and not force:
        log(f"已存在 {link}，跳过（使用 -y 覆盖）。")
        return

    if platform.system() == "Windows":
        log(f"{'[dry-run] ' if dry_run else ''}复制 {source} -> {link}")
        if not dry_run:
            if link.exists():
                shutil.rmtree(link)
            shutil.copytree(source, link)
    else:
        log(f"{'[dry-run] ' if dry_run else ''}软链 {source} -> {link}")
        if not dry_run:
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(source)

    init = None
    for name in ("init.lua", "init.vim"):
        p = config_dir / name
        if p.exists():
            init = p
            break
    if init is None:
        init = config_dir / "init.lua"
        log(f"{'[dry-run] ' if dry_run else ''}创建 {init}")
        if not dry_run:
            init.write_text(RTP_LINE_LUA, encoding="utf-8")
    else:
        line = RTP_LINE_LUA if init.suffix == ".lua" else RTP_LINE_VIM
        if line in init.read_text(encoding="utf-8"):
            log(f"{init} 已包含 runtimepath 配置，无需修改。")
        else:
            log(f"{'[dry-run] ' if dry_run else ''}在 {init} 末尾追加 runtimepath 配置")
            if not dry_run:
                with init.open("a", encoding="utf-8") as f:
                    f.write("\n" + line)


def uninstall(config_dir: Path, dry_run: bool) -> None:
    removed = []
    spec = config_dir / LUA_SPEC_REL
    if spec.exists():
        log(f"{'[dry-run] ' if dry_run else ''}删除 {spec}")
        if not dry_run:
            spec.unlink()
        removed.append(spec)

    link = config_dir / "rin.nvim"
    if link.is_symlink() or link.exists():
        log(f"{'[dry-run] ' if dry_run else ''}删除 {link}")
        if not dry_run:
            if link.is_symlink():
                link.unlink()
            else:
                shutil.rmtree(link)
        removed.append(link)

    for name in ("init.lua", "init.vim"):
        p = config_dir / name
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8")
        for line in (RTP_LINE_VIM, RTP_LINE_LUA):
            if line in content:
                log(f"{'[dry-run] ' if dry_run else ''}从 {p} 移除 runtimepath 配置")
                if not dry_run:
                    content = content.replace(line, "").replace("\n\n\n", "\n\n").strip()
                    p.write_text(content + "\n", encoding="utf-8")
                removed.append(p)

    if not removed:
        log("未发现已安装的 rin.nvim 组件，无需卸载。")


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 rin.nvim 到 Neovim 配置")
    parser.add_argument("--repo", metavar="USER/REPO",
                        help="GitHub 仓库地址（如 human-coding/rin.nvim），默认使用本地目录")
    parser.add_argument("-y", "--yes", action="store_true", help="已存在时静默覆盖")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际修改")
    parser.add_argument("--uninstall", action="store_true", help="卸载插件")
    args = parser.parse_args()

    config_dir = find_config_dir()
    log(f"Neovim 配置目录: {config_dir}")
    if not config_dir.is_dir():
        log(f"警告: {config_dir} 不存在，将自动创建。")
        if not args.dry_run:
            config_dir.mkdir(parents=True, exist_ok=True)

    if args.uninstall:
        uninstall(config_dir, args.dry_run)
        log("卸载完成，重启 nvim 生效。")
        return 0

    if args.repo and not any(c in args.repo for c in "/"):
        parser.error("--repo 需要 USER/REPO 格式，例如 human-coding/rin.nvim")

    if is_lazyvim(config_dir):
        log("检测到 lazy.nvim（lua/plugins/），使用 lazy.nvim 安装方式。")
        install_lazy_spec(config_dir, args.repo, args.dry_run, args.yes)
    else:
        log("未检测到 lazy.nvim，使用 runtimepath 安装方式。")
        install_rtp(config_dir, args.dry_run, args.yes)

    log("完成。请重启 nvim 生效。")
    if is_lazyvim(config_dir):
        log("LazyVim 用户重启后会自动加载；或执行 :Lazy reload rin")
    else:
        log("打开 .rin 文件后执行 :set filetype? 应显示 rin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
