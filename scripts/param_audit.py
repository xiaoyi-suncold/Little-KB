"""参数体检：给一份参数表，自动跑常见矛盾/风险检查。

用法：
  python scripts/param_audit.py 四轴
  python scripts/param_audit.py 六轴 --all
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kbcore import config  # noqa: E402


def load(conn, vehicle: str) -> dict[str, str]:
    return {
        row["name"].upper(): (row["value"] or "").strip()
        for row in conn.execute(
            "SELECT name, value FROM params WHERE vehicle = ?", (vehicle,)
        )
    }


def num(p: dict, key: str, default: float | None = None) -> float | None:
    try:
        return float(p.get(key, ""))
    except (TypeError, ValueError):
        return default


def audit(p: dict) -> list[tuple[str, str, str]]:
    """返回 [(级别, 规则, 说明)]，级别 PASS / INFO / WARN / FAIL。"""
    rows: list[tuple[str, str, str]] = []

    def add(level: str, rule: str, msg: str) -> None:
        rows.append((level, rule, msg))

    # 1. 失效保护
    for key, label in (("FENCE_ENABLE", "围栏"), ("BATT_FS_LOW_ACT", "低电量动作"),
                       ("BATT_FS_CRT_ACT", "严重低电量动作")):
        value = num(p, key)
        if value is None:
            add("INFO", key, "参数不存在（旧固件或未收录）")
        elif value == 0:
            add("FAIL", key, f"{label}未启用（值 0）——保护不会动作")
        else:
            add("PASS", key, f"{label}已设（值 {value:g}）")

    # 2. 解锁检查
    arming = num(p, "ARMING_CHECK")
    if arming is not None:
        if arming == 1:
            add("PASS", "ARMING_CHECK", "1 = 全部检查")
        elif arming == 0:
            add("FAIL", "ARMING_CHECK", "0 = 跳过全部检查")
        else:
            add("WARN", "ARMING_CHECK", f"{arming:g} 是位掩码，需按位解析确认跳过了哪些检查")

    # 3. 悬停油门与最小油门
    hover = num(p, "MOT_THST_HOVER")
    spin_min = num(p, "MOT_SPIN_MIN")
    spin_arm = num(p, "MOT_SPIN_ARM")
    if hover is not None:
        if hover < 0.20:
            add("WARN", "MOT_THST_HOVER", f"{hover:.2f} 偏低（默认 0.35，官方范围下限 0.125）：检查推重比与油门曲线标定")
        elif hover > 0.60:
            add("WARN", "MOT_THST_HOVER", f"{hover:.2f} 偏高：动力余量可能不足")
        else:
            add("PASS", "MOT_THST_HOVER", f"{hover:.2f} 在合理区间")
    if hover is not None and spin_min is not None and spin_min >= hover:
        add("FAIL", "MOT_SPIN_MIN", "最小油门 ≥ 悬停油门，飞行中会顶到下限")
    if spin_min is not None and spin_arm is not None and spin_arm > spin_min:
        add("WARN", "MOT_SPIN_ARM", "解锁怠速高于最小油门，起转后可能掉速")

    # 4. 电压自洽：用满电/解锁/低电的比例判断电芯数是否一致
    vmax = num(p, "MOT_BAT_VOLT_MAX")
    arm_v = num(p, "BATT_ARM_VOLT")
    low_v = num(p, "BATT_LOW_VOLT")
    if vmax and arm_v and low_v:
        cells_from_max = vmax / 4.2
        cells_from_arm = arm_v / 3.7
        if abs(cells_from_max - cells_from_arm) / max(cells_from_max, 1) > 0.15:
            add("FAIL", "电压自洽",
                f"MOT_BAT_VOLT_MAX={vmax:g} 约 {cells_from_max:.1f}S，"
                f"BATT_ARM_VOLT={arm_v:g} 约 {cells_from_arm:.1f}S——两套电芯数假设")
        else:
            add("PASS", "电压自洽", f"约 {cells_from_max:.1f}S 一致")
        if low_v >= arm_v:
            add("FAIL", "BATT_LOW_VOLT", "低电量阈值不低于解锁阈值")

    # 5. 姿态与限幅
    rate_max = num(p, "ATC_RATE_R_MAX")
    if rate_max is not None and rate_max > 0:
        add("INFO", "ATC_RATE_R_MAX", f"{rate_max:g}% 限幅：修正输出会被削顶，排查迟钝问题时先看它")
    fltd = num(p, "ATC_RAT_RLL_FLTD")
    gyro = num(p, "INS_GYRO_FILTER")
    if fltd and gyro and fltd > gyro:
        add("WARN", "滤波一致性", f"ATC_RAT_RLL_FLTD={fltd:g} 高于 INS_GYRO_FILTER={gyro:g}，D 项会放大噪声")

    # 6. 罗盘与航向源
    compass_use = num(p, "COMPASS_USE")
    yaw_src = num(p, "EK3_SRC1_YAW")
    if compass_use == 0 and yaw_src in (None, 1):
        add("WARN", "航向源", "罗盘关闭但 EK3_SRC1_YAW 仍指向罗盘，航向会失效")

    # 7. 围栏与返航高度
    f_alt = num(p, "FENCE_ALT_MAX")
    rtl_alt = num(p, "RTL_ALT")
    if f_alt and rtl_alt and rtl_alt / 100 > f_alt:
        add("WARN", "RTL_ALT", f"返航高度 {rtl_alt/100:g}m 超过围栏高度 {f_alt:g}m")

    # 8. 倾角
    angle = num(p, "ATC_ANGLE_MAX", num(p, "ANGLE_MAX"))
    if angle is not None and angle > 4500:
        add("WARN", "角度上限", f"{angle/100:g}° 偏大，位置环与避障更难收敛")

    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vehicle")
    parser.add_argument("--all", action="store_true", help="显示 PASS 项")
    args = parser.parse_args()

    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    params = load(conn, args.vehicle)
    if not params:
        print(f"没有机型 {args.vehicle}")
        return 2

    rows = audit(params)
    order = {"FAIL": 0, "WARN": 1, "INFO": 2, "PASS": 3}
    rows.sort(key=lambda r: order.get(r[0], 9))
    counts = {"FAIL": 0, "WARN": 0, "INFO": 0, "PASS": 0}
    print(f"=== {args.vehicle} 参数体检（{len(params)} 条）===")
    for level, rule, msg in rows:
        counts[level] = counts.get(level, 0) + 1
        if level == "PASS" and not args.all:
            continue
        print(f"[{level:<4}] {rule:<18} {msg}")
    print(f"\nFAIL {counts['FAIL']} · WARN {counts['WARN']} · INFO {counts['INFO']} · PASS {counts['PASS']}")
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
