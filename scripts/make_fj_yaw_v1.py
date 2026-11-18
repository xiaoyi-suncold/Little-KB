"""FJ 自动巡航版2：航向（yaw）第一轮调参。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版2.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_航向调参_v1_20261102.param")

CHANGES = {
    # 抗漂：提高偏航积分（原 0.018 是出厂值，大机型偏小）
    "ATC_RAT_YAW_I": "0.05",
    # 响应：偏航角加速度上限 40°/s² 太软，提到 120°/s²
    "ATC_ACCEL_Y_MAX": "12000",
    # 限速：防止原地甩头
    "ATC_RATE_Y_MAX": "120",
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
