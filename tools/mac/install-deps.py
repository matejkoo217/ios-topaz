#!/usr/bin/env python3
"""Install the build dependencies that Homebrew refuses on Intel macOS.

The kernel build needs jq, gum, cmake, ninja, ipsw (and optionally ccache); the
official Homebrew installer now stops with "only supported on Apple Silicon", so
each one is taken from its own upstream release instead, which is the same binary
Homebrew would have poured.

  python3 install-deps.py [--bin ~/bin]

Everything lands in the target directory (default ~/bin), which the caller is
expected to have on PATH.  Re-running is cheap: an existing binary is kept.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ARCH = platform.machine()          # x86_64 on this Mac
BIN = os.path.expanduser("~/bin")

# repo, asset patterns (case-insensitive), installed name, "raw" or "archive"
GH = [
    ("jqlang/jq", ("macos-amd64", "macos64", "darwin-amd64"), "jq", "raw"),
    ("charmbracelet/gum", ("darwin_x86_64", "darwin-amd64", "macos_x86_64"), "gum", "archive"),
    ("ninja-build/ninja", ("ninja-mac", "darwin"), "ninja", "archive"),
    # blacktop renamed the binary to ipswd; build.sh still calls it "ipsw"
    ("blacktop/ipsw", ("macos_x86_64", "macos-amd64"), "ipsw", "archive"),
    ("Kitware/CMake", ("macos-universal.tar.gz",), "cmake", "archive"),
]


def api(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                              "User-Agent": "fuxi-build-setup"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "fuxi-build-setup"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def extract(path, tmp):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
    else:
        with tarfile.open(path) as t:
            t.extractall(tmp)


def find(tmp, name):
    hits = []
    for root, _, files in os.walk(tmp):
        for f in files:
            if f == name:
                hits.append(os.path.join(root, f))
    hits.sort(key=len)
    return hits[0] if hits else None


def install_from(url, name, tmp, kind):
    if kind == "raw":
        dst = os.path.join(BIN, name)
        fetch(url, dst)
        os.chmod(dst, 0o755)
        print(f"installed {name} -> {dst}")
        return
    ext = ".zip" if url.endswith(".zip") else ".tar.gz"
    path = os.path.join(tmp, name + ext)
    fetch(url, path)
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic[:2] != b"\x1f\x8b" and magic[:2] != b"PK":
        raise SystemExit(f"{name}: {url} did not return an archive")
    extract(path, tmp)
    src = find(tmp, name) or find(tmp, name + "d")
    if not src:
        raise SystemExit(f"{name}: binary not found in {url}")
    dst = os.path.join(BIN, name)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o755)
    print(f"installed {name} -> {dst}")


def main():
    global BIN
    if "--bin" in sys.argv:
        BIN = os.path.expanduser(sys.argv[sys.argv.index("--bin") + 1])
    os.makedirs(BIN, exist_ok=True)

    todo = []
    for repo, patterns, name, kind in GH:
        if os.path.exists(os.path.join(BIN, name)) or shutil.which(name):
            print(f"have {name}")
            continue
        rel = api(f"https://api.github.com/repos/{repo}/releases/latest")
        pick = None
        for a in rel.get("assets", []):
            low = a["name"].lower()
            if any(p in low for p in patterns):
                pick = a["browser_download_url"]
                break
        if not pick:
            print(f"{name}: no matching asset in {repo} {rel.get('tag_name')} "
                  f"({[a['name'] for a in rel.get('assets', [])][:6]})", file=sys.stderr)
            continue
        todo.append((pick, name, kind))

    for url, name, kind in todo:
        tmp = tempfile.mkdtemp(prefix=f"dep-{name}-")
        try:
            install_from(url, name, tmp, kind)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\nPATH hint: export PATH=\"$HOME/bin:$PATH\"")
    for name in ("jq", "gum", "cmake", "ninja", "ipsw"):
        p = os.path.join(BIN, name)
        ok = os.access(p, os.X_OK)
        print(f"  {name:7s} {'ok' if ok else 'MISSING'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
