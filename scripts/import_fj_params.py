"""导入 jldh_fj 的参数版本并生成相邻版本差异。

用法：
  python scripts/import_fj_params.py            # 导入 + 打印差异摘要
  python scripts/import_fj_params.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore import config  # noqa: E402
from kbcore import params as params_mod  # noqa: E402

SOURCE = Path(r"D:\ai\deekseep\jldh_fj")

VERSIONS = [
    ("XILIU_FJ2_fixed_v2_抑振.param", "FJ2-抑振"),
    ("XILIU_FJ2_稳定修订.param", "FJ2-v1"),
    ("XILIU_FJ2_稳定修订v2_怠速.param", "FJ2-v2"),
    ("XILIU_FJ2_稳定修订v3_响应.param", "FJ2-v3"),
    ("XILIU_FJ5_稳定修订v4_低悬停.param", "FJ5-v4"),
    ("XILIU_FJ5_稳定修订v5_作废_单位错误勿用.param", "FJ5-v5作废"),
    ("XILIU_FJ5_V4_step1_delay.param", "FJ5-step1"),
    ("XILIU_FJ5_V6_刹车角度_目标.param", "FJ5-v6"),
    ("稳定调参参数_阶段1.param", "阶段1"),
]

CHAIN = [
    ("FJ2-抑振", "FJ2-v1"),
    ("FJ2-v1", "FJ2-v2"),
    ("FJ2-v2", "FJ2-v3"),
    ("FJ5-v4", "FJ5-step1"),
    ("FJ5-step1", "FJ5-v6"),
    ("FJ5-v5作废", "FJ5-v6"),
    ("阶段1", "FJ5-v4"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    imported = []
    for filename, vehicle in VERSIONS:
        path = SOURCE / filename
        if not path.exists():
            print(f"缺失：{path}")
            continue
        info = params_mod.import_param_file(conn, path, vehicle)
        imported.append(info)
        print(f"{vehicle:<12} {info['imported']:>5} 项  <- {filename}")

    summary = []
    print("\n=== 相邻版本差异 ===")
    for a, b in CHAIN:
        result = params_mod.diff(conn, a, b)
        changes = []
        for name in result["changed"]:
            va = conn.execute("SELECT value FROM params WHERE vehicle=? AND name=?", (a, name)).fetchone()
            vb = conn.execute("SELECT value FROM params WHERE vehicle=? AND name=?", (b, name)).fetchone()
            changes.append({"name": name, "from": va[0] if va else "", "to": vb[0] if vb else ""})
        only_a = result["only_a"]
        only_b = result["only_b"]
        summary.append({"a": a, "b": b, "changed": changes, "only_a": only_a, "only_b": only_b})
        print(f"\n{a} → {b}: 改动 {len(changes)}，仅 A {len(only_a)}，仅 B {len(only_b)}")
        for item in changes[:40]:
            print(f"  {item['name']:<22} {item['from']:>10} → {item['to']}")
        if len(changes) > 40:
            print(f"  … 其余 {len(changes) - 40} 项")

    if args.json:
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n写入 {args.json}")
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
