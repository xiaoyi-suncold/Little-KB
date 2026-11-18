"""导入机队参数并做一致性分析（只比调参白名单）。"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"D:\ai\deekseep\WJ")
sys.path.insert(0, r"D:\ai\deekseep\agent")

from kbcore import config  # noqa: E402
from kbcore import params as P  # noqa: E402

TUNING = re.compile(
    r"^(ATC_|PSC_|MOT_|LOIT_|ANGLE_MAX|EK3_|INS_GYRO_FILTER|INS_ACCEL_FILTER|INS_HNTCH_|"
    r"BATT_FS_|FENCE_|RTL_|WPNAV_|LAND_|PILOT_|ACRO_|AUTOTUNE_|RNGFND|PRX_|AVOID_|CHUTE_)"
)


def collect(group_dir: Path) -> dict[str, Path]:
    """返回 {编号: 参数文件}，兼容「子目录」与「文件直接平铺」两种结构。"""
    out = {}
    for p in sorted(group_dir.rglob("*.param")):
        rel = p.relative_to(group_dir)
        key = rel.parts[0] if len(rel.parts) > 1 else p.stem
        number = re.search(r"(\d)\s*号", key) or re.search(r"(\d)\s*号", p.stem)
        label = number.group(1) if number else str(len(out) + 1)
        out[f"{group_dir.name}-{label}"] = p
    return out


def main() -> int:
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    for group_name in ["六轴7台", "四轴1号", "四轴2号", "四轴3号", "四轴4号", "四轴5号"]:
        folder = ROOT / group_name
        if not folder.exists():
            print(f"缺目录 {folder}")
            continue
        mapping = collect(folder)
        for vehicle, path in mapping.items():
            info = P.import_param_file(conn, path, vehicle)
            print(f"{vehicle:<12} {info['imported']:>5} 项  <- {path.name}")

    def fleet(prefix: str):
        vehicles = [r[0] for r in conn.execute(
            "SELECT DISTINCT vehicle FROM params WHERE vehicle LIKE ? ORDER BY vehicle", (prefix + "%",))]
        data = {}
        for v in vehicles:
            data[v] = {r["name"]: r["value"] for r in conn.execute(
                "SELECT name, value FROM params WHERE vehicle = ?", (v,))}
        return vehicles, data

    report = {}
    for prefix in ["六轴7台"]:
        vehicles, data = fleet(prefix)
        if not vehicles:
            continue
        common = set.intersection(*(set(d) for d in data.values()))
        diff = defaultdict(dict)
        for name in common:
            if not TUNING.match(name.upper()):
                continue
            values = {v: data[v][name] for v in vehicles}
            if len(set(values.values())) > 1:
                diff[name] = values
        report[prefix] = diff
        print(f"\n=== {prefix}：{len(vehicles)} 架，共有 {len(common)} 项，调参差异 {len(diff)} 项 ===")
        for name, values in sorted(diff.items()):
            compact = ", ".join(f"{v.split('-')[-1]}={x}" for v, x in values.items())
            print(f"  {name:<20} {compact}")

    # 四轴 1-5 号是不同目录，需要合并比较
    units = [r[0] for r in conn.execute("SELECT DISTINCT vehicle FROM params WHERE vehicle LIKE '四轴%号-%' ORDER BY vehicle")]
    data = {}
    for v in units:
        rows = conn.execute("SELECT name, value FROM params WHERE vehicle = ?", (v,)).fetchall()
        if rows:
            data[v] = {r["name"]: r["value"] for r in rows}
    if data:
        common = set.intersection(*(set(d) for d in data.values()))
        diff = {n: {v: data[v][n] for v in data} for n in common
                if TUNING.match(n.upper()) and len({data[v][n] for v in data}) > 1}
        print(f"\n=== 四轴 1–5 号：{len(data)} 架，共有 {len(common)} 项，调参差异 {len(diff)} 项 ===")
        for name, values in sorted(diff.items()):
            print(f"  {name:<20} {', '.join(f'{k}={x}' for k, x in values.items())}")
        report["四轴1-5"] = diff

    out = Path(r"D:\ai\deekseep\agent\data\jldh\fleet_param_diff.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"\n写入 {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
