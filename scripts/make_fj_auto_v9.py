"""FJ 自动巡航 v9：降巡航速度，转弯观感更柔和。"""

import math
import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版4.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_降速柔和_v9_20261102.param")

CHANGES = {
    "WPNAV_SPEED": "250",     # 3.2 -> 2.5 m/s
    "WPNAV_ACCEL_C": "150",   # 1.7 -> 1.5 m/s²，倾角 8.7°
    "WPNAV_RADIUS": "400",    # r = 2.5²/1.5 = 4.17 m
    "WPNAV_JERK": "1.2",
    "ATC_RATE_Y_MAX": "65",
    "ANGLE_MAX": "2500",
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

rows = [
    ("v7 现在", 3.2, 2.0, 5.0),
    ("v8", 3.2, 1.7, 6.0),
    ("v9 降速", 2.5, 1.5, 4.0),
    ("更慢", 2.2, 1.5, 3.3),
]
geo = []
for label, v, a, rad in rows:
    r = v * v / a
    w = math.degrees(v / r)
    geo.append(f"{label}: v={v} m/s, tilt={math.degrees(math.atan(a/9.81)):.1f} deg, "
               f"radius={r:.1f} m, judge={rad} m, yaw={w:.0f} deg/s, 90deg={90/w:.1f} s")
Path(r"D:\ai\deekseep\agent\data\geo_v9.txt").write_text("\n".join(geo), encoding="utf-8")
print("written")
