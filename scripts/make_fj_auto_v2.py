"""FJ 自动巡航版 v2：进一步抑制悬停高度慢漂。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\XILIU_FJ_自动巡航版.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_自动巡航_抗漂_v2_20261102.param")

CHANGES = {
    # 外环更慢：不追慢漂
    "PSC_POSZ_P": "0.8",
    "PSC_VELZ_P": "2.5",
    "PSC_ACCZ_P": "0.30",
    # 削积分：让「缓变漂移」落进死区，但保留真实偏差的修正能力
    "PSC_ACCZ_I": "0.45",
    "PSC_ACCZ_IMAX": "200",
    # 平滑：把残余漂移变成看不见的缓慢趋势
    "PSC_ACCZ_FLTE": "15",
    "PSC_JERK_Z": "3",
    "PSC_ACCZ_SMAX": "0.3",
    # 让高度估计多一点气压权重（默认 2.0，越小越信气压）
    "EK3_ALT_M_NSE": "1.2",
    # 航线部分沿用上一版的转弯平滑
    "WPNAV_ACCEL": "100",
    "WPNAV_RADIUS": "500",
    "WPNAV_SPEED": "150",
    "WPNAV_JERK": "2",
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
