"""生成 FJ5 v2 稳定基线（保持 GPS 高度源）。"""

import re
import sys
from pathlib import Path

sys.path.insert(0, r"D:\ai\deekseep\agent")

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-10\XILIU_FJ5_手动调参.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ5_稳定基线_v2_GPS高度_20261030.param")

CHANGES = {
    # 垂直：GPS 高度源下降低跟随强度
    "PSC_POSZ_P": "0.8",
    "PSC_VELZ_P": "2.4",
    "PSC_ACCZ_P": "0.30",
    "PSC_ACCZ_I": "0.60",
    "PSC_ACCZ_IMAX": "300",
    "PSC_ACCZ_FLTE": "15",
    "PSC_JERK_Z": "3",
    "PILOT_SPEED_DN": "80",
    "PILOT_ACCEL_Z": "150",
    # 刹车与水平
    "LOIT_BRK_DELAY": "0.2",
    "LOIT_BRK_JERK": "900",
    "LOIT_SPEED": "450",
    "LOIT_ANG_MAX": "18",
    "PSC_VELXY_P": "2.0",
    "PSC_VELXY_D": "0.35",
    "WPNAV_SPEED": "600",
    # 安全
    "FENCE_ENABLE": "1",
    "BATT_FS_LOW_ACT": "2",
    "BATT_FS_CRT_ACT": "1",
    "RTL_SPEED": "300",
}

lines = SRC.read_text(encoding="utf-8", errors="ignore").splitlines()
seen, result = set(), []
for line in lines:
    m = re.match(r"^\s*([A-Z0-9_]+)\s*,\s*([^#]*?)\s*$", line)
    if m and m.group(1) in CHANGES:
        seen.add(m.group(1))
        result.append(f"{m.group(1)},{CHANGES[m.group(1)]}")
    else:
        result.append(line)
for k, v in CHANGES.items():
    if k not in seen:
        result.append(f"{k},{v}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(result) + "\n", encoding="utf-8")
print(f"写出 {OUT.name}：{len(result)} 行，修改 {len(CHANGES)} 项")
