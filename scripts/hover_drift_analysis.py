"""解析指定 .bin，缓存关键通道到 npz 并输出悬停高度漂移分析。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

BIN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\2026-10-30 14-42-09.bin")
NPZ = Path(r"D:\ai\deekseep\agent\data\jldh\flight_1442.npz")

TYPES = ["MODE", "CTUN", "GPS", "BARO", "BAT", "VIBE", "RCOU", "XKF1"]


def parse() -> dict:
    m = mavutil.mavlink_connection(str(BIN), robust_parsing=True)
    data: dict[str, list] = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        k = msg.get_type()
        if k == "MODE":
            data[k].append((t, int(msg.Mode)))
        elif k == "CTUN":
            data[k].append((t, float(msg.ThO), float(msg.Alt)))
        elif k == "GPS":
            data[k].append((t, float(msg.Spd), int(msg.Status), float(msg.HDop)))
        elif k == "BARO":
            data[k].append((t, float(msg.Alt)))
        elif k == "BAT":
            data[k].append((t, float(msg.Volt), float(msg.Curr)))
        elif k == "VIBE":
            data[k].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ)))
        elif k == "RCOU":
            data[k].append((t, float(msg.C1), float(msg.C2), float(msg.C3), float(msg.C4)))
        elif k == "XKF1":
            data[k].append((t, float(msg.PD), float(msg.VD)))
    return {k: np.array(v, dtype=float) for k, v in data.items() if v}


def main() -> int:
    if NPZ.exists():
        d = dict(np.load(NPZ))
    else:
        d = parse()
        NPZ.parent.mkdir(parents=True, exist_ok=True)
        np.savez(NPZ, **d)
        print(f"cached {NPZ.name}")

    mode = d["MODE"]
    ctun = d["CTUN"]
    gps = d["GPS"]
    baro = d.get("BARO", np.empty((0, 2)))
    bat = d.get("BAT", np.empty((0, 3)))
    vibe = d.get("VIBE", np.empty((0, 4)))

    t_end = ctun[-1, 0]
    print(f"日志时长 {t_end:.0f}s，CTUN {len(ctun)} 条，BARO {len(baro)} 条")

    def loiter_mask(ts):
        idx = np.searchsorted(mode[:, 0], ts, side="right") - 1
        idx = np.clip(idx, 0, len(mode) - 1)
        return mode[idx, 1] == 5

    # 悬停窗口：Loiter + 速度<0.5 + 高度>1
    t = gps[:, 0]
    v = gps[:, 1]
    mask = (v < 0.5) & loiter_mask(t)
    windows, start = [], None
    for i in range(len(t)):
        if mask[i] and start is None:
            start = t[i]
        if (not mask[i]) and start is not None:
            if t[i] - start >= 20:
                windows.append((start, t[i]))
            start = None
    print(f"悬停窗口 {len(windows)} 个\n")
    print(f"{'起点':>7} {'时长':>6} {'高度起':>7} {'高度止':>7} {'斜率m/min':>9} {'ThO均':>6} {'电压均':>6} {'气压-EKF':>9} {'VIBE':>5}")

    for a, b in windows:
        c = ctun[(ctun[:, 0] >= a) & (ctun[:, 0] <= b)]
        if len(c) < 30:
            continue
        alt, tho = c[:, 2], c[:, 1]
        slope = np.polyfit(c[:, 0] - a, alt, 1)[0] * 60
        bmask = (baro[:, 0] >= a) & (baro[:, 0] <= b)
        bdiff = (baro[bmask, 1].mean() - alt.mean()) if bmask.any() else float("nan")
        bmask2 = (bat[:, 0] >= a) & (bat[:, 0] <= b)
        volt = bat[bmask2, 1].mean() if bmask2.any() else float("nan")
        vmask = (vibe[:, 0] >= a) & (vibe[:, 0] <= b)
        vmax = vibe[vmask, 1:].max() if vmask.any() else float("nan")
        print(f"{a:>7.1f} {b-a:>6.1f} {alt[0]:>7.2f} {alt[-1]:>7.2f} {slope:>+9.2f} "
              f"{tho.mean():>6.3f} {volt:>6.1f} {bdiff:>+9.2f} {vmax:>5.1f}")

    print("\n=== 全飞行高度/电压/油门趋势（每 120 s 采样）===")
    for t0 in np.arange(0, t_end, 120):
        c = ctun[(ctun[:, 0] >= t0) & (ctun[:, 0] < t0 + 120)]
        if len(c) < 10:
            continue
        bmask = (bat[:, 0] >= t0) & (bat[:, 0] < t0 + 120)
        volt = bat[bmask, 1].mean() if bmask.any() else float("nan")
        print(f"  t={t0:>6.0f}s  Alt {c[:,2].min():>5.2f}~{c[:,2].max():<5.2f}  "
              f"ThO {c[:,1].mean():.3f}  Volt {volt:.1f}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
