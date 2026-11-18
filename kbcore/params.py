"""参数级知识库：把参数表拆成一行一个参数，支持按名字精确查询。

和全文索引的区别：全文索引回答「哪篇文档提到它」，这里回答「四轴机的
MOT_THST_HOVER 到底是多少、说明是什么、默认值是多少」。
"""

from __future__ import annotations

import re
from pathlib import Path

COLUMNS = ("name", "value", "category", "desc", "hint", "default_value")
VEHICLE_HINTS = (("四轴", "四轴"), ("六轴", "六轴"), ("四旋翼", "四轴"), ("六旋翼", "六轴"))


def detect_vehicle(path: Path) -> str:
    name = path.stem
    for token, vehicle in VEHICLE_HINTS:
        if token in name:
            return vehicle
    return name[:20]


def read_workbook(path: Path) -> list[dict]:
    """独立读取（非 read_only），便于与流式读取互相校验。

    openpyxl 为可选依赖：只有解析 Excel 参数表时才需要，
    缺失时返回空列表，不影响知识库其余功能。
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return []
    book = load_workbook(path, data_only=True, read_only=False)
    sheet = book.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    next(rows, None)
    out: list[dict] = []
    for row in rows:
        cells = list(row) + [None] * len(COLUMNS)
        name = str(cells[0] or "").strip()
        if not name or name == "参数名":
            continue
        record = {}
        for i, key in enumerate(COLUMNS):
            cell = cells[i]
            record[key] = "" if cell is None else str(cell).strip()
        out.append(record)
    book.close()
    return out


def import_workbook(conn, path: Path, vehicle: str | None = None, doc_id: int | None = None) -> dict:
    vehicle = vehicle or detect_vehicle(path)
    records = read_workbook(path)
    if not records:
        return {"vehicle": vehicle, "imported": 0}
    conn.executemany(
        """INSERT INTO params (vehicle, name, value, category, desc, hint, default_value, source, doc_id)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(vehicle, name) DO UPDATE SET
             value=excluded.value, category=excluded.category, desc=excluded.desc,
             hint=excluded.hint, default_value=excluded.default_value,
             source=excluded.source, doc_id=excluded.doc_id""",
        [
            (
                vehicle,
                r["name"],
                r["value"],
                r["category"],
                r["desc"],
                r["hint"],
                r["default_value"],
                str(path),
                doc_id,
            )
            for r in records
        ],
    )
    conn.commit()
    return {"vehicle": vehicle, "imported": len(records)}


def read_param_file(path: Path) -> dict[str, str]:
    """读取 ArduPilot .param 文本（NAME,VALUE / NAME VALUE 两种格式）。"""
    out: dict[str, str] = {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in re.split(r"[,\s]+", line) if p.strip()]
        if len(parts) >= 2 and parts[0].replace("_", "").isalnum():
            out[parts[0].upper()] = parts[1]
    return out


def import_param_file(conn, path: Path, vehicle: str) -> dict:
    values = read_param_file(path)
    if not values:
        return {"vehicle": vehicle, "imported": 0}
    rows = []
    for name, value in values.items():
        rows.append((vehicle, name, value, "", "", "", "", str(path), None))
    conn.executemany(
        """INSERT INTO params (vehicle, name, value, category, desc, hint, default_value, source, doc_id)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(vehicle, name) DO UPDATE SET value=excluded.value, source=excluded.source""",
        rows,
    )
    conn.commit()
    return {"vehicle": vehicle, "imported": len(rows)}


def lookup(conn, name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT vehicle, name, value, category, desc, hint, default_value, source"
        " FROM params WHERE upper(name) = upper(?) ORDER BY vehicle",
        (name.strip(),),
    ).fetchall()
    return [dict(r) for r in rows]


def search(conn, keyword: str, limit: int = 40) -> list[dict]:
    like = f"%{keyword.strip()}%"
    rows = conn.execute(
        "SELECT vehicle, name, value, category, desc FROM params"
        " WHERE name LIKE ? OR desc LIKE ? OR category LIKE ?"
        " ORDER BY name, vehicle LIMIT ?",
        (like, like, like, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def stats(conn) -> dict:
    rows = conn.execute(
        "SELECT vehicle, COUNT(*) c, SUM(CASE WHEN value = '' THEN 1 ELSE 0 END) empty"
        " FROM params GROUP BY vehicle"
    ).fetchall()
    return {"vehicles": [dict(r) for r in rows]}


def diff(conn, a: str, b: str) -> dict:
    """两个载具之间的参数差异（只比较两边都有值的）。"""
    qa = {
        r["name"]: r["value"]
        for r in conn.execute("SELECT name, value FROM params WHERE vehicle = ?", (a,))
    }
    qb = {
        r["name"]: r["value"]
        for r in conn.execute("SELECT name, value FROM params WHERE vehicle = ?", (b,))
    }
    common = set(qa) & set(qb)
    return {
        "a": a,
        "b": b,
        "only_a": sorted(set(qa) - set(qb)),
        "only_b": sorted(set(qb) - set(qa)),
        "changed": sorted(
            k for k in common if _norm(qa[k]) != _norm(qb[k])
        ),
    }


def _norm(value: str) -> str:
    text = (value or "").strip().lower()
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return f"{float(text):.6g}"
    return text
