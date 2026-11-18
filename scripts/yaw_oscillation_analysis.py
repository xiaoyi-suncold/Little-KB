"""偏航回摆分析：打杆-回中后的过冲、反向峰值与衰减。"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

BIN = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\2026-11-02 11-47-18.bin")
CACHE = Path(r"D:\ai\deekseep\agent\data\jldh\yaw_1147.npz")
TYPES = ["ATT", "MODE", "CTUN"]


def parse() -> dict:
    if CACHE.exists():
        return dict(np.load(CACHE))
    m = mavutil.mavlink_connection(str(BIN), robust_parsing=True)
    data = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        k = msg.get_type()
        if k == "ATT":
            data[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw)))
        elif k == "MODE":
            data[k].append((t, int(msg.Mode)))
        elif k == "CTUN":
            data[k].append((t, float(msg.Alt), float(msg.ThO)))
    out = {k: np.array(v, dtype=float) for k, v in data.items() if v}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, **out)
    return out


def main() -> int:
    d = parse()
    att, mode = d["ATT"], d.get("MODE")
    t = att[:, 0]
    yaw = np.degrees(np.unwrap(np.radians(att[:, 3])))
    rate = np.gradient(yaw, t)

    # 平滑 5 点，去掉微分噪声
    kernel = np.ones(5) / 5
    rate_s = np.convolve(rate, kernel, mode="same")

    print(f"日志 {t[-1]:.0f}s，最大偏航角速度 {np.abs(rate_s).max():.1f} °/s")
    if mode is not None:
        vals, counts = np.unique(mode[:, 1], return_counts=True)
        print("模式计数:", {int(v): int(c) for v, c in zip(vals, counts)})

    # 事件：|rate|>20°/s 的连续段
    idx = np.where(np.abs(rate_s) > 20)[0]
    events, cur = [], []
    for i in idx:
        if cur and t[i] - t[cur[-1]] > 0.8:
            events.append(cur)
            cur = []
        cur.append(i)
    if cur:
        events.append(cur)

    print(f"\n检测到 {len(events)} 次打杆事件")
    print(f"{'开始':>7} {'峰值':>7} {'反向峰':>7} {'过冲%':>6} {'过零':>4} {'稳定(s)':>7} {'最高速':>7}")
    for ev in events[:20]:
        a, b = t[ev[0]], t[ev[-1]]
        peak = rate_s[ev[np.argmax(np.abs(rate_s[ev]))]]
        # 峰值之后 4 秒内找反向峰和过零
        m2 = (t > b) & (t <= b + 4)
        if not m2.any():
            continue
        tail = rate_s[m2]
        sign = np.sign(peak)
        reverse = np.min(tail * sign)  # 反方向幅度（负值）
        crossings = int(np.sum(np.diff(np.sign(tail)) != 0))
        # 稳定时间：|rate| 连续小于 5°/s 的起点
        small = np.abs(tail) < 5
        settle = np.nan
        for k in range(len(small) - 5):
            if small[k:k + 5].all():
                settle = t[m2][k] - b
                break
        overshoot = abs(reverse / peak) * 100 if peak else np.nan
        print(f"{a:>7.1f} {peak:>7.1f} {reverse:>7.1f} {overshoot:>6.0f} {crossings:>4} "
              f"{settle if settle == settle else float('nan'):>7.2f} {np.abs(rate_s[m2]).max():>7.1f}")

    # 饱和检查：角速度是否长时间贴在某个值
    big = np.abs(rate_s[np.abs(rate_s) > 35]
                 )
    if len(big):
        print(f"\n|rate|>35°/s 的样本 {len(big)} 个，最大 {big.max():.1f}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
