"""根据 14S 电池与围栏状态生成修正参数（需用户确认电池平台）。"""

import re
from pathlib import Path

SRC = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_终版1.param")
OUT = Path(r"D:\ai\deekseep\agent\out\XILIU_FJ_终版1_14S与围栏修正_20261102.param")

CHANGES = {
    # 电池平台按 14S（日志实测 58.97 V 满电、51.88 V 收尾）
    "MOT_BAT_VOLT_MAX": "58.8",
    "MOT_BAT_VOLT_MIN": "46.2",
    "BATT_ARM_VOLT": "51.8",
    "BATT_LOW_VOLT": "50.4",
    "BATT_CRT_VOLT": "48.3",
    # 围栏打开
    "FENCE_ENABLE": "1",
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
