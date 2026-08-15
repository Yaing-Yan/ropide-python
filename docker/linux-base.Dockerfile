# 基础镜像: Debian + Python + PyInstaller + SSH
# 用 --platform 分别构建 amd64 / 386 / arm64 / arm/v7, 结果按目标名缓存复用。
# 该层不拷贝源码, 所以不受代码变化影响, 只有工具链升级才需要重建
# (./build.sh --rebuild-bases)。
# 自带 openssh-server (root/ropide), 可手动起容器登录调试:
#   docker run -d --name ropide-box -p 2201:22 -v "$PWD:/src:ro" \
#     ropide-base:<tag> /usr/sbin/sshd -D
FROM debian:bookworm

# 代理透传: build.sh 用 --build-arg 传入, 使 apt-get/pip 全程走代理;
# 值变化时会自动失效缓存重建 (--rebuild-bases 可强制重建)
ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG http_proxy=""
ARG https_proxy=""
ARG ALL_PROXY=""
ARG NO_PROXY=""
ENV HTTP_PROXY=${HTTP_PROXY} HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${http_proxy} https_proxy=${https_proxy} \
    ALL_PROXY=${ALL_PROXY} all_proxy=${ALL_PROXY} \
    NO_PROXY=${NO_PROXY} no_proxy=${NO_PROXY}

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip ca-certificates binutils file libpython3.11 \
      libpython3.11-dev openssh-server \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install --no-cache-dir --break-system-packages "pyinstaller>=6.10"

# SSH: root 密码 ropide
RUN echo 'root:ropide' | chpasswd \
 && sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config \
 && sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && mkdir -p /run/sshd

# 记录架构, 便于排查
RUN uname -m > /arch.txt && cat /arch.txt
