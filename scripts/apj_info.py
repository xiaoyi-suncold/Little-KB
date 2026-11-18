"""解析 .apj 固件：板型、镜像大小、版本字符串。"""

import base64
import gzip
import json
import re
import sys
from pathlib import Path

for p in [Path(r"D:\ai\deekseep\WJ\固件\BC_FC_1.0.2.apj"),
          Path(r"D:\ai\deekseep\WJ\4.6.3固件\arducopter.apj")]:
    raw = p.read_bytes()
    meta = json.loads(raw)
    img = base64.b64decode(meta["image"])
    try:
        bin_data = gzip.decompress(img)
    except Exception:
        bin_data = img
    text = bin_data.decode("latin-1", errors="ignore")
    found = sorted(set(re.findall(r"(ArduCopter[ -~]{0,40}|BC_FC[ -~]{0,20}|ChibiOS[ -~]{0,30})", text)))
    print(f"\n=== {p.name} ===")
    print(f"  board_id: {meta.get('board_id')}  magic: {meta.get('magic')}  镜像 {len(bin_data)/1024:.0f} KB")
    for s in found[:10]:
        print(f"  {s.strip()}")
