"""把飞行日志画成图，并做姿态跟踪、电机均衡、振动相关性分析。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from pymavlink import mavutil

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

BIN = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\2026-11-02 16-38-06.bin")
CACHE = Path(r"D:\ai\deekseep\agent\data\jldh\health_plot.npz")
FIG = Path(r"D:\ai\deekseep\agent\out\figs")
TYPES = ["MODE", "CTUN", "BAT", "VIBE", "GPS", "ATT", "RCOU", "BARO"]


def parse() -> dict:
    if CACHE.exists():
        return dict(np.load(CACHE, allow_pickle=True))
    m = mavutil.mavlink_connection(str(BIN), robust_parsing=True)
    rows = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        k = msg.get_type()
        if k == "MODE":
            rows[k].append((t, int(msg.Mode)))
        elif k == "CTUN":
            rows[k].append((t, float(msg.ThO), float(msg.Alt), float(getattr(msg, "DAlt", 0))))
        elif k == "BAT":
            rows[k].append((t, float(msg.Volt), float(msg.Curr)))
        elif k == "VIBE":
            rows[k].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ),
                            int(getattr(msg, "Clip0", 0)) + int(getattr(msg, "Clip1", 0)) + int(getattr(msg, "Clip2", 0))))
        elif k == "GPS":
            rows[k].append((t, float(msg.Spd), int(msg.NSats), float(msg.HDop), float(msg.Alt)))
        elif k == "ATT":
            rows[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw),
                            float(getattr(msg, "DesRoll", 0)), float(getattr(msg, "DesPitch", 0)),
                            float(getattr(msg, "DesYaw", 0))))
        elif k == "RCOU":
            rows[k].append((t, float(msg.C1), float(msg.C2), float(msg.C3), float(msg.C4)))
        elif k == "BARO":
            rows[k].append((t, float(msg.Alt)))
    out = {}
    for k, v in rows.items():
        out[k] = np.array(v, dtype=float)
    np.savez(CACHE, **out)
    return out


def main() -> int:
    d = parse()
    FIG.mkdir(parents=True, exist_ok=True)
    mode, ctun, bat = d["MODE"], d["CTUN"], d["BAT"]
    vibe, gps, att, rcou, baro = d["VIBE"], d["GPS"], d["ATT"], d["RCOU"], d["BARO"]

    # 图 1：高度 + 电压 + 模式
    fig, ax1 = plt.subplots(figsize=(12, 4.5))
    ax1.plot(ctun[:, 0], ctun[:, 2], lw=1.0, color="#1f77b4", label="高度 (m)")
    ax1.plot(ctun[:, 0], ctun[:, 3], lw=0.8, color="#ff7f0e", alpha=0.6, label="目标高度 (m)")
    ax1.set_xlabel("时间 (s)")
    ax1.set_ylabel("高度 (m)")
    ax2 = ax1.twinx()
    ax2.plot(bat[:, 0], bat[:, 1], lw=1.2, color="#d62728", label="电压 (V)")
    ax2.set_ylabel("电压 (V)", color="#d62728")
    names = {0: "Stab", 2: "AltHold", 3: "Auto", 5: "Loiter", 6: "RTL", 9: "Land"}
    for t, m in mode:
        ax1.axvline(t, color="gray", ls=":", lw=0.6, alpha=0.5)
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)
    ax1.set_title("高度 / 目标高度 / 电压（灰线为模式切换）")
    fig.tight_layout()
    fig.savefig(FIG / "f1_alt_volt.png", dpi=130)
    plt.close(fig)

    # 图 2：速度 + 倾角 + 油门
    tilt = np.sqrt(att[:, 1] ** 2 + att[:, 2] ** 2)
    fig, ax = plt.subplots(3, 1, figsize=(12, 7), sharex=True)
    ax[0].plot(gps[:, 0], gps[:, 1], color="#2ca02c", lw=1.0)
    ax[0].set_ylabel("速度 (m/s)")
    ax[0].set_title("水平速度 / 倾角 / 油门")
    ax[1].plot(att[:, 0], tilt, color="#9467bd", lw=0.8)
    ax[1].set_ylabel("倾角 (°)")
    ax[2].plot(ctun[:, 0], ctun[:, 1], color="#8c564b", lw=0.8)
    ax[2].set_ylabel("油门 (0-1)")
    ax[2].set_xlabel("时间 (s)")
    fig.tight_layout()
    fig.savefig(FIG / "f2_speed_tilt_thr.png", dpi=130)
    plt.close(fig)

    # 图 3：振动
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.plot(vibe[:, 0], vibe[:, 1], lw=0.7, label="VibeX")
    ax.plot(vibe[:, 0], vibe[:, 2], lw=0.7, label="VibeY")
    ax.plot(vibe[:, 0], vibe[:, 3], lw=0.7, label="VibeZ")
    ax.axhline(30, color="orange", ls="--", lw=0.8, label="30 警告线")
    ax.set_ylabel("振动 (m/s²)")
    ax.set_xlabel("时间 (s)")
    ax.legend(fontsize=9)
    ax.set_title("三轴振动（削顶次数 %d）" % int(vibe[:, 4].sum()))
    fig.tight_layout()
    fig.savefig(FIG / "f3_vibe.png", dpi=130)
    plt.close(fig)

    # 图 4：气压-EKF 差 + 卫星数
    t_common = np.linspace(max(baro[0, 0], ctun[0, 0]), min(baro[-1, 0], ctun[-1, 0]), 600)
    baro_i = np.interp(t_common, baro[:, 0], baro[:, 1])
    ctun_i = np.interp(t_common, ctun[:, 0], ctun[:, 2])
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.plot(t_common, baro_i - ctun_i, color="#e377c2", lw=1.0, label="气压 − EKF 高度 (m)")
    ax.set_ylabel("差值 (m)")
    ax.set_xlabel("时间 (s)")
    ax2 = ax.twinx()
    ax2.plot(gps[:, 0], gps[:, 2], color="#7f7f7f", lw=0.6, alpha=0.6, label="卫星数")
    ax2.set_ylabel("卫星数")
    ax.set_title("气压与 EKF 高度差 / 卫星数")
    fig.tight_layout()
    fig.savefig(FIG / "f4_baro_ekf.png", dpi=130)
    plt.close(fig)

    # 分析
    out = []
    des_roll, des_pitch = att[:, 4], att[:, 5]
    fly = ctun[:, 2] > 3
    rms_r = float(np.sqrt(np.mean((att[fly, 1] - des_roll[fly]) ** 2)))
    rms_p = float(np.sqrt(np.mean((att[fly, 2] - des_pitch[fly]) ** 2)))
    out.append(f"姿态跟踪 RMSE：横滚 {rms_r:.2f}°，俯仰 {rms_p:.2f}°")

    hover = (ctun[:, 2] > 3) & (gps[:, 1][:len(ctun)] < 1.0 if len(gps) >= len(ctun) else np.zeros(len(ctun), bool))
    n = min(len(rcou), len(ctun))
    mask = (ctun[:n, 2] > 3) & (ctun[:n, 1] < 0.35)
    if mask.any():
        c = rcou[:n][mask][:, 1:5]
        spread = (c.max(axis=1) - c.min(axis=1))
        out.append(f"电机输出差异（低油门飞行段）：均值 {spread.mean():.0f} us，最大 {spread.max():.0f} us")

    nv = min(len(vibe), len(ctun))
    thr = ctun[:nv, 1]
    vx = vibe[:nv, 1]
    out.append(f"振动X 与油门相关系数：{np.corrcoef(thr, vx)[0,1]:.2f}")

    v_start, v_end = bat[0, 1], bat[-1, 1]
    out.append(f"电压 {v_start:.2f} → {v_end:.2f} V，{bat[-1,0]/60:.1f} 分钟，"
               f"平均 {abs(v_end-v_start)/(bat[-1,0]/60):.3f} V/min")

    Path(r"D:\ai\deekseep\agent\data\health_analysis.txt").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
