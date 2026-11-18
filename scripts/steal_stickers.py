"""从已 clone 的 ChineseBQB 仓库树里挑表情，按 raw 路径下载（走 gh-proxy）

前置：/tmp/cqb 已 clone（--filter=blob:none 即可，只要 tree）
输出：D:\\ruanjian\\qq-bridge\\state\\memes\\gbq\\
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

REPO = r"C:\Users\84216\AppData\Local\Temp\cqb"
MIRROR = "https://gh-proxy.com/https://raw.githubusercontent.com/zhaoolee/ChineseBQB/master/"
OUT = r"D:\ruanjian\qq-bridge\state\memes\gbq"

CATS = ["001Funny_滑稽大佬😏BQB", "010Cat_是喵星人啦🐱BQB", "011Dog_狗🐶BQB", "031Penguin_沙雕企鹅🐧BQB"]
PER_CAT = 8
UA = {"User-Agent": "Mozilla/5.0"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def list_files() -> list[str]:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    paths = list_files()
    total = 0
    for cat in CATS:
        files = [p for p in paths if p.startswith(cat + "/") and re.search(r"\.(gif|png|jpg|jpeg)$", p, re.I)]
        # 跳过纯编号文件，优先带中文描述的中等大小图
        files = [f for f in files if not re.fullmatch(r".*/\d+\.(gif|png|jpg|jpeg)", f, re.I)]
        short = cat.split("_")[0]
        for i, rel in enumerate(files[:PER_CAT], 1):
            ext = os.path.splitext(rel)[1].lower()
            name = f"gbq_{short}_{i:02d}{ext}"
            dst = os.path.join(OUT, name)
            if os.path.exists(dst):
                continue
            url = MIRROR + urllib.parse.quote(rel)
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if len(data) < 800:
                    print(f"  skip(too small) {rel}")
                    continue
                with open(dst, "wb") as f:
                    f.write(data)
                desc = os.path.splitext(os.path.basename(rel))[0]
                print(f"  ok {name} <- {desc} ({len(data)//1024}KB)")
                total += 1
            except Exception as e:
                print(f"  fail {rel}: {e}")
            time.sleep(0.2)
    print(f"共下载 {total} 张 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
