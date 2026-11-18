"""生成 FJ 自动巡航版稳定参数：垂直软化 + 转弯平滑。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\XILIU_FJ_自动巡航版.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_自动巡航_稳定版_v1_20261030.param")

CHANGES = {
    # 悬停：降低垂直环对 GPS 高度慢漂的跟随
    "PSC_POSZ_P": "0.9",
    "PSC_VELZ_P": "2.7",
    "PSC_ACCZ_P": "0.34",
    "PSC_ACCZ_I": "0.68",
    "PSC_ACCZ_IMAX": "400",
    "PSC_ACCZ_FLTE": "18",
    "PSC_JERK_Z": "4",
    # 航线：降低横向加速度、放大转弯半径、降巡航速度
    "WPNAV_ACCEL": "100",
    "WPNAV_RADIUS": "500",
    "WPNAV_SPEED": "150",
    "WPNAV_JERK": "2",
    # 降落柔和
    "LAND_SPEED": "50",
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
