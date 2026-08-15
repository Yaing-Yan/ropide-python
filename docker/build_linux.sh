#!/usr/bin/env bash
# Linux 容器内的构建入口: 依赖自动发现 -> 按 *.spec 逐个 PyInstaller 构建 -> 拷贝产物到 /out
set -euo pipefail

# 1) 自动扫描第三方依赖并安装缺失项 (新增 import 无需改任何脚本)
python3 /opt/install_deps.py --src /src --install

# 2) 按根目录 *.spec 构建 (新增入口只需新增同名 .spec 文件)
mkdir -p /out
cd /src
shopt -s nullglob
specs=(*.spec)
if [[ ${#specs[@]} -eq 0 ]]; then
  echo "!! 未找到 *.spec, 无法构建" >&2
  exit 1
fi
for spec in "${specs[@]}"; do
  echo "==> pyinstaller $spec"
  pyinstaller --noconfirm --clean "$spec"
  cp -f dist/* /out/
done
echo "==> 构建完成: $(ls /out)"
