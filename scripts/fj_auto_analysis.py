"""分析：定点悬停高度漂移 + 自动航线转弯速率。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

BIN1 = Path(r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\2026-10-30 15-54-01.bin")
BIN2 = Path(r"D:\wx_test\WXWork\1688856445788758\Cache\File\2026-10\2026-10-30 16-54-43.bin")
CACHE = Path(r"D:\ai\deekseep\agent\data\jldh")

TYPES = ["MODE", "CTUN", "GPS", "BARO", "BAT", "ATT", "VIBE", "XKF1"]


def parse(path: Path, key: str) -> dict:
    npz = CACHE / f"{key}.npz"
    if npz.exists():
        return dict(np.load(npz))
    m = mavutil.mavlink_connection(str(path), robust_parsing=True)
    data = {k: [] for k in TYPES}
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
            data[k].append((t, float(msg.Spd), float(msg.GCrs) if hasattr(msg, "GCrs") else 0.0))
        elif k == "BARO":
            data[k].append((t, float(msg.Alt)))
        elif k == "BAT":
            data[k].append((t, float(msg.Volt)))
        elif k == "ATT":
            data[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw)))
        elif k == "VIBE":
            data[k].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ)))
        elif k == "XKF1":
            data[k].append((t, float(getattr(msg, "PD", 0))))
    out = {k: np.array(v, dtype=float) for k, v in data.items() if v}
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(npz, **out)
    return out


def hover_report(d: dict) -> None:
    mode, ctun, gps, baro, bat = d["MODE"], d["CTUN"], d["GPS"], d["BARO"], d["BAT"]
    print(f"\n=== 悬停日志：时长 {ctun[-1,0]:.0f}s，高度 {ctun[:,2].min():.1f}~{ctun[:,2].max():.1f}，"
          f"电压 {bat[:,1].min():.1f}~{bat[:,1].max():.1f} ===")
    idx = np.searchsorted(mode[:, 0], gps[:, 0], side="right") - 1
    loiter = mode[np.clip(idx, 0, len(mode) - 1), 1] == 5
    stable = (gps[:, 1] < 0.5) & loiter
    t = gps[:, 0]
    windows, start = [], None
    for i in range(len(t)):
        if stable[i] and start is None:
            start = t[i]
        if not stable[i] and start is not None:
            if t[i] - start >= 30:
                windows.append((start, t[i]))
            start = None
    print(f"{'起点':>7} {'时长':>6} {'高度起':>7} {'高度止':>7} {'m/min':>7} {'ThO':>6} {'气压-EKF':>9}")
    for a, b in windows:
        c = ctun[(ctun[:, 0] >= a) & (ctun[:, 0] <= b)]
        if len(c) < 30:
            continue
        slope = np.polyfit(c[:, 0] - a, c[:, 2], 1)[0] * 60
        bm = (baro[:, 0] >= a) & (baro[:, 0] <= b)
        diff = baro[bm, 1].mean() - c[:, 2].mean() if bm.any() else float("nan")
        print(f"{a:>7.0f} {b-a:>6.0f} {c[0,2]:>7.2f} {c[-1,2]:>7.2f} {slope:>+7.2f} {c[:,1].mean():>6.3f} {diff:>+9.2f}")


def turn_report(d: dict) -> None:
    mode, att, gps, ctun = d["MODE"], d["ATT"], d["GPS"], d["CTUN"]
    print(f"\n=== 航线日志：时长 {ctun[-1,0]:.0f}s，高度 {ctun[:,2].min():.1f}~{ctun[:,2].max():.1f} ===")
    auto = mode[mode[:, 1] == 3]
    print(f"Auto 模式段 {len(auto)} 个；模式计数：",
          {int(k): int(v) for k, v in zip(*np.unique(mode[:, 1], return_counts=True))})

    t = att[:, 0]
    yaw = np.degrees(np.unwrap(np.radians(att[:, 3])))
    rate = np.gradient(yaw, t)
    tilt = np.sqrt(att[:, 1] ** 2 + att[:, 2] ** 2)

    # 转弯事件：航向速率 >15°/s
    idx = np.where(np.abs(rate) > 15)[0]
    events, cur = [], []
    for i in idx:
        if cur and t[i] - t[cur[-1]] > 1.0:
            events.append(cur)
            cur = []
        cur.append(i)
    if cur:
        events.append(cur)
    print(f"\n检测到 {len(events)} 次转弯（|yaw rate|>15°/s）")
    print(f"{'开始':>7} {'持续':>6} {'峰值°/s':>8} {'最大倾角':>8} {'速度':>6}")
    for ev in events[:15]:
        a, b = t[ev[0]], t[ev[-1]]
        mask = (t >= a - 0.5) & (t <= b + 0.5)
        if mask.sum() < 3:
            continue
        peak = np.abs(rate[mask]).max()
        max_tilt = tilt[mask].max()
        gm = (gps[:, 0] >= a - 1) & (gps[:, 0] <= b + 1)
        spd = gps[gm, 1].max() if gm.any() else float("nan")
        print(f"{a:>7.1f} {b-a:>6.2f} {peak:>8.1f} {max_tilt:>8.1f} {spd:>6.2f}")


def main() -> int:
    d1 = parse(BIN1, "fj_auto_hover")
    d2 = parse(BIN2, "fj_auto_mission")
    hover_report(d1)
    turn_report(d2)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
