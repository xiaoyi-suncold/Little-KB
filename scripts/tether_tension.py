"""系留无人机系缆受力估算（均布载荷悬链线解 + 指数风廓线平均风压）

用途：装机前算"缆会给无人机多大拉力、要多大的水平保持力"。
模型：
- 缆绳按不可伸长、重量沿弧长均布处理，风载按指数风廓线在高度上的平均值折算成
  均布水平载荷 —— 等效载荷 q = sqrt(w^2 + h^2)，方向与竖直偏 atan(h/w)。
- 悬链线方程：L = 2a·sinh(d / 2a)，d 为弦长（这里取无人机垂直高度 H），
  二分法解 a，再算顶端张力 T_top = q·a·cosh(d / 2a)。
- 风载：v(z) = v1·(z/z1)^m  →  <v²> = v1²·(H/z1)^(2m) / (2m+1)
  h = 0.5·ρ·Cd·d_cable·<v²>

单位：N、m、s、kg。库内标准要求见 kb/无人机/知识库/系留无人机标准与一手资料.md
"""
from __future__ import annotations

import math
import sys

RHO_AIR = 1.225
G = 9.80665

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mean_v2(height: float, v_ref: float = 5.0, z_ref: float = 10.0, exponent: float = 0.14) -> float:
    """指数风廓线在 0..height 上的 <v²> 均值。"""
    if height <= 0:
        return 0.0
    return v_ref ** 2 * (height / z_ref) ** (2 * exponent) / (2 * exponent + 1)


def solve_catenary_a(length: float, chord: float, tol: float = 1e-9, it: int = 200) -> float:
    """解 L = 2a·sinh(d/2a) 的 a（二分）。要求 length > chord。"""
    if length <= chord:
        return float("nan")
    lo, hi = 1e-6, max(chord, 1.0)
    f = lambda a: 2 * a * math.sinh(chord / (2 * a)) - length
    # 找上界：a 越小 2a·sinh(d/2a) 越大
    while f(hi) > 0 and hi < 1e7:
        hi *= 2
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def tether_loads(
    height: float = 100.0,
    length: float = 105.0,
    mass_per_m: float = 0.015,
    diameter: float = 0.003,
    v_ref: float = 5.0,
    wind_exponent: float = 0.14,
    cd: float = 1.2,
) -> dict:
    """返回顶端张力（总/竖直/水平）、角度、垂度。"""
    w = mass_per_m * G
    v2 = mean_v2(height, v_ref, 10.0, wind_exponent)
    h = 0.5 * RHO_AIR * cd * diameter * v2
    q = math.hypot(w, h)
    a = solve_catenary_a(length, height)
    if not math.isfinite(a):
        return {"error": "length<=height"}
    T_top = q * a * math.cosh(height / (2 * a))
    tilt = math.atan2(h, w)  # 载荷方向偏离竖直的角度
    sag = a * math.cosh(0.0) - a  # 以中点为基准的相对垂度（近似）
    mid_drop = a * (math.cosh(height / (2 * a)) - 1.0)
    return {
        "T_top_N": T_top,
        "T_top_kg": T_top / G,
        "T_vertical_N": T_top * math.cos(tilt),
        "T_horizontal_N": T_top * math.sin(tilt),
        "load_angle_deg": math.degrees(tilt),
        "mean_vsms": math.sqrt(v2),
        "wind_load_N_per_m": h,
        "sag_m": mid_drop,
        "catenary_a": a,
    }


def tether_loss(
    power_kw: float, voltage_v: float, length_m: float, area_mm2: float, rho_cu: float = 0.0175
) -> dict:
    """双导体压降与线损（标准：运行功率 >1 kW 时线功率损耗 ≤5%）。"""
    r = 2.0 * rho_cu * length_m / area_mm2
    current = power_kw * 1000.0 / voltage_v
    drop = current * r
    loss_w = current ** 2 * r
    return {
        "resistance_ohm": r,
        "current_A": current,
        "drop_V": drop,
        "drop_pct": drop / voltage_v * 100.0,
        "loss_W": loss_w,
        "loss_pct_of_system": loss_w / (power_kw * 1000.0) * 100.0,
    }


if __name__ == "__main__":
    print("== 例1：100 m 高、105 m 缆、1.5 kg/100m、Ø3mm、风 5 m/s@10m ==")
    r = tether_loads()
    print(f"顶端张力 {r['T_top_N']:.1f} N（{r['T_top_kg']:.2f} kg）"
          f"｜竖直 {r['T_vertical_N']:.1f} N｜水平 {r['T_horizontal_N']:.1f} N"
          f"｜偏斜 {r['load_angle_deg']:.1f}°｜垂度 {r['sag_m']:.2f} m")

    print("\n== 例2：风速对顶端张力的影响（同缆同高）==")
    for v in (0, 3, 5, 8, 12):
        r = tether_loads(v_ref=v)
        print(f"风 {v:>2} m/s：总 {r['T_top_N']:6.1f} N，水平 {r['T_horizontal_N']:6.1f} N，"
              f"偏斜 {r['load_angle_deg']:4.1f}°，垂度 {r['sag_m']:4.1f} m")

    print("\n== 例3：高度对顶端张力的影响（风 5 m/s）==")
    for hh in (30, 50, 100, 200, 300):
        r = tether_loads(height=hh, length=hh * 1.05)
        print(f"{hh:>3} m：总 {r['T_top_N']:6.1f} N（{r['T_top_kg']:5.2f} kg），"
              f"水平 {r['T_horizontal_N']:5.1f} N，垂度 {r['sag_m']:4.1f} m")

    print("\n== 例4：线损校核（1.6 kW，100 m，标准要求 >1kW 时线损 ≤5%）==")
    for v, area in ((400, 0.75), (400, 1.5), (800, 0.75), (800, 1.5)):
        q = tether_loss(1.6, v, 100, area)
        flag = "OK" if q["loss_pct_of_system"] <= 5 else "超标"
        print(f"{v} V / {area} mm2：{q['current_A']:5.2f} A，压降 {q['drop_V']:6.1f} V "
              f"({q['drop_pct']:4.1f}%)，线损 {q['loss_W']:6.0f} W "
              f"({q['loss_pct_of_system']:4.1f}%) {flag}")
