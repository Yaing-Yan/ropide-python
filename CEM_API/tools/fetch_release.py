#!/usr/bin/env python3
"""下载 CasioEmuMsvc 最新 Windows x64 发行版，得到可被 Emu 使用的
CasioEmuMsvc.exe + CasioEmuMsvc.Plugin.McpPlugin.dll。

用法::

    python tools/fetch_release.py                # 下载到 CEM-API/bin/
    python tools/fetch_release.py --tag stable-20260808170455-9a586c3
    python tools/fetch_release.py --output ~/emu

随后::

    from cem import Emu
    emu = Emu("path/to/model", exe="CEM-API/bin/CasioEmuMsvc.exe")
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = "telecomadm1145/CasioEmuMsvc"
RELEASE_BASE = f"https://github.com/{REPO}/releases"
API_BASE = f"https://api.github.com/repos/{REPO}/releases"

NEEDED = [
    "CasioEmuMsvc.exe",
    "CasioEmuMsvc.Plugin.McpPlugin.dll",
]


def _fetch(url, token=None, binary=False):
    request = urllib.request.Request(url, headers={"User-Agent": "cem-api-fetch"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    return data if binary else data.decode("utf-8", "replace")


def _api(path, token=None):
    try:
        return json.loads(_fetch(f"{API_BASE}{path}", token))
    except urllib.error.HTTPError:
        # 限流 / 不存在时回退到 HTML 解析
        return None
    except json.JSONDecodeError:
        return None


def find_windows_asset(tag, token=None):
    """找到 windows-x64-*.zip 的下载地址。优先 API，回退解析资产 HTML。"""
    release = _api(f"/tags/{tag}", token)
    if release and release.get("assets"):
        for asset in release["assets"]:
            if re.match(r"windows-x64-.*\.zip", asset["name"]):
                return asset["browser_download_url"]
    # 回退: 解析 expanded_assets 页面 HTML 里的资产链接
    try:
        page = _fetch(f"{RELEASE_BASE}/expanded_assets/{tag}", token)
    except urllib.error.HTTPError:
        return None
    for url in re.findall(r'href="([^"]+)"', page):
        if re.search(r"/releases/download/.*/windows-x64-.*\.zip", url):
            return "https://github.com" + url
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="latest", help="发行版 tag，默认 latest")
    parser.add_argument("--output", default=None, help="输出目录，默认 CEM-API/bin")
    parser.add_argument("--token", default=None, help="GitHub token (可选，提升 API 配额)")
    args = parser.parse_args()

    output = Path(args.output) if args.output else Path(__file__).resolve().parent.parent / "bin"
    output.mkdir(parents=True, exist_ok=True)

    if args.tag == "latest":
        release = _api("/latest", args.token)
        if not release:
            print("获取 latest release 失败（可能被限流），请用 --tag 指定")
            sys.exit(1)
        tag = release["tag_name"]
    else:
        tag = args.tag
    print(f"release tag: {tag}")

    url = find_windows_asset(tag, args.token)
    if not url:
        print(f"在 {tag} 中找不到 windows-x64 资产")
        sys.exit(1)
    print(f"下载: {url}")

    zip_path = output / "release.zip"
    try:
        zip_path.write_bytes(_fetch(url, args.token, binary=True))
    except urllib.error.HTTPError as exc:
        print(f"下载失败: HTTP {exc.code}")
        sys.exit(1)

    with zipfile.ZipFile(zip_path) as archive:
        for name in NEEDED + ["roms.db"]:
            try:
                member = archive.read(name)
            except KeyError:
                continue
            (output / name).write_bytes(member)
            print(f"  解压: {name} ({len(member)} bytes)")

        for name in ("CasioEmuMsvc.pdb", "CasioEmuMsvc.Plugin.McpPlugin.pdb"):
            try:
                member = archive.read(name)
            except KeyError:
                continue
            (output / name).write_bytes(member)

    zip_path.unlink(missing_ok=True)
    print(f"\n完成。可执行文件位于: {output}")
    print(f"用法: Emu('model_dir', exe=r'{output / 'CasioEmuMsvc.exe'}')")


if __name__ == "__main__":
    main()
