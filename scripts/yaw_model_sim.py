"""航向回摆的闭环仿真：对比不同参数下的过冲与稳定时间。

模型（简化但可比较）：
  航向 ψ' = ω
  角速度 ω' = (K·u − ω) / τ        K = 90 °/s（满输出），τ = 0.06 s
  角度环：ω_cmd = clamp(ANG_P·(ψ_target − ψ), ±RATE_MAX)
  角速度环：误差经 FLTE 一阶低通，u = P·e + I·∫e + D·de/dt
"""

from __future__ import annotations

import numpy as np

DT = 0.005
T_END = 6.0
K = 90.0
TAU = 0.06


def simulate(ang_p, p, i, d, flte, fltd, rate_max, hold=1.5, target=90.0):
    t = np.arange(0, T_END, DT)
    psi, omega, integ, e_f, de_f = 0.0, 0.0, 0.0, 0.0, 0.0
    psi_target = target
    hist = []
    for k, tk in enumerate(t):
        # 打杆阶段：目标航向持续前移（等效于保持最大偏航速度）
        if tk < hold:
            rate_cmd = rate_max
        else:
            rate_cmd = np.clip(ang_p * (psi_target - psi), -rate_max, rate_max)
        e = rate_cmd - omega
        e_f += (e - e_f) * min(1.0, 2 * np.pi * flte * DT)
        de = (e_f - de_f) / DT
        de_f = e_f
        d_term = d * de
        # D 项低通
        if fltd > 0:
            alpha = min(1.0, 2 * np.pi * fltd * DT)
            d_term = d * (de_f * alpha)
        integ += e_f * DT
        u = np.clip(p * e_f + i * integ + d_term, -1, 1)
        omega += (K * u - omega) / TAU * DT
        psi += omega * DT
        hist.append((tk, psi, omega, u))
    arr = np.array(hist)
    # 松杆后（hold 之后）的航向峰值与稳定
    after = arr[arr[:, 0] >= hold]
    if len(after) == 0:
        return {}
    psi_after = after[:, 1]
    overshoot = max(0.0, psi_after.max() - target)
    # 稳定时间：最后一次超出 ±2° 的时刻
    outside = np.where(np.abs(psi_after - target) > 2.0)[0]
    settle = after[outside[-1], 0] - hold if len(outside) else 0.0
    # 反向角速度峰值
    reverse_peak = abs(after[:, 2].min())
    return {
        "overshoot_deg": round(overshoot, 1),
        "overshoot_pct": round(overshoot / target * 100, 0),
        "settle_s": round(settle, 2),
        "reverse_rate": round(reverse_peak, 1),
    }


CASES = {
    "当前（D0.0015/FLTE2/ANG4.5/RATE45）": dict(ang_p=4.5, p=0.185, i=0.018, d=0.0015, flte=2, fltd=20, rate_max=45),
    "方案A（D0.004/FLTE5/ANG3.5，RATE不动）": dict(ang_p=3.5, p=0.185, i=0.018, d=0.004, flte=5, fltd=20, rate_max=45),
    "方案B（再加P0.15，RATE不动）": dict(ang_p=3.5, p=0.15, i=0.018, d=0.004, flte=5, fltd=20, rate_max=45),
    "方案C（D0.003/FLTE4/ANG4.0，RATE不动）": dict(ang_p=4.0, p=0.185, i=0.018, d=0.003, flte=4, fltd=20, rate_max=45),
    "对照：放开RATE到90（不改其他）": dict(ang_p=3.5, p=0.185, i=0.018, d=0.004, flte=5, fltd=20, rate_max=90),
}

for name, params in CASES.items():
    r = simulate(**params)
    print(f"{name:<38} 航向过冲 {r['overshoot_deg']:>5.1f}° ({r['overshoot_pct']:>3.0f}%)  "
          f"稳定 {r['settle_s']:>4.2f}s  反向角速度 {r['reverse_rate']:>4.1f}°/s")
