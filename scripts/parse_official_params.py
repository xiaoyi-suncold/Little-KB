"""从官方 Copter 参数文档提取参数元数据（v2：正确处理多列表头与括号后缀）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lxml import etree

HTML = Path(r"C:\Users\84216\AppData\Local\Temp\copter_params.html")
OUT = Path(r"D:\ai\deekseep\agent\data\official_param_meta.json")
NAME_RE = re.compile(r"^([A-Z][A-Z0-9_]{2,40})(?:\s*\([^)]*\))?\s*:\s*(.*)$")


def text_of(node) -> str:
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def in_table(node) -> bool:
    parent = node.getparent()
    while parent is not None:
        if parent.tag == "table":
            return True
        parent = parent.getparent()
    return False


def parse() -> dict:
    tree = etree.parse(str(HTML), etree.HTMLParser(recover=True))
    root = tree.getroot()
    meta: dict[str, dict] = {}

    for h3 in root.iter("h3"):
        raw = text_of(h3).replace("¶", "").strip()
        m = NAME_RE.match(raw)
        if not m:
            continue
        name, title = m.group(1), m.group(2).strip()
        section = h3.getparent()
        while section is not None and section.tag != "section":
            section = section.getparent()
        if section is None:
            continue

        desc_parts = [text_of(p) for p in section.iter("p")
                      if not in_table(p) and not text_of(p).startswith("Note:")]
        rec = {
            "title": title,
            "desc": " ".join(dict.fromkeys(d for d in desc_parts if d))[:600],
            "range": "", "units": "", "default": "", "values": "",
        }
        for table in section.iter("table"):
            headers = [text_of(th) for th in table.iter("th")]
            body_rows = table.xpath("./tbody/tr")
            if not headers or not body_rows:
                continue
            cells = [text_of(td) for td in body_rows[0].xpath("./td")]
            for h, v in zip(headers, cells):
                h, v = h.strip().lower(), v.strip()
                if h.startswith("range"):
                    rec["range"] = v[:80]
                elif h.startswith("unit"):
                    rec["units"] = v[:40]
                elif h.startswith("default"):
                    rec["default"] = v[:40]
                elif h.startswith(("values", "bitmask")):
                    all_vals = " / ".join(text_of(r) for r in body_rows)[:240]
                    rec["values"] = all_vals
        meta[name] = rec
    return meta


if __name__ == "__main__":
    meta = parse()
    OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"提取 {len(meta)} 个参数")
    for probe in ["MOT_THST_HOVER", "ATC_RATE_Y_MAX", "ATC_ANGLE_MAX", "ATC_RAT_YAW_FLTE",
                  "ATC_RAT_YAW_D", "WPNAV_RADIUS"]:
        r = meta.get(probe)
        print(probe, "->", None if not r else {k: (v[:60] if isinstance(v, str) else v) for k, v in r.items()})
