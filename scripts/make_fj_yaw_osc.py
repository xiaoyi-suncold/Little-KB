"""FJ 自动巡航版3：抑制航向回摆。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版3.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_航向回摆_v1_20261102.param")

CHANGES = {
    # 阻尼：D 从 0.0015 提到 0.004，配合 FLTD 20
    "ATC_RAT_YAW_D": "0.004",
    # 误差滤波：2 Hz 太慢，滞后直接变成过冲
    "ATC_RAT_YAW_FLTE": "5",
    # 角度环：4.5 偏高，回中过冲主要来自这里
    "ATC_ANG_YAW_P": "3.5",
    # 输出限幅：45 如果是百分比会削掉修正能力，先放开
    "ATC_RATE_Y_MAX": "0",
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
