"""校验参数表解析是否忠实：源 xlsx ↔ params 表 逐字段比对。

用法：
  python scripts/verify_params.py            # 校验 kb/ 下所有参数表
  python scripts/verify_params.py --official apm_params.txt   # 额外比对官方参数名清单

检查项：
  C1 行数一致          C2 源表无重名          C3 逐字段一致
  C4 数值可解析        C5 命名格式合法        C6 类别/说明覆盖率
  C7 两种读取模式一致（read_only ↔ 普通）
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore import config  # noqa: E402
from kbcore import params as params_mod  # noqa: E402

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,40}$")
NUMERIC_DEFAULT = re.compile(r"^-?\d+(\.\d+)?$")


def read_stream(path: Path) -> list[dict]:
    """read_only 流式读取——与 extract.py 索引正文时走的是同一条路径。"""
    book = load_workbook(path, data_only=True, read_only=True)
    sheet = book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    next(rows, None)
    out = []
    for row in rows:
        cells = list(row) + [None] * len(params_mod.COLUMNS)
        name = str(cells[0] or "").strip()
        if not name or name == "参数名":
            continue
        out.append({key: ("" if cells[i] is None else str(cells[i]).strip())
                    for i, key in enumerate(params_mod.COLUMNS)})
    book.close()
    return out


def check_file(path: Path, conn: sqlite3.Connection) -> list[tuple[str, bool, str]]:
    vehicle = params_mod.detect_vehicle(path)
    normal = params_mod.read_workbook(path)
    stream = read_stream(path)
    db = {
        r["name"]: r
        for r in conn.execute(
            "SELECT name, value, category, desc, hint, default_value FROM params WHERE vehicle = ?",
            (vehicle,),
        )
    }
    results: list[tuple[str, bool, str]] = []

    results.append(("C1 行数一致", len(normal) == len(db),
                    f"源 {len(normal)} 行 / 库 {len(db)} 条"))

    names = [r["name"] for r in normal]
    dup = sorted({n for n in names if names.count(n) > 1})
    results.append(("C2 源表无重名", not dup, f"重复 {len(dup)} 个 {dup[:5]}"))

    mismatch = []
    for row in normal:
        record = db.get(row["name"])
        if not record:
            mismatch.append((row["name"], "缺失"))
            continue
        for key in ("value", "category", "desc", "hint", "default_value"):
            if (record[key] or "").strip() != (row[key] or "").strip():
                mismatch.append((row["name"], key))
    results.append(("C3 逐字段一致", not mismatch, f"差异 {len(mismatch)} 处 {mismatch[:3]}"))

    bad_number = []
    for row in normal:
        default = (row["default_value"] or "").strip()
        value = (row["value"] or "").strip()
        if NUMERIC_DEFAULT.match(default) and value:
            try:
                float(value)
            except ValueError:
                if not re.fullmatch(r"-?\d+(\.\d+)?", value):
                    bad_number.append((row["name"], value))
    results.append(("C4 数值可解析", not bad_number, f"异常 {len(bad_number)} 处 {bad_number[:3]}"))

    bad_name = [r["name"] for r in normal if not NAME_RE.match(r["name"])]
    results.append(("C5 命名格式合法", not bad_name, f"异常 {len(bad_name)} 个 {bad_name[:5]}"))

    no_cat = [r["name"] for r in normal if not r["category"]]
    no_desc = [r["name"] for r in normal if not r["desc"]]
    results.append(("C6 类别/说明覆盖率", not no_cat and len(no_desc) < len(normal) * 0.02,
                    f"缺类别 {len(no_cat)} / 缺说明 {len(no_desc)}"))

    mode_diff = sum(1 for a, b in zip(normal, stream) if a != b) + abs(len(normal) - len(stream))
    results.append(("C7 两种读取模式一致", mode_diff == 0, f"差异 {mode_diff} 行"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", default="", help="官方参数名清单（每行一个）")
    args = parser.parse_args()

    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    files = sorted(config.KB_DIR.rglob("*.xlsx"))
    if not files:
        print("kb/ 下没有 xlsx")
        return 2

    failed = 0
    for path in files:
        print(f"\n=== {path.relative_to(config.KB_DIR)}（{params_mod.detect_vehicle(path)}）===")
        for name, ok, detail in check_file(path, conn):
            print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")
            failed += 0 if ok else 1

    official: set[str] = set()
    if args.official and Path(args.official).exists():
        official = {
            line.strip().upper()
            for line in Path(args.official).read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        print(f"\n=== 官方参数清单：{len(official)} 个 ===")
        for vehicle in ("四轴", "六轴"):
            names = [r[0] for r in conn.execute("SELECT name FROM params WHERE vehicle = ?", (vehicle,))]
            known = [n for n in names if n.upper() in official]
            print(f"  {vehicle}: {len(names)} 个参数，匹配官方 {len(known)} 个"
                  f"（{len(known) / max(len(names), 1):.1%}）")
            unknown = [n for n in names if n.upper() not in official][:15]
            print(f"    非官方/未收录示例：{unknown}")

    conn.close()
    print("\n全部通过" if failed == 0 else f"\n{failed} 项失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
