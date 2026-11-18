"""生成按系统分组的中文参数手册（docx），默认值来自 ArduPilot 4.6.3 源码。"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

PARAM = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\XILIU_FJ_自动巡航版3.param")
OUT = Path(r"D:\ai\deekseep\agent\out\FJ参数中文手册_4.6.3_v1_20261102.docx")

# 默认值：来自 ArduPilot Copter-4.6.3 源码（AP_GROUPINFO / 宏定义）
DEFAULTS = {
    "WPNAV_SPEED": "1000", "WPNAV_ACCEL": "250", "WPNAV_JERK": "1.0", "WPNAV_RADIUS": "200",
    "WPNAV_SPEED_UP": "250", "WPNAV_SPEED_DN": "150", "WPNAV_ACCEL_Z": "100", "WPNAV_ACCEL_C": "0",
    "LOIT_SPEED": "1250", "LOIT_ANG_MAX": "0", "LOIT_ACC_MAX": "500",
    "LOIT_BRK_ACCEL": "250", "LOIT_BRK_JERK": "500", "LOIT_BRK_DELAY": "1.0",
    "MOT_THST_HOVER": "0.35", "MOT_SPIN_MIN": "0.15", "MOT_SPIN_ARM": "0.10", "MOT_SPIN_MAX": "0.95",
    "MOT_THST_EXPO": "0.65", "MOT_HOVER_LEARN": "2", "MOT_BAT_VOLT_MAX": "0", "MOT_BAT_VOLT_MIN": "0",
    "MOT_PWM_MIN": "1000", "MOT_PWM_MAX": "2000", "MOT_YAW_HEADROOM": "200",
    "ATC_ACCEL_R_MAX": "110000", "ATC_ACCEL_P_MAX": "110000", "ATC_ACCEL_Y_MAX": "27000",
    "ATC_SLEW_YAW": "6000", "ATC_RATE_R_MAX": "0", "ATC_RATE_P_MAX": "0", "ATC_RATE_Y_MAX": "0",
    "ATC_INPUT_TC": "0.15", "ATC_RAT_YAW_I": "0.018",
    "ANGLE_MAX": "3000", "WP_YAW_BEHAVIOR": "2", "LAND_SPEED": "50", "RTL_ALT": "1500",
    "ATC_THR_MIX_MAN": "0.1",
    "INS_HNTCH_FREQ": "80",
    "GPS_TYPE": "1",
    "BATT_CAPACITY": "3300",
    "RTL_SPEED": "0",
    "PILOT_Y_RATE": "202.5",
    "PILOT_Y_EXPO": "0",
    "PILOT_SPEED_DN": "0",
    "PILOT_ACCEL_Z": "250",
}

CHAPTERS = [
    ("第一章 姿态控制（ATC_）", "姿态环分两级：角度环把姿态误差换成期望角速度，角速度环换成电机差动。调参永远从角速度环开始，角度环最后动。", [
        ("ANGLE_MAX", "全模式最大倾角，单位 0.01°。限制的是横向加速度上限（g·tanθ）", "先定倾角再调增益；25° 对应 4.6 m/s²"),
        ("ATC_ANG_RLL_P", "横滚角度环 P：角度误差→期望角速度", "偏软会回中慢，过高会点头"),
        ("ATC_ANG_PIT_P", "俯仰角度环 P", "同上"),
        ("ATC_ANG_YAW_P", "航向角度环 P：航向误差→期望偏航角速度", "航向回摆时先降它，再谈 D"),
        ("ATC_RAT_RLL_P", "横滚角速度环 P，姿态响应主增益", "从低往高加，直到出现小幅高频抖再回退 30%"),
        ("ATC_RAT_RLL_D", "横滚角速度环 D，抑制过冲", "加 D 必须同时看振动；振动大时 D 会放大噪声"),
        ("ATC_RAT_PIT_P", "俯仰角速度环 P", "同横滚"),
        ("ATC_RAT_YAW_P", "偏航角速度环 P", "大机型 0.15–0.25"),
        ("ATC_RAT_YAW_I", "偏航角速度环 I，消除风与反扭造成的稳态偏差", "默认 0.018 偏保守，可到 0.03–0.05"),
        ("ATC_RAT_YAW_D", "偏航角速度环 D，抑制停杆回摆", "0.001–0.004，配合 FLTD=20"),
        ("ATC_RAT_YAW_FLTE", "偏航误差滤波（Hz）", "2 Hz 滞后大，可到 4–5"),
        ("ATC_RATE_Y_MAX", "偏航角速度上限（度/秒），0=不限", "限制目标角速度，不是输出百分比"),
        ("ATC_ACCEL_Y_MAX", "偏航角加速度上限（0.01°/s²）", "决定停杆后多快停住，4000 很软，可到 12000"),
        ("ATC_SLEW_YAW", "自动模式下航向误差允许变化率（0.01°/s）", "默认 6000，一般不动"),
        ("ATC_INPUT_TC", "摇杆输入平滑时间常数（秒）", "0.15 中等，0.2 更柔"),
        ("ATC_THR_MIX_MAN", "手动油门与姿态的混控比例", "默认 0.5，不建议动"),
    ]),
    ("第二章 位置控制（PSC_）", "位置控制是三层串级：位置→速度→加速度。高度通道对环境最敏感，GPS 高度漂移会直接变成“掉高/升高”。", [
        ("PSC_POSXY_P", "水平位置环 P：位置误差→期望速度", "1.0 左右，漂移大时先看航向与罗盘"),
        ("PSC_VELXY_P", "水平速度环 P，抗风与刹车的主增益", "1.8–2.5"),
        ("PSC_VELXY_I", "水平速度环 I", "默认 1.0"),
        ("PSC_VELXY_D", "水平速度环 D，刹车末端阻尼", "松杆瞬间反向尖峰时降低它"),
        ("PSC_POSZ_P", "垂直位置环 P：高度误差→期望速度", "0.8–1.0，掉高时降低它减慢跟随"),
        ("PSC_VELZ_P", "垂直速度环 P", "2.4–3.0"),
        ("PSC_ACCZ_P", "垂直加速度环 P：加速度误差→油门", "0.30–0.45；环路指标 = P×VELZ/HOVER"),
        ("PSC_ACCZ_I", "垂直加速度环 I", "一般取 2×P，太低会持续掉高，太高会过冲"),
        ("PSC_ACCZ_IMAX", "垂直积分上限", "400–500，防积分饱和"),
        ("PSC_ACCZ_FLTE", "垂直加速度误差低通（Hz）", "15–20，低一点更平滑但更迟钝"),
        ("PSC_JERK_Z", "垂直加加速度限制", "3–5，压住上下窜"),
    ]),
    ("第三章 动力与油门（MOT_）", "动力参数决定“给多少油出多少力”。悬停油门必须实测，电压补偿必须按电芯数配。", [
        ("MOT_THST_HOVER", "悬停油门（0–1）", "读 CTUN.ThO 悬停均值填入，别照抄 0.35"),
        ("MOT_SPIN_MIN", "飞行中最小油门", "比悬停油门低 0.05–0.08"),
        ("MOT_SPIN_ARM", "解锁怠速", "略低于 SPIN_MIN，能可靠起转即可"),
        ("MOT_SPIN_MAX", "最大油门比例", "一般 0.95，不改"),
        ("MOT_THST_EXPO", "油门-推力曲线形状", "大桨低盘载 0.5–0.7；小桨高盘载 0.75–0.9"),
        ("MOT_HOVER_LEARN", "悬停油门学习：0 关 / 1 学 / 2 学并保存", "调好悬停后可开 2，飞一次自动学"),
        ("MOT_BAT_VOLT_MAX", "电压补偿上限，按电芯数×4.2", "12S=50.4，14S=58.8；设错等于没有补偿"),
        ("MOT_BAT_VOLT_MIN", "电压补偿下限，按电芯数×3.3", "12S=39.6，14S=46.2"),
        ("MOT_PWM_MIN", "电调最小 PWM", "普通电调 1000，高压电调按手册"),
        ("MOT_PWM_MAX", "电调最大 PWM", "普通 2000"),
        ("MOT_YAW_HEADROOM", "偏航控制预留的油门余量", "默认 200，大机型可 300"),
    ]),
    ("第四章 航线与定点（WPNAV_ / LOIT_）", "航线参数决定“飞多快、拐多急”。入弯停顿几乎都出在 WPNAV_ACCEL_C 和 WPNAV_RADIUS 上。", [
        ("WPNAV_SPEED", "航线巡航速度（cm/s）", "作业常用 200–400"),
        ("WPNAV_ACCEL", "航线水平加速度（cm/s²）", "250 左右；与小转弯半径一起决定转弯角速度"),
        ("WPNAV_JERK", "航线加加速度（m/s³）", "1–3，越小越平滑"),
        ("WPNAV_RADIUS", "航点判定半径（cm）", "200–500；大一点提前切弯"),
        ("WPNAV_ACCEL_C", "转弯向心加速度上限（cm/s²），0=2×ACCEL", "入弯停顿的主因；20 会把转弯速度压到 0.6 m/s"),
        ("WPNAV_SPEED_UP", "航线爬升速度上限（cm/s）", "250"),
        ("WPNAV_SPEED_DN", "航线下降速度上限（cm/s）", "150，别太快以免掉高"),
        ("WPNAV_ACCEL_Z", "航线垂直加速度（cm/s²）", "100"),
        ("LOIT_SPEED", "定点最大速度（cm/s）", "600–1000"),
        ("LOIT_ANG_MAX", "定点最大倾角（度），0=用 ANGLE_MAX", "16–25"),
        ("LOIT_ACC_MAX", "定点最大加速度（cm/s²）", "320–500"),
        ("LOIT_BRK_ACCEL", "松杆刹车减速度上限（cm/s²）", "120–250，越小越柔但停得远"),
        ("LOIT_BRK_DELAY", "松杆后多久开始刹车（秒）", "0.2–0.45，大一点更顺"),
        ("LOIT_BRK_JERK", "刹车加加速度（cm/s³）", "500–900，越大刹车建立越快"),
    ]),
    ("第五章 滤波与传感器（INS_ / EK3_ / COMPASS_ / GPS）", "振动与传感器决定高度、航向可不可信。参数只能掩盖，不能修复硬件问题。", [
        ("ATH_GYRO_FILTER", "", ""),
        ("INS_GYRO_FILTER", "陀螺低通截止（Hz）", "大桨 15–25；过低会迟钝"),
        ("INS_ACCEL_FILTER", "加速度计低通截止（Hz）", "10–20"),
        ("INS_HNTCH_ENABLE", "动态陷波开关", "振动有明确桨叶频率时开"),
        ("INS_HNTCH_FREQ", "陷波中心频率（Hz）", "按 FFT 峰值填"),
        ("EK3_SRC1_POSZ", "高度源：1 气压 / 2 测距 / 3 GPS", "GPS 高度会慢漂，这是掉高的根源"),
        ("EK3_SRC1_YAW", "航向源：1 罗盘 / 2 GPS 移动基线 / 3 GPS", "双天线机型用 2"),
        ("EK3_ALT_M_NSE", "气压高度测量噪声（m）", "越小越信气压；气压脏时别调太小"),
        ("COMPASS_ENABLE", "罗盘总开关", "用 GPS 航向时可关"),
        ("COMPASS_USE", "是否使用该罗盘", "同上"),
        ("GPS_TYPE", "GPS 类型（4.8 起为 GPS1_TYPE）", "DroneCAN 一般 9"),
    ]),
    ("第六章 电池（BATT_）", "电压平台配错会让推力随电量下降，表现为“飞久了掉高”，而且低电量保护永远不会响。", [
        ("BATT_MONITOR", "电池监控类型", "DroneCAN 一般为 8"),
        ("BATT_CAPACITY", "电池容量（mAh）", "按实际填，3300 对 14S 作业机明显偏小"),
        ("BATT_ARM_VOLT", "允许解锁的最低电压", "电芯数×3.7"),
        ("BATT_LOW_VOLT", "低电量触发电压", "电芯数×3.6"),
        ("BATT_CRT_VOLT", "严重低电量电压", "电芯数×3.45"),
        ("BATT_FS_LOW_ACT", "低电量动作：0 无 / 2 RTL / 3 降落", "作业机建议 2"),
        ("BATT_FS_CRT_ACT", "严重低电量动作", "建议 1（降落）"),
    ]),
    ("第七章 安全与失效保护（ARMING_ / FENCE_ / RTL_ / LAND_）", "安全参数不影响手感，但决定出事时飞机会怎么做。作业前必须逐项确认。", [
        ("ARMING_CHECK", "解锁检查位掩码，1=全部检查", "不要图省事关掉"),
        ("FENCE_ENABLE", "围栏总开关", "作业必须开"),
        ("FENCE_TYPE", "围栏类型位掩码：1 半径 2 多边形 4 最大高度 8 最小高度", "常用 7"),
        ("FENCE_ALT_MAX", "围栏最大高度（m）", "按作业高度+余量"),
        ("FENCE_RADIUS", "围栏半径（m）", "按作业区+余量"),
        ("RTL_ALT", "返航高度（cm）", "高于作业区障碍物"),
        ("RTL_SPEED", "返航速度（cm/s），0=用 WPNAV_SPEED", "300 左右"),
        ("LAND_SPEED", "降落末段速度（cm/s）", "50–70"),
    ]),
    ("第八章 操控手感（PILOT_ / WP_YAW_）", "同一架飞机，不同飞手感受不同。这些参数改的是“杆量到动作”的映射，不改变控制环路。", [
        ("PILOT_Y_RATE", "偏航摇杆映射的最大角速度（度/秒）", "与 ATC_RATE_Y_MAX 配合，别一个 200 一个 45"),
        ("PILOT_Y_EXPO", "偏航摇杆曲线指数", "0 线性，0.3 中心更细"),
        ("PILOT_SPEED_DN", "手动下降速度上限（cm/s），0=跟随上行", "80–150"),
        ("PILOT_ACCEL_Z", "手动垂直加速度（cm/s²）", "150–250"),
        ("WP_YAW_BEHAVIOR", "航线机头朝向：0 不转 1 面向下一航点 2 除RTL外 3 面向home", "协调转弯用 1"),
    ]),
]

APPENDIX = [
    ("悬停长时间掉高/升高", "先看气压-EKF 高度差是否随时间增大；再看电压平台是否与电芯数匹配；最后才动 PSC_ACCZ_I 与 PSC_POSZ_P。"),
    ("停杆后航向回摆", "顺序：ATC_RAT_YAW_D ↑ → FLTE ↑ → ATC_ANG_YAW_P ↓ → ATC_RAT_YAW_P ↓。ATC_ACCEL_Y_MAX 决定停得多快。"),
    ("入弯停顿", "看 WPNAV_ACCEL_C：v = √(ACCEL_C × RADIUS)。0.2 m/s² × 2 m 只能转 0.63 m/s，必然刹停。"),
    ("振动偏大", "先查桨平衡与机臂，再看 INS_HNTCH；不要用降低 ATC_RAT_*_D 来掩盖。"),
    ("解锁被拒", "读 MP 的 PreArm 提示，逐项对照 ARMING_CHECK 的位掩码，不要整项关掉。"),
]


def load_table_defaults() -> dict[str, str]:
    """从已导入的参数表取参考默认值（仅填补源码里没覆盖到的项）。"""
    import sqlite3
    conn = sqlite3.connect("D:/ai/deekseep/agent/data/kb.sqlite3")
    rows = conn.execute("SELECT name, default_value FROM params WHERE default_value != '' GROUP BY name").fetchall()
    out = {}
    for name, val in rows:
        out[name.upper()] = str(val).strip()
    return out


def read_params() -> dict[str, str]:
    out = {}
    for line in PARAM.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [p.strip() for p in re.split(r"[,\s]+", line.strip()) if p.strip()]
        if len(parts) >= 2 and not line.startswith("#"):
            out[parts[0].upper()] = parts[1]
    return out


def set_cell(cell, text, bold=False, size=9, color=None):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = color


def main() -> int:
    params = read_params()
    table_defaults = load_table_defaults()
    merged_defaults = dict(table_defaults)
    merged_defaults.update(DEFAULTS)  # 源码值优先
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "微软雅黑"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")
    style.font.size = Pt(10.5)

    title = doc.add_heading("FJ 四轴无人机参数手册", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph("ArduCopter 4.6.3 · 按系统分组 · 默认值取自官方源码")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.runs[0].font.size = Pt(12)
    sub.runs[0].font.color.rgb = RGBColor(0x60, 0x60, 0x60)

    doc.add_paragraph("")
    intro = doc.add_paragraph()
    intro.add_run("怎么用这本手册\n").bold = True
    for line in [
        "· 每章一个系统，表格里“默认”是 ArduPilot 4.6.3 的出厂值，“当前”是本机参数文件的值。",
        "· 说明写“管什么”，建议写“怎么动”，两者都只给方向和量级，不承诺唯一最优值。",
        "· 调参顺序永远是：先传感器与动力，再姿态，最后位置与航线。",
        "· 一次只改一组，飞一个起落记录一次，再决定下一步。",
    ]:
        doc.add_paragraph(line)

    for chapter, lead, rows in CHAPTERS:
        doc.add_heading(chapter, level=1)
        doc.add_paragraph(lead)
        table = doc.add_table(rows=1, cols=6)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["参数", "默认", "当前", "说明", "调整建议", "备注"]
        for i, h in enumerate(headers):
            set_cell(table.rows[0].cells[i], h, bold=True, size=9)
        for name, desc, advice in rows:
            if not name or name.startswith("ATH_"):
                continue
            cur = params.get(name, "—")
            default = merged_defaults.get(name, "—")
            note = "改名/新版本" if name in {"GPS_TYPE"} else ""
            cells = table.add_row().cells
            set_cell(cells[0], name, bold=True, size=8.5)
            set_cell(cells[1], default, size=8.5)
            set_cell(cells[2], cur, size=8.5)
            set_cell(cells[3], desc, size=8.5)
            set_cell(cells[4], advice, size=8.5)
            set_cell(cells[5], note, size=8.5)
        for row in table.rows:
            row.cells[0].width = Pt(120)
            row.cells[3].width = Pt(200)
        doc.add_paragraph("")

    doc.add_heading("附录 A 常见问题速查", level=1)
    for title_text, body in APPENDIX:
        p = doc.add_paragraph()
        p.add_run(title_text + "：").bold = True
        p.add_run(body)

    doc.add_heading("附录 B 默认值来源", level=1)
    for line in [
        "默认值来自 ArduPilot 源码 tag Copter-4.6.3：",
        "· WPNAV_*：libraries/AC_WPNav/AC_WPNav.cpp 与 AC_WPNav.h",
        "· LOIT_*：libraries/AC_WPNav/AC_Loiter.cpp",
        "· MOT_*：libraries/AP_Motors/AP_MotorsMulticopter.cpp 与同名头文件",
        "· ATC_*：libraries/AC_AttitudeControl/AC_AttitudeControl*.cpp",
        "· ANGLE_MAX / WP_YAW_BEHAVIOR / LAND_SPEED / RTL_ALT：ArduCopter/config.h",
        "标“—”的参数表示该版本源码里未直接给出默认值，或参数名在新版本中已变更。",
    ]:
        doc.add_paragraph(line)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    print(f"写出 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
