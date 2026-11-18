"""FJ 自动巡航 v8：转弯力度再柔一档（保持判定半径与转弯半径匹配）。"""

import math
import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版4.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_转弯柔和_v8_20261102.param")

CHANGES = {
    "WPNAV_SPEED": "320",
    "WPNAV_ACCEL_C": "170",   # 2.0 -> 1.7 m/s²，倾角 11.5° -> 9.8°
    "WPNAV_RADIUS": "600",    # 与 r = 3.2²/1.7 = 6.0 m 匹配
    "WPNAV_JERK": "1.2",      # 侧倾建立更缓
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

geo = []
for label, v, a, rad in [("v7 现在", 3.2, 2.0, 5.0), ("v8", 3.2, 1.7, 6.0),
                         ("更柔", 3.2, 1.4, 7.3), ("降速版", 2.8, 1.7, 4.6)]:
    r = v * v / a
    w = math.degrees(v / r)
    geo.append(f"{label}: 倾角 {math.degrees(math.atan(a / 9.81)):.1f} deg, 半径 {r:.1f} m, "
               f"判定 {rad} m, 角速度 {w:.0f} deg/s, 90 deg {90 / w:.1f} s")
Path(r"D:\ai\deekseep\agent\data\geo_v8.txt").write_text("\n".join(geo), encoding="utf-8")
print("written")
