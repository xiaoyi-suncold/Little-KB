"""FJ 自动巡航版3：不动 ATC_RATE_Y_MAX 的航向平滑方案。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版3.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_航向平滑_v2_20261102.param")

CHANGES = {
    # 打杆灵敏度：PILOT_Y_RATE 202.5 远大于 RATE_MAX 45，
    # 杆量到 22% 就顶满，难精细控制
    "PILOT_Y_RATE": "60",
    # 目标角速度的加速度上限：80°/s² 太慢，45°/s 要 0.56s 才停
    "ATC_ACCEL_Y_MAX": "13000",
    # 阻尼
    "ATC_RAT_YAW_D": "0.003",
    # 误差滤波：2Hz 滞后大
    "ATC_RAT_YAW_FLTE": "4",
    # 角度环略降
    "ATC_ANG_YAW_P": "4.0",
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
