"""定点模式（Loiter）专项分析：悬停掉高、刹车距离、振动与电压。

用法：
  python scripts/loiter_analysis.py <log.bin>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

TYPES = ["MODE", "CTUN", "GPS", "VIBE", "RCOU", "BAT", "XKF1", "BARO"]


def collect(path: Path) -> dict:
    m = mavutil.mavlink_connection(str(path), robust_parsing=True)
    data = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        typ = msg.get_type()
        if typ == "MODE":
            data[typ].append((t, int(msg.Mode)))
        elif typ == "CTUN":
            data[typ].append((t, float(msg.ThO), float(msg.Alt), float(getattr(msg, "DAlt", 0))))
        elif typ == "GPS":
            data[typ].append((t, float(getattr(msg, "Spd", 0)), int(getattr(msg, "Status", 0))))
        elif typ == "VIBE":
            data[typ].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ)))
        elif typ == "RCOU":
            data[typ].append((t, float(msg.C1), float(msg.C2), float(msg.C3), float(msg.C4)))
        elif typ == "BAT":
            data[typ].append((t, float(getattr(msg, "Volt", 0)), float(getattr(msg, "Curr", 0))))
        elif typ == "XKF1":
            data[typ].append((t, float(getattr(msg, "PD", 0))))
        elif typ == "BARO":
            data[typ].append((t, float(getattr(msg, "Alt", 0))))
    return {k: np.array(v, dtype=float) for k, v in data.items() if v}


def segments(mode: np.ndarray, target: int = 5, gap: float = 2.0, min_len: float = 8.0):
    out = []
    start = None
    last_t = None
    for t, m in mode:
        if m == target:
            if start is None:
                start = t
            last_t = t
        else:
            if start is not None and last_t - start >= min_len:
                out.append((start, last_t))
            start = None
    if start is not None and last_t - start >= min_len:
        out.append((start, last_t))
    return out


def window(arr, a, b):
    if len(arr) == 0:
        return arr
    mask = (arr[:, 0] >= a) & (arr[:, 0] <= b)
    return arr[mask]


def main() -> int:
    path = Path(sys.argv[1])
    d = collect(path)
    print(f"文件 {path.name}")

    ctun, gps, vibe, rcou, bat, xkf1, baro = (d.get(k, np.empty((0, 2))) for k in
                                              ("CTUN", "GPS", "VIBE", "RCOU", "BAT", "XKF1", "BARO"))
    mode = d.get("MODE", np.empty((0, 2)))

    segs = segments(mode)
    print(f"Loiter 段数：{len(segs)}")

    rows = []
    for a, b in segs:
        c = window(ctun, a, b)
        g = window(gps, a, b)
        v = window(vibe, a, b)
        r = window(rcou, a, b)
        if len(c) < 5:
            continue
        alt = c[:, 2]
        tho = c[:, 1]
        spd = g[:, 1] if len(g) else np.array([0.0])
        rows.append({
            "start": a, "dur": b - a,
            "alt_start": alt[0], "alt_end": alt[-1], "alt_min": alt.min(), "alt_max": alt.max(),
            "drift": alt[-1] - alt[0],
            "tho_mean": tho.mean(), "tho_std": tho.std(),
            "spd_mean": spd.mean(), "spd_max": spd.max(),
            "vibe_max": float(v[:, 1:].max()) if len(v) else None,
            "rcou_mean": r[:, 1:].mean(axis=0) if len(r) else None,
        })

    rows.sort(key=lambda x: x["start"])
    print("\n=== Loiter 段（按时间）===")
    print(f"{'起始':>8} {'时长':>6} {'起点高':>7} {'终点高':>7} {'漂移':>7} {'高度范围':>12} {'ThO均':>6} {'速度均':>6} {'VIBE':>5}")
    for r_ in rows:
        print(f"{r_['start']:>8.1f} {r_['dur']:>6.1f} {r_['alt_start']:>7.2f} {r_['alt_end']:>7.2f} "
              f"{r_['drift']:>+7.2f} {r_['alt_min']:>5.2f}~{r_['alt_max']:<5.2f} "
              f"{r_['tho_mean']:>6.3f} {r_['spd_mean']:>6.2f} "
              f"{(r_['vibe_max'] if r_['vibe_max'] is not None else 0):>5.1f}")

    # 刹车事件：速度从 >2.5 m/s 降到 <0.5 m/s
    print("\n=== 刹车事件（速度 >2.5 → <0.5）===")
    if len(gps) > 10:
        t = gps[:, 0]
        s = gps[:, 1]
        events = []
        i = 0
        while i < len(t):
            if s[i] > 2.5:
                j = i
                while j < len(t) and s[j] > 0.5:
                    j += 1
                if j < len(t) and j - i > 3:
                    dt = t[j] - t[i]
                    dist = float(np.trapz(s[i:j + 1], t[i:j + 1]))
                    events.append({
                        "t": t[i], "v0": float(s[i]), "v_min": float(s[j]),
                        "dur": float(dt), "dist": dist,
                        "decel": float((s[i] - s[j]) / max(dt, 0.1)),
                    })
                    i = j
            i += 1
        for e in events[:12]:
            print(f"  t={e['t']:>7.1f}s  {e['v0']:>4.1f}→{e['v_min']:.1f} m/s  "
                  f"用时 {e['dur']:>4.1f}s  距离 {e['dist']:>5.1f} m  平均减速度 {e['decel']:>4.2f} m/s²")

    # 悬停时的 EKF 高度 vs 气压
    print("\n=== 高度源对比（Loiter 段均值）===")
    for a, b in segs:
        c = window(ctun, a, b)
        p = window(baro, a, b)
        k = window(xkf1, a, b)
        if len(c) < 5:
            continue
        print(f"  {a:>7.1f}s  CTUN.Alt={c[:,2].mean():.2f}  BARO={p[:,1].mean() if len(p) else float('nan'):.2f}  "
              f"XKF1.PD={k[:,1].mean() if len(k) else float('nan'):.2f}")

    print("\n=== 电压 ===")
    if len(bat):
        print(f"  {bat[:,1].min():.1f} ~ {bat[:,1].max():.1f} V, 平均 {bat[:,1].mean():.1f} V")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
