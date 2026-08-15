# =============================================================================
# Makefile — ropide-python 当前环境一键构建
#
# 取代 build.sh 的“本机构建”职责: 键入 `make` 即为【当前环境】构建两个可执行文件:
#
#   dist/main                (main.py, 依赖 compiler.py / package.py / CEM_API/ / gadgets/)
#   dist/install_nvim_plugin (install_nvim_plugin.py, 依赖 nvim/)
#
# 构建策略 (与 build.sh 原生构建一致):
#   * 自动检测 PyInstaller, 缺失时用 pip 自动安装
#   * 用 docker/install_deps.py 扫描源码 import, 自动安装缺失的第三方依赖
#   * 按根目录 *.spec 逐个构建 (新增入口只需新增同名 .spec 文件)
#
# 用法:
#   make                        # 构建全部 (默认)
#   make main                   # 仅构建 main
#   make install_nvim_plugin    # 仅构建 install_nvim_plugin
#   make clean                  # 清理 build/ dist/ __pycache__
#   make help                   # 显示本帮助
#
# 可覆盖变量:
#   make PYTHON=/path/to/python3  # 指定解释器
# =============================================================================

SHELL := /bin/bash

PYTHON ?= python3
PIP     := $(PYTHON) -m pip
PYI     := $(PYTHON) -m PyInstaller

# 由根目录 *.spec 自动发现入口 (当前两个: main / install_nvim_plugin)
SPECS := $(wildcard *.spec)

.PHONY: all setup main install_nvim_plugin clean help

# 默认目标: 为当前环境构建全部程序
all: setup
	@test -n "$(SPECS)" || { echo "[make] 错误: 未找到 *.spec 文件" >&2; exit 1; }
	@set -e; \
	for spec in $(SPECS); do \
		echo "==> [make] 构建 $${spec} ..."; \
		$(PYI) --noconfirm --clean "$${spec}"; \
	done
	@echo "[make] 构建完成, 可执行文件位于 dist/ :"
	@ls -lh dist/ 2>/dev/null | grep -E 'main|install_nvim_plugin' || true

# 仅构建 main
main: setup
	@echo "==> [make] 构建 main.spec ..."
	$(PYI) --noconfirm --clean main.spec

# 仅构建 install_nvim_plugin
install_nvim_plugin: setup
	@echo "==> [make] 构建 install_nvim_plugin.spec ..."
	$(PYI) --noconfirm --clean install_nvim_plugin.spec

# 确保当前环境就绪: PyInstaller 可用 + 第三方依赖齐全。
# 注意: install_deps.py 对“依赖安装失败”只告警不报错(见脚本内注释),
# 真正缺模块时会在 PyInstaller 阶段以 "hidden import not found" 告警、
# 或产物运行时 ModuleNotFoundError 暴露出来。
setup:
	@if ! $(PYTHON) -m PyInstaller --version >/dev/null 2>&1; then \
		echo "[make] 未检测到 PyInstaller, 自动安装 ..."; \
		$(PIP) install --no-cache-dir pyinstaller || \
		$(PIP) install --no-cache-dir --break-system-packages pyinstaller || true; \
	fi
	@if ! $(PYTHON) -m PyInstaller --version >/dev/null 2>&1; then \
		echo "[make] 错误: PyInstaller 安装后仍不可用 (请检查网络/权限, 或 make PYTHON=... 指定解释器)" >&2; \
		exit 1; \
	fi
	@echo "[make] PyInstaller 可用 ($$($(PYTHON) -m PyInstaller --version))"
	@$(PYTHON) docker/install_deps.py --src . --install

clean:
	rm -rf build dist __pycache__
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@echo "[make] 已清理 build/ dist/ __pycache__"

help:
	@printf '%s\n' \
	  "" \
	  "用法:" \
	  "  make                         构建全部 (main + install_nvim_plugin)" \
	  "  make main                    仅构建 main" \
	  "  make install_nvim_plugin     仅构建 install_nvim_plugin" \
	  "  make clean                   清理 build/ dist/ __pycache__" \
	  "  make PYTHON=python3.12       指定解释器构建" \
	  ""
