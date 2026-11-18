"""构建参数字典（参数语义库），不依赖任何机型的具体取值。

用法：
  python scripts/build_paramdict.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore import config  # noqa: E402
from kbcore import paramdict  # noqa: E402
from kbcore.index import Index  # noqa: E402


def main() -> int:
    sections_file = config.DATA_DIR / "official_sections.txt"
    sections = set()
    if sections_file.exists():
        sections = {
            line.strip()
            for line in sections_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    index = Index(config.DB_PATH)
    with index.transaction() as conn:
        stats = paramdict.build(conn, sections)
        rows = conn.execute(
            "SELECT category, COUNT(*) c FROM param_dict GROUP BY category ORDER BY c DESC"
        ).fetchall()
        notes = conn.execute(
            "SELECT note, COUNT(*) c FROM param_dict WHERE note != '' GROUP BY note ORDER BY c DESC LIMIT 8"
        ).fetchall()

    print(f"参数语义库：{stats['total']} 条，其中当前官方仍存在 {stats['standard']} 条")
    print("\n类别分布：")
    for row in rows:
        print(f"  {row['category']:<8} {row['c']}")
    print("\n标注：")
    for row in notes:
        print(f"  {row['note']}: {row['c']}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
