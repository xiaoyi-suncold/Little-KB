"""生成 FJ5 v3：刹车柔和版（只调刹车组，垂直保持原值）。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-10\XILIU_FJ5_手动调参.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ5_刹车柔和_v3_20261030.param")

CHANGES = {
    # 刹车手感（本次核心）
    "LOIT_BRK_DELAY": "0.35",
    "LOIT_BRK_ACCEL": "180",
    "LOIT_BRK_JERK": "700",
    "LOIT_ANG_MAX": "16",
    "LOIT_ACC_MAX": "320",
    "PSC_VELXY_P": "1.8",
    "PSC_VELXY_D": "0.24",
    # 速度上限（沿用 v2，避免回到 7.8 m/s）
    "LOIT_SPEED": "450",
    "WPNAV_SPEED": "600",
    # 安全项（v2 已包含，保持）
    "FENCE_ENABLE": "1",
    "BATT_FS_LOW_ACT": "2",
    "BATT_FS_CRT_ACT": "1",
    "RTL_SPEED": "300",
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
