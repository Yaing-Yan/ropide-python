# 基础镜像: Debian + wine + Windows Python + SSH
# 通过 ARG 区分:
#   PY_URL : Python 来源
#     zip  (推荐, 稳定) -> NuGet 完整版 zip, 免安装器解压即用
#       amd64 -> https://www.nuget.org/api/v2/package/python/3.12.8
#       x86   -> https://www.nuget.org/api/v2/package/pythonx86/3.11.9
#     exe  (实验性, 仅 ARM64 无 NuGet 包) -> 官方安装器
#       arm64 -> https://www.python.org/ftp/python/3.12.8/python-3.12.8-arm64.exe
#   WINE32 : 1 表示需要 wine32 (i386 多架构), 0 表示纯 64 位
# Python 安装到 C:\Python312 (容器内 /root/.wine/drive_c/Python312)。
# 自带 openssh-server (root/ropide), 可手动起容器登录调试:
#   docker run -d --name ropide-box -p 2201:22 -v "$PWD:/src:ro" \
#     ropide-base:<tag> /usr/sbin/sshd -D
# 该层不拷贝源码, 可缓存复用。
FROM debian:bookworm

# 代理透传: build.sh 用 --build-arg 传入, 使 apt-get/wget/wine 全程走代理
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

ARG PY_URL
ARG PY_TYPE=zip
ARG WINE32=0

ENV WINEDEBUG=-all \
    WINEPREFIX=/root/.wine \
    WINEDLLOVERRIDES="mscoree,mshtml="

RUN if [ "$WINE32" = "1" ]; then dpkg --add-architecture i386; fi \
 && apt-get update \
 && if [ "$WINE32" = "1" ]; then \
      apt-get install -y --no-install-recommends wine wine32; \
    else \
      apt-get install -y --no-install-recommends wine; \
    fi \
 && apt-get install -y --no-install-recommends \
      xvfb xauth wget ca-certificates unzip openssh-server \
 && rm -rf /var/lib/apt/lists/* \
 && mv /usr/bin/winedbg-stable /usr/bin/winedbg-stable.disabled 2>/dev/null || true \
 && xvfb-run -a timeout 300 wineboot -u || true \
 && timeout 300 wineserver -w || true \
 && if [ "$PY_TYPE" = "zip" ]; then \
      wget -q -O /tmp/python.zip "$PY_URL" \
      && unzip -q /tmp/python.zip -d /tmp/pynuget \
      && mkdir -p "/root/.wine/drive_c/Python312" \
      && cp -a /tmp/pynuget/tools/. "/root/.wine/drive_c/Python312/" \
      && rm -rf /tmp/pynuget /tmp/python.zip; \
    else \
      wget -q -O /tmp/python-installer.exe "$PY_URL" \
      && xvfb-run -a wine /tmp/python-installer.exe /quiet \
         InstallAllUsers=1 Include_pip=1 PrependPath=0 Include_launcher=0 \
         AssociateFiles=0 Shortcuts=0 "TargetDir=C:\Python312" \
      && rm -f /tmp/python-installer.exe; \
    fi \
 && xvfb-run -a wine "C:\Python312\python.exe" -m ensurepip --upgrade >/dev/null \
 && xvfb-run -a wine "C:\Python312\python.exe" --version \
 && xvfb-run -a wine "C:\Python312\python.exe" -m pip --version

# SSH: root 密码 ropide
RUN echo 'root:ropide' | chpasswd \
 && sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config \
 && sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config \
 && mkdir -p /run/sshd

# 记录架构, 便于排查
RUN uname -m > /arch.txt && cat /arch.txt
