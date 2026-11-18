"""FJ 自动巡航 v3：解决入弯停顿（转弯向心加速度限制过小）。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版2.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_自动巡航_转弯流畅_v3_20261102.param")

CHANGES = {
    # 入弯停顿的直接原因：ACCEL_C 只有 0.2 m/s²，转弯速度被压到 0.6 m/s
    "WPNAV_ACCEL_C": "150",
    # 半径放大，提前切入而不是到点再转
    "WPNAV_RADIUS": "300",
    # 加加速度放宽，减速与加速衔接更连贯
    "WPNAV_JERK": "3",
    # 巡航速度降到 2.5 m/s，入弯减速量更小
    "WPNAV_SPEED": "250",
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
