"""FJ 自动巡航 v5：到点即转、不停顿（提高转弯向心加速度，放开航向速率）。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版4.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_流畅转弯_v5_20261102.param")

CHANGES = {
    # 入弯不再刹到 1.8：向心加速度从 1.1 提到 3.2 m/s²，拐角速度≈巡航速度
    "WPNAV_ACCEL_C": "320",
    # 巡航降到 3.2 m/s，让 25–30° 倾角内能完成转弯
    "WPNAV_SPEED": "320",
    # 加加速度略放宽，减速→转弯衔接更连续
    "WPNAV_JERK": "2",
    # 航向速率上限放开：90°/s 才能 1 秒转完 90°
    "ATC_RATE_Y_MAX": "90",
    # 允许 30° 倾角，给转弯留横向加速度余量
    "ANGLE_MAX": "3000",
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
