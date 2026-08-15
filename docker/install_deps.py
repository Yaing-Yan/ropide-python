#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自动扫描项目源码中的第三方 Python 依赖并安装缺失的部分。

用法:
  python3 install_deps.py --src /src                 # 只扫描并列出
  python3 install_deps.py --src /src --install       # 扫描 + pip 安装缺失依赖

实现:
  1. 用 ast 解析源码树中所有 .py 文件, 收集顶层 import 的模块名
  2. 过滤标准库 (sys.stdlib_module_names) 和项目本地模块 (src 内同名文件/目录)
  3. 用 importlib.util.find_spec 检查哪些第三方模块缺失
  4. pip install 自动安装缺失模块 (FALLBACK 表处理 import 名 != pip 包名的情况)

兼容 Linux / Windows(wine) / 任意架构的 Python, 仅依赖标准库。
"""

import argparse
import ast
import importlib.util
import os
import subprocess
import sys

# import 名 -> pip 包名 的例外映射
FALLBACK = {
    "dotenv": "python-dotenv",
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "serial": "pyserial",
    "dateutil": "python-dateutil",
    "MySQLdb": "mysqlclient",
    "pymysql": "PyMySQL",
    "psycopg2": "psycopg2-binary",
    "crypto": "pycryptodome",
    "Crypto": "pycryptodome",
    "nacl": "pynacl",
    "paramiko": "paramiko",
    "googleapiclient": "google-api-python-client",
}

SKIP_DIRS = {
    "build", "dist", "release", "__pycache__", ".git", ".venv", ".vev",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", "node_modules",
    # 开发/测试目录里的 import 不是运行时依赖 (如 CEM_API/tests、examples)
    "tests", "examples",
}


def collect_imports(src):
    """遍历 src 下所有 .py, 返回 (第三方模块集合, 本地模块集合)。"""
    stdlib = set(sys.stdlib_module_names)
    local = set()
    third = set()
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    tree = ast.parse(f.read(), filename=path)
            except (SyntaxError, OSError):
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods = [node.module.split(".")[0]]
                for m in mods:
                    if m in stdlib or m in local:
                        continue
                    if os.path.isdir(os.path.join(src, m)) or os.path.isfile(
                        os.path.join(src, m + ".py")
                    ):
                        local.add(m)
                        continue
                    third.add(m)
    return third, local


def is_installed(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def pip_install(args):
    """pip install, 自动兼容 PEP 668 (externally-managed 环境, 如 Debian)。"""
    cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir"] + args
    r = subprocess.run(cmd)
    if r.returncode != 0:
        # Debian 12+ / Ubuntu 23.04+ 的系统 python 禁止 pip 直接安装
        r2 = subprocess.run(cmd + ["--break-system-packages"])
        return r2.returncode
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=".", help="源码目录")
    ap.add_argument("--install", action="store_true", help="自动 pip 安装缺失依赖")
    args = ap.parse_args()

    third, local = collect_imports(args.src)
    print("[deps] 本地模块   : " + (", ".join(sorted(local)) if local else "无"))
    print("[deps] 第三方依赖 : " + (", ".join(sorted(third)) if third else "无"))

    missing = sorted(m for m in third if not is_installed(m))
    if not missing:
        print("[deps] 所有第三方依赖均已安装")
        return 0

    print("[deps] 缺失依赖   : " + ", ".join(missing))
    if not args.install:
        print("[deps] 提示: 加 --install 自动 pip 安装")
        return 0

    pkgs = sorted({FALLBACK.get(m, m) for m in missing})
    print("[deps] 安装: pip install " + " ".join(pkgs))
    batch = pip_install(pkgs)

    failed = []
    for m in missing:
        if is_installed(m):
            continue
        pkg = FALLBACK.get(m, m)
        if batch != 0 or pkg != m:
            print(f"[deps] 单独尝试安装 {pkg} ...")
            pip_install([pkg])
        if not is_installed(m):
            failed.append(m)

    if failed:
        # 不致命: 可能是测试/开发目录或已改名包留下的 import,
        # 真正缺的模块会在 PyInstaller 阶段明确报错
        print(
            "[deps] 警告: 以下依赖安装失败 (构建将继续, 若 PyInstaller 报缺模块请人工检查): "
            + ", ".join(failed),
            file=sys.stderr,
        )
        return 0
    print("[deps] 依赖安装完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
