#!/usr/bin/env bash
# 一键构建 release：Linux 本机 PyInstaller 构建，Windows 通过 wine 构建，macOS 由 GitHub Actions (.github/workflows/macos-build.yml) 构建。
# 用法:
#   ./build.sh           构建 Linux + Windows 并打包 zip
#   ./build.sh --linux   只构建 Linux
#   ./build.sh --windows 只构建 Windows
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DO_LINUX=0
DO_WINDOWS=0
if [[ $# -eq 0 ]]; then
  DO_LINUX=1
  DO_WINDOWS=1
else
  for arg in "$@"; do
    case "$arg" in
      --linux) DO_LINUX=1 ;;
      --windows) DO_WINDOWS=1 ;;
      *) echo "未知参数: $arg"; exit 1 ;;
    esac
  done
fi

build_one() {
  local name="$1" data="$2"
  pyinstaller --noconfirm --clean --onefile --name "$name" --add-data "$data" "$name.py"
}

build_win_one() {
  local name="$1" data="$2"
  wine "C:\\Python312\\python.exe" -m PyInstaller --noconfirm --clean --onefile \
    --name "$name" --add-data "$data" --distpath "dist\\windows-x86-64" "$name.py"
}

if [[ $DO_LINUX -eq 1 ]]; then
  echo "==> 构建 Linux x86_64"
  build_one main "gadgets:gadgets"
  build_one install_nvim_plugin "nvim:nvim"
  mkdir -p release-linux-x86-64
  cp -f dist/main dist/install_nvim_plugin release-linux-x86-64/
  rm -f ropide-linux-x86-64.zip
  (cd release-linux-x86-64 && zip -q ../ropide-linux-x86-64.zip main install_nvim_plugin)
  echo "==> 完成: ropide-linux-x86-64.zip"
fi

if [[ $DO_WINDOWS -eq 1 ]]; then
  if ! command -v wine >/dev/null 2>&1 || [[ ! -f "$HOME/.wine/drive_c/Python312/python.exe" ]]; then
    echo "!! 跳过 Windows: 未找到 wine 或 wine 中未安装 Python (C:\\Python312)"
  else
    echo "==> 构建 Windows x86_64 (wine)"
    build_win_one main "gadgets;gadgets"
    build_win_one install_nvim_plugin "nvim;nvim"
    mkdir -p release-windows-x86-64
    cp -f dist/windows-x86-64/main.exe dist/windows-x86-64/install_nvim_plugin.exe release-windows-x86-64/
    rm -f ropide-windows-x86-64.zip
    (cd release-windows-x86-64 && zip -q ../ropide-windows-x86-64.zip main.exe install_nvim_plugin.exe)
    echo "==> 完成: ropide-windows-x86-64.zip"
  fi
fi

echo "全部完成"
