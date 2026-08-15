#!/usr/bin/env bash
# Windows (wine) 容器内的构建入口:
#   依赖自动发现(在 Windows Python 内执行, 保证标准库判断一致)
#   -> 按 *.spec 逐个用 wine + Windows Python 跑 PyInstaller -> 拷贝产物到 /out
set -euo pipefail

PY='C:\Python312\python.exe'
W() { xvfb-run -a wine "$@"; }

# 1) 确保 pip 是最新可用版本 (失败不阻断)
W "$PY" -m pip install --upgrade pip --quiet || true

# 2) 依赖扫描 + 自动安装 (wine 内 Windows Python 执行; /src 在 wine 里是 Z:\src)
cp /opt/install_deps.py /root/.wine/drive_c/install_deps.py
W "$PY" 'C:\install_deps.py' --src 'Z:\src' --install

# 3) 按根目录 *.spec 构建 (新增入口只需新增同名 .spec 文件)
mkdir -p /out
cd /src
shopt -s nullglob
specs=(*.spec)
if [[ ${#specs[@]} -eq 0 ]]; then
  echo "!! 未找到 *.spec, 无法构建" >&2
  exit 1
fi
for spec in "${specs[@]}"; do
  echo "==> wine pyinstaller $spec"
  W "$PY" -m PyInstaller --noconfirm --clean "$spec"
  cp -f dist/*.exe /out/
done
echo "==> 构建完成: $(ls /out)"
