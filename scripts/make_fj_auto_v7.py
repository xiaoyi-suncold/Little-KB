"""FJ 自动巡航 v7：让判定半径与实际转弯半径匹配，真正提前切弯。"""

import math
import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版4.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_提前切弯_v7_20261102.param")

CHANGES = {
    "WPNAV_SPEED": "320",
    "WPNAV_ACCEL_C": "200",
    "WPNAV_RADIUS": "500",   # 判定半径 5 m，与 3.2 m/s、2.0 m/s² 的转弯半径 5.1 m 匹配
    "WPNAV_JERK": "1.5",
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
print(f"{OUT.name}: {len(out)} 行, 修改 {len(CHANGES)} 项")

print("\n几何校验（半径 r = v² / a）：")
for label, speed, acc, radius in [
    ("现在（版4）", 4.0, 1.1, 3.0),
    ("v6", 3.2, 2.0, 3.0),
    ("v7", 3.2, 2.0, 5.0),
]:
    r = speed ** 2 / acc
    w = math.degrees(speed / r)
    print(f"  {label:<10} v={speed} a={acc} → 转弯半径 {r:>4.1f} m，判定半径 {radius} m，"
          f"角速度 {w:>4.0f}°/s，90° 用时 {90/w:>3.1f} s")
