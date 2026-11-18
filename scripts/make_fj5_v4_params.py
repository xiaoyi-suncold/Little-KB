"""生成 FJ5 v4：修正电池电压平台（14S），其余保持当前值。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\XILIU_FJ5_稳定修订v5_低悬停.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ5_电压平台修正_v4_20261030.param")

# 14S LiPo：满电 58.8 / 空载下限 46.2 / 解锁 51.8 / 低电 50.4 / 严重 48.3
CHANGES = {
    # 主因：电池平台按 12S 配置，实际 14S
    "MOT_BAT_VOLT_MAX": "58.8",
    "MOT_BAT_VOLT_MIN": "46.2",
    "BATT_ARM_VOLT": "51.8",
    "BATT_LOW_VOLT": "50.4",
    "BATT_CRT_VOLT": "48.3",
    # 辅助：降低对 GPS 高度慢漂的跟随强度
    "PSC_POSZ_P": "0.9",
    "PSC_VELZ_P": "2.7",
    "PSC_ACCZ_P": "0.34",
    "PSC_ACCZ_I": "0.68",
    "PSC_ACCZ_IMAX": "400",
    "PSC_ACCZ_FLTE": "18",
    "PSC_JERK_Z": "4",
}

lines = SRC.read_text(encoding="utf-8", errors="ignore").splitlines()
seen, out = set(), []
for line in lines:
    m = re.match(r"^\s*([A-Z0-9_]+)\s*,\s*([^#]*?)\s*$", line)
    if m and m.group(1) in CHANGES:
        seen.add(m.group(1))
        out.append(f"{m.group(1)},{CHANGES[m.group(1)]}")
    else:
        out.append(line)
for k, v in CHANGES.items():
    if k not in seen:
        out.append(f"{k},{v}")

OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"{OUT.name}: {len(out)} 行, 修改 {len(CHANGES)} 项")
for k, v in CHANGES.items():
    print(f"  {k} = {v}")
