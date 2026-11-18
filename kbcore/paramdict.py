"""参数字典：只保留「这个参数是什么意思」，不关心某台机的当前值。

数据来源：两份参数表的「作用说明 / 调参提示」列，按参数名去重合并；
再用 ArduPilot 官方文档的 section 锚点判断它是否仍是当前版本的标准参数，
并标注已知的改名关系（旧名 → 新名）。
"""

from __future__ import annotations

import re
from pathlib import Path

# 已核对的改名关系（旧名 → 新名），依据 ArduPilot Copter 4.8 参数文档
RENAMES = {
    "ANGLE_MAX": "ATC_ANGLE_MAX",
    "ARMING_CHECK": "ARMING_SKIPCHK",
    "GPS_TYPE": "GPS1_TYPE",
    "GPS_RATE_MS": "GPS1_RATE_MS",
    "GPS_POS1_X": "GPS1_POS_X",
    "GPS_POS1_Y": "GPS1_POS_Y",
    "GPS_POS1_Z": "GPS1_POS_Z",
    "GPS_POS2_X": "GPS2_POS_X",
    "GPS_POS2_Y": "GPS2_POS_Y",
    "GPS_POS2_Z": "GPS2_POS_Z",
    "GPS_MB_OFS_X": "GPS_MB1_OFS_X",
    "GPS_MB_OFS_Y": "GPS_MB1_OFS_Y",
    "GPS_MB_OFS_Z": "GPS_MB1_OFS_Z",
    "GPS_MB_TYPE": "GPS_MB1_TYPE",
    "PSC_POSXY_P": "PSC_NE_POS_P",
    "PSC_VELXY_P": "PSC_NE_VEL_P",
    "PSC_VELXY_I": "PSC_NE_VEL_I",
    "PSC_VELXY_D": "PSC_NE_VEL_D",
    "PSC_POSZ_P": "PSC_D_POS_P",
    "PSC_VELZ_P": "PSC_D_VEL_P",
    "PSC_VELZ_I": "PSC_D_VEL_I",
    "PSC_VELZ_D": "PSC_D_VEL_D",
    "PSC_ACCZ_P": "PSC_D_ACC_P",
    "PSC_ACCZ_I": "PSC_D_ACC_I",
    "PSC_ACCZ_D": "PSC_D_ACC_D",
    "PSC_ACCZ_IMAX": "PSC_D_ACC_IMAX",
}

# 厂商定制 / 非 Copter 参数（文档中不存在，且不属于改名）
KNOWN_CUSTOM = {
    "WATER_PUMP_AUTO": "厂商定制的喷洒泵控制",
    "SURFTRAK_AUTO": "ArduPilot 水面跟踪（Sub/Rover）参数，非 Copter",
    "SURFTRAK_MODE": "同上",
    "GPS_CAN_NODEID1": "厂商或旧版 CAN GPS 参数",
    "GPS_CAN_NODEID2": "同上",
    "BTN_DEBOUNCE_MS": "厂商定制按钮",
    "BTN_REPORT_SEND": "厂商定制按钮",
}

CATEGORY_ORDER = [
    "姿态控制", "姿态限制", "姿态估计", "位置控制", "动力", "电池", "失效保护",
    "解锁/安全", "围栏", "航点导航", "自动模式", "模式", "EKF滤波", "IMU", "罗盘",
    "GPS", "气压计", "测距仪", "气压", "数据流", "遥控", "输出", "CAN总线", "串口",
]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


MACHINE_PATTERNS = [
    r"[；，]?\s*本机[^；。]*?(?=[；。]|$)",
    r"[；，]?\s*当前\s*[^；。]*?\d[^；。]*?(?=[；。]|$)",
    r"[；，]?\s*(?:v\d+\s*取|取)\s*[\d.]+",
    r"[；，]?\s*ThO\s*[≈=]\s*[\d.]+",
]


def strip_machine_values(text: str) -> str:
    """去掉作者针对某一台机写的具体取值，只留语义。

    「悬停油门前馈值（0–1）。本机日志稳定悬停 ThO≈0.156」→「悬停油门前馈值（0–1）」
    """
    original = _clean(text)
    cleaned = original
    for pattern in MACHINE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"[；，。：]{2,}", lambda m: "。" if "。" in m.group(0) else m.group(0)[0], cleaned)
    cleaned = cleaned.replace("：。", "。").replace("；。", "。").replace("，。", "。")
    cleaned = re.sub(r"[；，]\s*(?=[；。]|$)", "", cleaned)
    cleaned = re.sub(r"[；，。：]+$", "", cleaned).strip()
    return cleaned if len(cleaned) >= 6 else original


def _merge_hints(items: list[str]) -> str:
    seen, out = set(), []
    for item in items:
        item = _clean(item)
        if not item or item in seen:
            continue
        # 去掉重复前缀的短句
        if any(item in existing for existing in out):
            continue
        out = [x for x in out if x not in item] + [item]
        seen.add(item)
    return "；".join(out[:2])


def is_standard(name: str, sections: set[str]) -> bool:
    slug = name.lower().replace("_", "-")
    if slug in sections:
        return True
    prefix = slug + "-"
    return any(section.startswith(prefix) for section in sections)


def build(conn, sections: set[str]) -> dict:
    rows = conn.execute(
        "SELECT name, vehicle, category, desc, hint FROM params ORDER BY name"
    ).fetchall()

    merged: dict[str, dict] = {}
    for row in rows:
        name = row["name"]
        item = merged.setdefault(
            name,
            {"name": name, "category": row["category"], "desc": [], "hint": [], "vehicles": set()},
        )
        item["vehicles"].add(row["vehicle"])
        if row["desc"]:
            item["desc"].append(_clean(row["desc"]))
        if row["hint"]:
            item["hint"].append(_clean(row["hint"]))
        if not item["category"] and row["category"]:
            item["category"] = row["category"]

    records = []
    for name, item in merged.items():
        descs = sorted((strip_machine_values(d) for d in set(item["desc"])), key=len, reverse=True)
        hint = _merge_hints([strip_machine_values(h) for h in item["hint"]])
        standard = is_standard(name, sections)
        renamed = RENAMES.get(name, "")
        custom = KNOWN_CUSTOM.get(name, "")
        note = ""
        if custom:
            note = custom
        elif renamed:
            note = f"4.8 更名为 {renamed}"
        elif not standard:
            note = "未在当前官方文档检索到（旧版/厂商/已废弃）"
        records.append(
            {
                "name": name,
                "category": item["category"] or "未分类",
                "meaning": descs[0] if descs else "",
                "hint": hint,
                "vehicles": ",".join(sorted(item["vehicles"])),
                "standard": 1 if standard else 0,
                "renamed_to": renamed,
                "note": note,
            }
        )

    conn.execute("DELETE FROM param_dict")
    conn.executemany(
        """INSERT INTO param_dict
           (name, category, meaning, hint, vehicles, standard, renamed_to, note)
           VALUES (?,?,?,?,?,?,?,?)""",
        [
            (
                r["name"], r["category"], r["meaning"], r["hint"], r["vehicles"],
                r["standard"], r["renamed_to"], r["note"],
            )
            for r in records
        ],
    )
    conn.commit()
    return {"total": len(records), "standard": sum(r["standard"] for r in records)}


def lookup(conn, name: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM param_dict WHERE upper(name) = upper(?)", (name.strip(),)
    ).fetchone()
    return dict(row) if row else None


def by_category(conn, category: str | None = None, limit: int = 500) -> list[dict]:
    if category:
        rows = conn.execute(
            "SELECT name, category, meaning FROM param_dict WHERE category = ?"
            " ORDER BY name LIMIT ?",
            (category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT category, COUNT(*) c FROM param_dict GROUP BY category ORDER BY c DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def search(conn, keyword: str, limit: int = 30) -> list[dict]:
    like = f"%{keyword.strip()}%"
    rows = conn.execute(
        "SELECT name, category, meaning, note FROM param_dict"
        " WHERE name LIKE ? OR meaning LIKE ? OR hint LIKE ?"
        " ORDER BY standard DESC, name LIMIT ?",
        (like, like, like, limit),
    ).fetchall()
    return [dict(r) for r in rows]
