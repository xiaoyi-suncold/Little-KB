"""FJ 自动巡航 v6：在「顿」与「猛」之间折中。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版4.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_转弯折中_v6_20261102.param")

CHANGES = {
    # 向心加速度：3.2 → 2.0 m/s²，倾角 18° → 11.5°
    "WPNAV_ACCEL_C": "200",
    # 航向速率：90 → 65 °/s，90° 转弯约 1.4 s
    "ATC_RATE_Y_MAX": "65",
    # 加加速度回到更柔的 1.5
    "WPNAV_JERK": "1.5",
    # 巡航保持 3.2 m/s
    "WPNAV_SPEED": "320",
    # 倾角上限回到 25°
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
for k, v in CHANGES.items():
    print(f"  {k} = {v}")

v = 3.2
for acc in (110, 200, 320):
    vc = (acc / 100 * 3) ** 0.5
    print(f"  预测 ACCEL_C={acc}: 拐角速度 {vc:.2f} m/s, 倾角 {__import__('math').degrees(__import__('math').atan(acc/100/9.81)):.1f}°")
