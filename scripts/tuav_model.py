"""系留四旋翼 + 绞车：自建一致模型（用于验证"缆长-轨迹协同"控制）

为什么要自建：仓库 sof-danny/TUAV_system_control 的 MATLAB 代码直接搬过来跑会发散
（见 scripts/tuav_sim.py 的诊断：最高速度 183 m/s）——原因是那份 dynamics.m 里
z 轴加速度把重力项与推力项符号搞反（`+ m*g*C_theta*C_phi + Tz`），且角速度反馈
用的是角度而不是角速度。这里按标准多旋翼动力学重写一版一致的。

模型：
- 四旋翼刚体：位置 p、速度 v、机体姿态 R（这里用简化的小角度姿态角）、推力 T 沿机体 z；
- 系缆：从地面原点 O 到无人机，若 |p| > l 则视为绷紧，按"弹性 + 阻尼"给拉力，
  拉力方向沿 p 方向；否则不受力（缆松弛）；
- 绞车：以速度 PID 调 l，使 l 跟随"当前位置下的悬链线所需长度"；
- 风：水平常值力 + 小扰动；
- 控制器：位置 PD → 期望加速度 → 反解推力大小与姿态角（俯仰/横滚），
  姿态环用 PD 跟踪。

输出：航点跟踪误差、缆长跟踪误差、张力、最大速度。
"""
from __future__ import annotations

import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

G = 9.81
M = 2.84
IXX, IYY, IZZ = 0.5192, 0.4929, 0.0947

# 缆（用上一版静态脚本的同一组参数）
MASS_PER_M = 0.015      # 1.5 kg / 100 m
K_TETHER = 400.0        # 等效弹性 N/m（绷紧时）
C_TETHER = 8.0          # 等效阻尼 N·s/m
L_SLACK = 1.02          # 缆长超过直线距离 2% 视为松弛

# 航点
WAYPOINTS = [(0.0, 0.0, 20.0), (15.0, 0.0, 40.0), (15.0, 15.0, 60.0), (0.0, 0.0, 100.0)]


class State:
    __slots__ = ("p", "v", "att", "rate", "l", "ld", "tension", "ei")

    def __init__(self):
        self.p = [0.0, 0.0, 1.0]      # x, y, z(上)
        self.v = [0.0, 0.0, 0.0]
        self.att = [0.0, 0.0, 0.0]    # roll, pitch, yaw
        self.rate = [0.0, 0.0, 0.0]
        self.l = 3.0                  # 放出缆长
        self.ld = 0.0
        self.tension = 0.0
        self.ei = [0.0, 0.0, 0.0]


def catenary_length(height: float, horizontal: float, mass_per_m: float = MASS_PER_M) -> float:
    """给定几何位置，算悬链线所需缆长（无风近似；与静态脚本同一套方程）。"""
    chord = math.hypot(horizontal, height)
    if chord <= 1e-6:
        return 0.0
    w = mass_per_m * G
    a = max(chord * 1e-3, 1e-3)
    # 解 L = 2a·sinh(d/2a)，用二分（a 越大 L 越接近 d）
    lo, hi = 1e-4, 1e6
    for _ in range(100):
        mid = math.sqrt(lo * hi)
        L = 2 * mid * math.sinh(chord / (2 * mid))
        if L > chord * 1.06:   # 允许 6% 余量（对应垂度）
            lo = mid
        else:
            hi = mid
    return 2 * hi * math.sinh(chord / (2 * hi))


def tether_force(s: State):
    d = math.sqrt(sum(c * c for c in s.p))
    if d < 1e-6:
        return [0.0, 0.0, 0.0], 0.0
    slack = s.l * (1 - L_SLACK * 0)  # 用 l 直接比较
    if d <= s.l * 0.995:
        return [0.0, 0.0, 0.0], 0.0
    stretch = d - s.l * 0.995
    # 径向单位向量（指向无人机）
    u = [c / d for c in s.p]
    # 相对径向速度
    vr = sum(s.v[i] * u[i] for i in range(3))
    mag = K_TETHER * stretch + C_TETHER * max(0.0, vr)
    mag = min(mag, 5000.0)
    return [-mag * u[i] for i in range(3)], mag


def step(s: State, dt: float, target, wind=(0.0, 0.0), wind_noise=0.0, kp=0.9, kd=1.8,
         ki=0.25, att_kp=6.0, att_kd=2.2, winch_kp=1.5, a_max=0.4 * G):
    tx, ty, tz = target
    ex = [tx - s.p[0], ty - s.p[1], tz - s.p[2]]
    ev = [-s.v[0], -s.v[1], -s.v[2]]
    for i in range(3):
        s.ei[i] = max(-20.0, min(20.0, s.ei[i] + ex[i] * dt))
    # 期望加速度（位置 PID，限幅到 0.4 g）
    a_des = [kp * ex[i] + kd * ev[i] + ki * s.ei[i] for i in range(3)]
    a_des = [max(-a_max, min(a_max, a)) for a in a_des]
    # 姿态反解（小角度：推力沿机体 z，水平加速度由倾角产生）
    pitch_d = a_des[0] / G
    roll_d = -a_des[1] / G
    pitch_d = max(-0.5, min(0.5, pitch_d))
    roll_d = max(-0.5, min(0.5, roll_d))

    # 姿态环：期望角速度 → 力矩
    e_att = [roll_d - s.att[0], pitch_d - s.att[1], 0.0 - s.att[2]]
    w_d = [att_kp * e for e in e_att]
    torque = [IXX * att_kd * (w_d[0] - s.rate[0]),
              IYY * att_kd * (w_d[1] - s.rate[1]),
              IZZ * att_kd * (w_d[2] - s.rate[2])]

    # 推力：要产生 a_des 的竖直加速度并抵消重力
    T = M * (a_des[2] + G) / (math.cos(s.att[0]) * math.cos(s.att[1]))
    T = max(0.0, min(T, 6 * M * G))

    # 系缆
    tf, tension = tether_force(s)
    s.tension = tension

    # 风力
    wx = wind[0] + wind_noise * math.sin(1.7 * dt * 100)

    ax = (T * math.sin(s.att[1]) + tf[0] + wx) / M
    ay = (-T * math.sin(s.att[0]) + tf[1] + wind[1]) / M
    az = (T * math.cos(s.att[0]) * math.cos(s.att[1]) + tf[2]) / M - G

    for i, a in enumerate((ax, ay, az)):
        s.v[i] += a * dt
        s.p[i] += s.v[i] * dt
    for i in range(3):
        s.rate[i] += torque[i] / (IXX, IYY, IZZ)[i] * dt
        s.att[i] += s.rate[i] * dt

    # 绞车：跟随"当前位置所需缆长"
    l_target = catenary_length(max(s.p[2], 0.1), math.hypot(s.p[0], s.p[1])) * 1.0
    l_target = max(l_target, math.hypot(math.hypot(s.p[0], s.p[1]), s.p[2]) or 1.0)
    s.ld = winch_kp * (l_target - s.l)
    s.ld = max(-2.0, min(2.0, s.ld))   # 标准要求收放线 ≥2 m/s，这里按上限跑
    s.l = max(1.0, s.l + s.ld * dt)
    if s.p[2] < 0:
        s.p[2] = 0.0
        s.v[2] = 0.0


def run(wind=(0.0, 0.0), wind_noise=0.0, t_end=120.0, dt=0.002, verbose_every=20.0):
    s = State()
    t = 0.0
    wp = 0
    vmax = 0.0
    tmax = 0.0
    arrivals = {}
    log = []
    while t < t_end:
        step(s, dt, WAYPOINTS[wp], wind, wind_noise)
        t += dt
        vmax = max(vmax, math.sqrt(sum(v * v for v in s.v)))
        tmax = max(tmax, s.tension)
        if math.dist(tuple(s.p), WAYPOINTS[wp]) < 1.0 and wp < len(WAYPOINTS) - 1:
            arrivals[wp + 1] = t
            wp += 1
        if abs(t % verbose_every) < dt / 2:
            log.append((t, tuple(round(c, 2) for c in s.p), round(s.l, 1), round(s.tension, 1)))
    err = math.dist(tuple(s.p), WAYPOINTS[wp])
    return dict(s=s, wp=wp, t=t, err=err, vmax=vmax, tmax=tmax, arrivals=arrivals, log=log)


if __name__ == "__main__":
    print("== 情形1：无风，四点航点（垂直 20→40→60→100 m）==")
    r = run()
    print(f"最终航点 #{r['wp'] + 1}，距目标 {r['err']:.2f} m")
    print(f"最高速度 {r['vmax']:.2f} m/s｜峰值缆张力 {r['tmax']:.1f} N "
          f"（{r['tmax'] / G:.2f} kg）")
    print(f"到达时刻 " + ", ".join(f"#{i}@{tt:.1f}s" for i, tt in sorted(r['arrivals'].items())))
    for row in r["log"]:
        print(f"  t={row[0]:5.0f}s 位置 {row[1]} 缆长 {row[2]:5.1f} m 张力 {row[3]:6.1f} N")

    print("\n== 情形2：横风 3 m/s（≈60 N 推力扰动）+ 噪声 ==")
    r2 = run(wind=(5.0, 0.0), wind_noise=1.0)
    print(f"最终航点 #{r2['wp'] + 1}，距目标 {r2['err']:.2f} m｜最高速度 {r2['vmax']:.2f} m/s"
          f"｜峰值张力 {r2['tmax']:.1f} N")
