"""生成参数注释表（xlsx）：以官方 Copter 4.6 参数定义为准，附中文类别与重点解析。"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PDEF = Path(r"D:\ai\deekseep\agent\data\pdef.xml")
PARAM = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版3.param")
OUT = Path(r"D:\ai\deekseep\agent\out\FJ参数注释表_v1_20261102.xlsx")

CATEGORY = [
    ("ANGLE_", "姿态控制"),
    ("ATC_", "姿态控制"), ("PSC_", "位置控制"), ("MOT_", "动力"), ("INS_", "IMU/滤波"),
    ("EK3_", "EKF 滤波"), ("EK2_", "EKF 滤波"), ("AHRS_", "姿态估计"), ("COMPASS_", "罗盘"),
    ("GPS", "GPS"), ("BARO", "气压计"), ("BATT_", "电池"), ("FENCE_", "围栏"),
    ("FS_", "失效保护"), ("ARMING_", "解锁检查"), ("RTL_", "返航"), ("LAND_", "降落"),
    ("WPNAV_", "航线导航"), ("LOIT_", "定点"), ("PILOT_", "操控手感"), ("RC", "遥控"),
    ("SERVO", "输出"), ("SR", "数据流"), ("LOG_", "日志"), ("CAN", "CAN 总线"),
    ("SERIAL", "串口"), ("RELAY", "继电器"), ("RNGFND", "测距仪"), ("PRX_", "避障"),
    ("AVOID_", "避障"), ("ACRO_", "特技"), ("AUTOTUNE_", "自动调参"), ("CHUTE_", "降落伞"),
    ("BTN_", "按钮"), ("STAT_", "统计"), ("SYSID_", "系统 ID"), ("GCS_", "地面站"),
    ("NTF_", "通知"), ("CAM_", "相机"), ("MNT_", "云台"), ("TERRAIN_", "地形"),
    ("TEMP", "温度"), ("BRD_", "板载"), ("FLOW", "光流"), ("WP_", "航线"),
]

NOTES = {
    "MOT_THST_HOVER": "悬停油门（0–1）。按实测 CTUN.ThO 填，不要用 0.35 硬套",
    "MOT_SPIN_MIN": "飞行中最小油门。比悬停油门低 0.05–0.08",
    "MOT_SPIN_ARM": "解锁怠速。略低于 SPIN_MIN，地面可靠起转即可",
    "MOT_THST_EXPO": "油门-推力曲线形状。大桨低盘载 0.5–0.7，小桨高盘载 0.75–0.9",
    "MOT_HOVER_LEARN": "悬停油门自动学习。0=关，2=学习并保存",
    "MOT_BAT_VOLT_MAX": "电压补偿上限，按电芯数×4.2 设置（12S=50.4，14S=58.8）",
    "MOT_BAT_VOLT_MIN": "电压补偿下限，按电芯数×3.3 设置",
    "PSC_POSZ_P": "垂直位置环 P：高度误差→期望速度",
    "PSC_VELZ_P": "垂直速度环 P：速度误差→期望加速度",
    "PSC_ACCZ_P": "垂直加速度环 P：加速度误差→油门",
    "PSC_ACCZ_I": "垂直加速度环 I，消除持续高度偏差，一般取 2×P",
    "PSC_ACCZ_IMAX": "垂直积分上限，防饱和",
    "PSC_JERK_Z": "垂直加加速度限制，压住上下窜",
    "PSC_VELXY_P": "水平速度环 P，刹车与抗风的主要增益",
    "PSC_VELXY_D": "水平速度环 D，刹车末端阻尼；过高会在松杆瞬间产生反向尖峰",
    "ANGLE_MAX": "全模式最大倾角（0.01°），25°=2500",
    "ATC_ANGLE_MAX": "全模式最大倾角（度）",
    "ATC_ANG_YAW_P": "航向角度环 P：航向偏差→期望偏航角速度",
    "ATC_RAT_YAW_P": "偏航角速度环 P",
    "ATC_RAT_YAW_I": "偏航角速度环 I，抗风与反扭的稳态偏差",
    "ATC_RAT_YAW_D": "偏航角速度环 D，抑制停杆回摆",
    "ATC_RAT_YAW_FLTE": "偏航误差滤波（Hz），过低会滞后并导致过冲",
    "ATC_RAT_YAW_FLTD": "偏航 D 项低通（Hz）",
    "ATC_RATE_Y_MAX": "偏航角速度上限（度/秒），0=不限制；限制的是目标角速度，不是输出百分比",
    "ATC_ACCEL_Y_MAX": "偏航角加速度上限（0.01°/s²），决定停杆后多快停下来",
    "ATC_RAT_RLL_P": "横滚角速度环 P",
    "ATC_RAT_RLL_D": "横滚角速度环 D，过高会放大高频振动",
    "ATC_ANG_RLL_P": "横滚角度环 P",
    "ATC_INPUT_TC": "摇杆输入平滑时间常数，越大越柔",
    "WPNAV_SPEED": "航线巡航速度（cm/s）",
    "WPNAV_ACCEL": "航线水平加速度（cm/s²），影响加减速与转弯半径",
    "WPNAV_JERK": "航线加加速度（m/s³），越小越平滑",
    "WPNAV_RADIUS": "航点判定半径（cm），越大越早切向下一点",
    "WPNAV_ACCEL_C": "转弯向心加速度上限（cm/s²），0=2×WPNAV_ACCEL；过小会在拐角刹停",
    "WP_YAW_BEHAVIOR": "航线机头朝向：0=不转 1=面向下一航点 2=除RTL外 3=面向home",
    "LOIT_SPEED": "定点最大速度（cm/s）",
    "LOIT_ANG_MAX": "定点最大倾角（度），0=用 ANGLE_MAX",
    "LOIT_BRK_DELAY": "松杆后多久开始刹车（秒）",
    "LOIT_BRK_JERK": "刹车加加速度（cm/s³），越大刹车建立越快",
    "LOIT_BRK_ACCEL": "刹车减速度上限（cm/s²），上限 250",
    "EK3_SRC1_POSZ": "高度源：1=气压 2=测距 3=GPS",
    "EK3_SRC1_YAW": "航向源：1=罗盘 2=GPS 移动基线 3=GPS",
    "EK3_ALT_M_NSE": "气压高度测量噪声（m），越小越信气压",
    "BATT_ARM_VOLT": "允许解锁的最低电压",
    "BATT_LOW_VOLT": "低电量触发电压",
    "BATT_CRT_VOLT": "严重低电量触发电压",
    "BATT_CAPACITY": "电池容量（mAh），影响电量百分比与保护触发",
    "FENCE_ENABLE": "围栏总开关，1=启用",
    "FENCE_TYPE": "围栏类型位掩码：1=半径 2=多边形 4=最大高度 8=最小高度",
    "ARMING_CHECK": "解锁检查位掩码，1=全部检查（4.8 起改为 ARMING_SKIPCHK）",
    "ARMING_SKIPCHK": "解锁时跳过的检查位掩码，默认 0",
    "INS_GYRO_FILTER": "陀螺低通截止（Hz）",
    "INS_ACCEL_FILTER": "加速度计低通截止（Hz）",
    "INS_HNTCH_ENABLE": "陷波滤波器开关",
    "PILOT_Y_RATE": "摇杆到偏航角速度的映射上限（度/秒）",
}


def _fmt_range(text: str) -> str:
    parts = text.split()
    if len(parts) == 2:
        return f"{parts[0]} ~ {parts[1]}"
    return text


def load_pdef() -> dict[str, dict]:
    tree = etree.parse(str(PDEF))
    meta = {}
    for node in tree.iter("param"):
        full = node.get("name") or ""
        name = full.split(":")[-1].upper()
        fields = {f.get("name"): (f.text or "").strip() for f in node.findall("field")}
        meta[name] = {
            "title": (node.get("humanName") or "").strip(),
            "doc": re.sub(r"\s+", " ", (node.get("documentation") or "")).strip(),
            "range": _fmt_range(fields.get("Range", "")),
            "units": fields.get("Units", ""),
            "values": fields.get("Values", ""),
            "bitmask": fields.get("Bitmask", ""),
            "user": node.get("user", ""),
        }
    return meta


def category_of(name: str) -> str:
    up = name.upper()
    for prefix, cat in CATEGORY:
        if up.startswith(prefix):
            return cat
    return "其他"


def read_param(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [p.strip() for p in re.split(r"[,\s]+", line.strip()) if p.strip()]
        if len(parts) >= 2 and not line.startswith("#"):
            out[parts[0].upper()] = parts[1]
    return out


def main() -> int:
    meta = load_pdef()
    params = read_param(PARAM)
    import json as _json
    import sqlite3 as _sqlite3
    defaults = {}
    try:
        conn = _sqlite3.connect("D:/ai/deekseep/agent/data/kb.sqlite3")
        for name, val in conn.execute("SELECT name, default_value FROM params WHERE default_value != '' GROUP BY name"):
            defaults[name.upper()] = str(val).strip()
        conn.close()
    except Exception:
        pass
    extra_path = Path("D:/ai/deekseep/agent/data/param_defaults_463.json")
    if extra_path.exists():
        defaults.update({k.upper(): v for k, v in _json.loads(extra_path.read_text(encoding="utf-8")).items()})
    print(f"官方定义 {len(meta)} 条，当前参数 {len(params)} 条")

    wb = Workbook()
    ws = wb.active
    ws.title = "参数总表"
    headers = ["参数名", "当前值", "默认值(4.6.3)", "类别", "官方标题", "官方说明", "范围", "单位", "取值/位掩码", "中文速查", "状态"]
    ws.append(headers)
    head_fill = PatternFill("solid", fgColor="1F4E78")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(vertical="center")

    missing = []
    for name in sorted(params):
        rec = meta.get(name)
        status = "官方标准"
        if rec is None:
            rec = {"title": "", "doc": "", "range": "", "units": "", "values": "", "bitmask": ""}
            status = "官方未收录（旧版/厂商）"
            missing.append(name)
        values = rec.get("bitmask") or rec.get("values")
        ws.append([
            name, params[name], defaults.get(name, "—"), category_of(name), rec["title"], rec["doc"][:400],
            (rec["range"] or "—"), (rec["units"] or "—"), (values or "—")[:200],
            NOTES.get(name, ""), status,
        ])

    widths = [22, 14, 16, 12, 30, 70, 16, 16, 30, 44, 20]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:K{ws.max_row}"

    # 第二张表：重点参数
    ws2 = wb.create_sheet("重点参数中文解析")
    ws2.append(["参数名", "当前值", "中文解析", "范围", "单位", "官方说明"])
    for name in NOTES:
        rec = meta.get(name, {})
        ws2.append([name, params.get(name, "—"), NOTES[name],
                    rec.get("range", ""), rec.get("units", ""), rec.get("doc", "")[:300]])
    for i, w in enumerate([22, 14, 60, 16, 16, 80], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    # 第三张表：已知更正
    ws3 = wb.create_sheet("已知更正")
    ws3.append(["项目", "原表写法", "正确写法", "依据"])
    fixes = [
        ("ATC_RATE_Y_MAX", "输出限制（百分比）", "偏航角速度上限，单位 度/秒", "官方文档：Angular Velocity Max for Yaw，范围 0–1080 deg/s"),
        ("ATC_RAT_YAW_I 默认值", "0.18", "0.018（Copter 4.x）", "官方源码默认值/4.6 pdef"),
        ("BATT_CAPACITY", "说明写 47Ah，值为 3300", "按实际电池填写（如 33000 mAh）", "说明与值矛盾，只能实测"),
        ("ANGLE_MAX", "当前固件仍用旧名", "4.8 起改名为 ATC_ANGLE_MAX", "官方 4.8 参数表"),
        ("ARMING_CHECK", "位掩码含义按旧版解释", "4.8 起改为 ARMING_SKIPCHK（跳过项），默认 0", "官方 4.8 参数表"),
        ("PSC_ACCZ_*", "旧名", "4.8 起为 PSC_D_ACC_*，且单位 ×0.1", "官方 4.8 参数表：this is _ACCZ_P * 0.1"),
        ("GPS_TYPE", "旧名", "4.8 起为 GPS1_TYPE", "官方 4.8 参数表"),
        ("MOT_THST_HOVER 说明", "本机 0.16/0.35 混写", "按机型实测，不同机不可照抄", "本库案例 001/003"),
    ]
    for row in fixes:
        ws3.append(list(row))
    for i, w in enumerate([24, 34, 44, 60], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # 第四张表：说明
    ws4 = wb.create_sheet("说明")
    notes = [
        ["数据来源", "ArduPilot ParameterRepository Copter-4.6/apm.pdef.xml（官方参数定义）"],
        ["当前值来源", "XILIU_FJ_自动巡航版3.param"],
        ["官方说明", "保留英文原文，未做机器翻译，避免二次误差"],
        ["中文速查", "仅对常用参数人工核对后填写，空白表示未整理，不代表无意义"],
        ["状态列", "官方标准 / 官方未收录（旧版或厂商定制）"],
        ["范围/单位", "来自官方定义，可能随固件版本变化，以本机固件为准"],
        ["默认值", "未收录：官方 pdef 不含默认值，避免填错；需要时查固件源码或本机参数"],
        ["生成脚本", "scripts/make_param_annotation.py"],
    ]
    ws4.append(["项目", "内容"])
    for row in notes:
        ws4.append(row)
    ws4.column_dimensions["A"].width = 18
    ws4.column_dimensions["B"].width = 90

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"写出 {OUT}（{len(params)} 行）")
    print(f"官方未收录：{len(missing)} 项，例如 {missing[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
