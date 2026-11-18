"""自动航线转弯分析：最低速度、减速深度、转弯时间、倾斜角。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

CACHE = Path(r"D:\ai\deekseep\agent\data\jldh")
TYPES = ["MODE", "GPS", "ATT", "CTUN"]

LOGS = [
    ("自动巡航版2", Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\2026-11-02 10-23-22.bin")),
    ("自动巡航版", Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\2026-11-02 10-59-42.bin")),
]


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
        elif k == "GPS":
            data[k].append((t, float(msg.Spd)))
        elif k == "ATT":
            data[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw)))
        elif k == "CTUN":
            data[k].append((t, float(msg.Alt)))
    out = {k: np.array(v, dtype=float) for k, v in data.items() if v}
    np.savez(npz, **out)
    return out


def analyse(label: str, d: dict) -> None:
    mode, gps, att = d["MODE"], d["GPS"], d["ATT"]
    t = att[:, 0]
    yaw = np.degrees(np.unwrap(np.radians(att[:, 3])))
    rate = np.gradient(yaw, t)
    tilt = np.sqrt(att[:, 1] ** 2 + att[:, 2] ** 2)

    g_t, g_v = gps[:, 0], gps[:, 1]

    def speed_at(ts):
        if len(g_t) == 0:
            return np.nan
        idx = np.searchsorted(g_t, ts)
        idx = min(max(idx, 0), len(g_t) - 1)
        return g_v[idx]

    # 只分析 Auto 段内的转弯
    auto = mode[mode[:, 1] == 3]
    print(f"\n=== {label}：时长 {t[-1]:.0f}s，Auto 段 {len(auto)} 个，"
          f"最大速度 {g_v.max():.2f} m/s ===")

    idx = np.where(np.abs(rate) > 15)[0]
    events, cur = [], []
    for i in idx:
        if cur and t[i] - t[cur[-1]] > 1.2:
            events.append(cur)
            cur = []
        cur.append(i)
    if cur:
        events.append(cur)

    rows = []
    for ev in events:
        a, b = t[ev[0]], t[ev[-1]]
        if b - a < 0.5:
            continue
        mask = (t >= a - 1) & (t <= b + 1)
        peak_rate = np.abs(rate[mask]).max()
        max_tilt = tilt[mask].max()
        v_before = speed_at(a - 2.0)
        v_min = min(speed_at(x) for x in np.linspace(a, b, 8))
        v_after = speed_at(b + 3.0)
        rows.append((a, b - a, peak_rate, max_tilt, v_before, v_min, v_after))

    print(f"{'开始':>7} {'持续':>5} {'峰值°/s':>8} {'倾角':>5} {'入弯速':>6} {'最低速':>6} {'出弯速':>6}")
    for r in rows[:20]:
        print(f"{r[0]:>7.1f} {r[1]:>5.2f} {r[2]:>8.1f} {r[3]:>5.1f} "
              f"{r[4]:>6.2f} {r[5]:>6.2f} {r[6]:>6.2f}")

    if rows:
        mins = np.array([r[5] for r in rows])
        befores = np.array([r[4] for r in rows])
        print(f"\n转弯 {len(rows)} 次：入弯平均 {befores.mean():.2f} m/s，"
              f"最低速平均 {mins.mean():.2f} m/s（最低 {mins.min():.2f}），"
              f"平均速度损失 {befores.mean()-mins.mean():.2f} m/s")


def main() -> int:
    for label, path in LOGS:
        if not path.exists():
            print(f"缺失 {path}")
            continue
        analyse(label, parse(path, f"turn_{path.stem[-8:].replace(' ','_')}"))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
