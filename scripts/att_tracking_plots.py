"""绘制姿态期望值与实际值对比图，并统计跟踪误差。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

NPZ = Path(r"D:\ai\deekseep\agent\data\jldh\health_plot.npz")
OUT = Path(r"D:\ai\deekseep\agent\out\figs")


def downsample(t, y, n=4000):
    idx = np.linspace(0, len(t) - 1, min(n, len(t))).astype(int)
    return t[idx], y[idx]


def wrap(deg):
    return (deg + 180) % 360 - 180


def main() -> int:
    d = dict(np.load(NPZ, allow_pickle=True))
    att = d["ATT"]
    ctun = d["CTUN"]
    t = att[:, 0]
    roll, pitch = att[:, 1], att[:, 2]
    yaw = np.degrees(np.unwrap(np.radians(att[:, 3])))
    des_roll, des_pitch = att[:, 4], att[:, 5]
    des_yaw = np.degrees(np.unwrap(np.radians(att[:, 6])))

    flying = ctun[:, 2] > 3
    n = min(len(t), len(ctun))
    flying = flying[:n]
    e_roll = roll[:n] - des_roll[:n]
    e_pitch = pitch[:n] - des_pitch[:n]
    e_yaw = wrap(yaw[:n] - des_yaw[:n])

    stats = []
    for name, e, des in [("横滚", e_roll, des_roll[:n]), ("俯仰", e_pitch, des_pitch[:n]), ("航向", e_yaw, des_yaw[:n])]:
        m = flying
        stats.append(f"{name}: RMSE {np.sqrt(np.mean(e[m]**2)):.2f}°, 最大 {np.abs(e[m]).max():.1f}°, "
                     f"95% {np.percentile(np.abs(e[m]), 95):.2f}°")
    Path(r"D:\ai\deekseep\agent\data\att_stats.txt").write_text("\n".join(stats), encoding="utf-8")

    fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True)
    for ax, (actual, des, label) in zip(axes, [
        (roll, des_roll, "横滚角 (°)"),
        (pitch, des_pitch, "俯仰角 (°)"),
        (yaw, des_yaw, "航向角 (°)"),
    ]):
        tt, aa = downsample(t, actual)
        _, dd = downsample(t, des)
        ax.plot(tt, aa, lw=0.7, color="#1f77b4", label="实际")
        ax.plot(tt, dd, lw=0.7, color="#ff7f0e", alpha=0.85, label="期望")
        ax.set_ylabel(label)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.25)
    axes[0].set_title("姿态期望值 vs 实际值（全程 2620 s）")
    axes[-1].set_xlabel("时间 (s)")
    fig.tight_layout()
    fig.savefig(OUT / "f5_att_des_vs_act.png", dpi=130)
    plt.close(fig)

    # 局部放大：选 1700-1850 s（低空悬停/手动段），并画误差
    a, b = 1700, 1850
    m = (t >= a) & (t <= b)
    fig, axes = plt.subplots(2, 2, figsize=(13, 7))
    for ax, (actual, des, label) in zip(axes.flat[:3], [
        (roll, des_roll, "横滚角 (°)"),
        (pitch, des_pitch, "俯仰角 (°)"),
        (yaw, des_yaw, "航向角 (°)"),
    ]):
        ax.plot(t[m], actual[m], lw=1.0, color="#1f77b4", label="实际")
        ax.plot(t[m], des[m], lw=1.0, color="#ff7f0e", label="期望")
        ax.set_title(f"{label} {a}–{b}s", fontsize=10)
        ax.legend(fontsize=8)
        ax.grid(alpha=0.25)
    ax = axes.flat[3]
    ax.plot(t[m], e_roll[m], lw=0.9, label="横滚误差")
    ax.plot(t[m], e_pitch[m], lw=0.9, label="俯仰误差")
    ax.axhline(0, color="k", lw=0.5)
    ax.set_title("跟踪误差 (实际−期望)", fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.suptitle(f"局部放大：{a}–{b} s", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "f6_att_zoom.png", dpi=130)
    plt.close(fig)

    print("\n".join(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
