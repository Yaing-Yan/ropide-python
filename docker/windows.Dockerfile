# 编译镜像: 拷贝源码 + 依赖自动发现 + wine 下 PyInstaller 构建
ARG BASE_IMAGE=ropide-base:windows-amd64
FROM ${BASE_IMAGE}

COPY . /src
COPY docker/install_deps.py /opt/install_deps.py
COPY docker/build_windows.sh /opt/build_windows.sh

WORKDIR /src
ENTRYPOINT ["/opt/build_windows.sh"]
