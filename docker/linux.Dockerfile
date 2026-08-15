# 编译镜像: 拷贝源码 + 依赖自动发现 + PyInstaller 构建
# 每次构建都会重跑 (源码变更会使其失效), 但基础层被缓存, 速度很快。
ARG BASE_IMAGE=ropide-base:linux-amd64
FROM ${BASE_IMAGE}

COPY . /src
COPY docker/install_deps.py /opt/install_deps.py
COPY docker/build_linux.sh /opt/build_linux.sh

WORKDIR /src
ENTRYPOINT ["/opt/build_linux.sh"]
