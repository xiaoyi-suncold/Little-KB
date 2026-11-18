"""对比两份 ArduPilot 参数表（xlsx），输出 Markdown 报告。

用法：
  python scripts/xlsx_param_diff.py A.xlsx B.xlsx --out report.md

两份表的结构约定：
  第 1 个 sheet 为参数表：参数名 | 当前值 | 类别 | 作用说明 | 调参/学习提示 | 默认值
  其后的 sheet 忽略（学习地图、本机重点等由人工阅读）。
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover
    print("需要 openpyxl", file=sys.stderr)
    raise

KEYS = ("name", "value", "category", "desc", "hint", "default")


def load_params(path: Path) -> tuple[str, dict[str, dict], list[str]]:
    book = load_workbook(path, data_only=True, read_only=True)
    sheet = book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None) or ()
    params: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        cells = list(row) + [None] * (len(KEYS) - len(row))
        name = str(cells[0] or "").strip()
        if not name or name == "参数名":
            continue
        record = {key: ("" if cells[i] is None else str(cells[i]).strip()) for i, key in enumerate(KEYS)}
        params[name] = record
        order.append(name)
    book.close()
    return str(header[0] or ""), params, order


def norm(value: str) -> str:
    text = (value or "").strip().lower()
    try:
        return f"{float(text):.6g}"
    except ValueError:
        return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("a")
    parser.add_argument("b")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    a_name = Path(args.a).stem
    b_name = Path(args.b).stem
    _, pa, oa = load_params(Path(args.a))
    _, pb, ob = load_params(Path(args.b))

    common = [name for name in oa if name in pb]
    only_a = [name for name in oa if name not in pb]
    only_b = [name for name in ob if name not in pa]
    filled_a = [name for name in oa if pa[name]["value"].strip()]
    filled_b = [name for name in ob if pb[name]["value"].strip()]
    # 只比较两边都填了值的参数：学习地图类表格常常只填重点参数，
    # 把「空」当成 0 会造出大量假差异。
    comparable = [
        name for name in common
        if pa[name]["value"].strip() and pb[name]["value"].strip()
    ]
    changed = [name for name in comparable if norm(pa[name]["value"]) != norm(pb[name]["value"])]

    cat_a = Counter(pa[n]["category"] or "未分类" for n in pa)
    cat_b = Counter(pb[n]["category"] or "未分类" for n in pb)
    changed_by_cat = Counter(pa[n]["category"] or "未分类" for n in changed)

    lines: list[str] = []
    add = lines.append
    add(f"# 参数表对比：{a_name} vs {b_name}")
    add("")
    add("| 指标 | " + a_name + " | " + b_name + " |")
    add("| --- | --- | --- |")
    add(f"| 参数条数 | {len(pa)} | {len(pb)} |")
    add(f"| 填了当前值的参数 | {len(filled_a)} | {len(filled_b)} |")
    add(f"| 共有参数 | {len(common)} | {len(common)} |")
    add(f"| 两边都有值、可比较 | {len(comparable)} | {len(comparable)} |")
    add(f"| 仅本表独有 | {len(only_a)} | {len(only_b)} |")
    add(f"| 值不同 | {len(changed)} | — |")
    add("")
    add("## 类别分布")
    add("")
    add("| 类别 | " + a_name + " | " + b_name + " | 值不同数 |")
    add("| --- | --- | --- | --- |")
    for cat, _count in (cat_a + cat_b).most_common(40):
        add(f"| {cat} | {cat_a.get(cat, 0)} | {cat_b.get(cat, 0)} | {changed_by_cat.get(cat, 0)} |")
    add("")

    if only_a:
        add(f"## 仅 {a_name} 有（{len(only_a)}）")
        add("")
        for name in only_a[:80]:
            add(f"- `{name}` = {pa[name]['value']}（{pa[name]['category']}）{pa[name]['desc']}")
        add("")

    if only_b:
        add(f"## 仅 {b_name} 有（{len(only_b)}）")
        add("")
        for name in only_b[:80]:
            add(f"- `{name}` = {pb[name]['value']}（{pb[name]['category']}）{pb[name]['desc']}")
        add("")

    add(f"## 值不同的参数（{len(changed)}）")
    add("")
    add(f"| 参数 | 类别 | {a_name} | {b_name} | 说明 |")
    add("| --- | --- | --- | --- | --- |")
    for name in changed:
        ra, rb = pa[name], pb[name]
        desc = ra["desc"].replace("|", "/")[:80]
        add(f"| `{name}` | {ra['category']} | {ra['value']} | {rb['value']} | {desc} |")
    add("")

    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written {args.out} ({len(text)} chars)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
