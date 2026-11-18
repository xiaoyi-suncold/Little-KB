"""系留四旋翼 + 绞车 简化仿真（Python 复刻 + 修正）

来源：GitHub sof-danny/TUAV_system_control（arXiv:2412.09502 配套 MATLAB 代码）
把 main.m / dynamics.m / cableDynamics.m 的模型搬成 Python，便于本地验证与对照。

状态（14 + 2n）：
 0 x, 1 vx, 2 y, 3 vy, 4 z, 5 vz,
 6 roll, 7 p, 8 pitch, 9 q, 10 yaw, 11 r,
 12 缆长 l, 13 缆长变化率,
 14.. 缆绳集中质量的位移/速度（弹簧-阻尼，用于表现"抖动"）

用法：
    python scripts/tuav_sim.py            # 跑原文参数 + 修正参数，打印对比
"""
from __future__ import annotations

import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

G = 9.81

# ---- 平台参数（照搬 main.m）----
M = 2.84          # kg
IXX = 0.5192
IYY = 0.4929
IZZ = 0.0947
L_ARM = 0.405

IW = 0.01         # 绞车转动惯量
R_W = 0.1         # 卷筒半径

RHO = 0.034       # 缆密度 kg/m^2（原文口径）
S_CABLE = 1.1e-4  # 缆截面积 m^2
T0 = 5.0          # 初始张力 N
A_CAT = T0 / (RHO * G)
X0 = 0.0
ALPHA = math.atan(math.sinh(X0 / A_CAT))

K = dict(k1=25, k2=25, k3=25, k4=15, k5=45, k6=55, k7=85, k8=85,
         k9=85, k10=95, k11=105, k12=95, k13=100, k14=100)

N_DIST = dict(Nx=0.01, Ny=0.01, Nz=0.01, N_phi=0.0, N_theta=0.0, N_psi=0.0)

THRESH = 1e-10
MAX_TETHER = 30.0

# 缆绳（视觉/抖动层）
N_MASS = 10
K_SPRING = 100.0
D_DAMP = 0.01
M_MASS = 2.0

WAYPOINTS = [(1.0, 2.0, 4.0), (4.0, 5.0, 8.0), (6.0, 10.0, 15.0), (2.0, 10.0, 10.0)]


def _clip(x, lim):
    return max(-lim, min(lim, x))


def _sat(angle, limit=0.9):
    """角度限幅，避免 cos 过零导致控制量爆炸。"""
    return _clip(angle, limit)


def deriv(x, wp_idx, fix_law: bool, pitch_ref: float):
    x1, x2, x3, x4, x5, x6, x7, x8, x9, x10, x11, x12, x13, x14 = x[:14]
    k = K

    x1_ref, x3_ref, x5_ref = WAYPOINTS[wp_idx]
    x7_ref, x9_ref, x11_ref = 0.0, pitch_ref, 0.0

    beta = math.atan(math.sinh(_clip((x1 - X0) / A_CAT, 50.0)))
    Th = T0 + RHO * S_CABLE * x5 * G
    Tx = Th * math.cos(ALPHA) * math.sin(beta)
    Ty = -Th * math.cos(ALPHA) * math.cos(beta)
    Tz = -Th * math.sin(ALPHA)

    x13_ref = math.sqrt(abs(2 * A_CAT * math.sinh(x1 / (2 * A_CAT))) + x5 ** 2)

    e1, e2 = x1 - x1_ref, x2
    e3, e4 = x3 - x3_ref, x4
    e5, e6 = x5 - x5_ref, x6
    e7, e8 = x7 - x7_ref, x8
    e9, e10 = x9 - x9_ref, x10
    e11, e12 = x11 - x11_ref, x12
    e13, e14 = x13 - x13_ref, x14

    z1 = e2 + k["k1"] * e1
    z2 = e4 + k["k3"] * e3
    z3 = e6 + k["k5"] * e5
    z4 = e8 + k["k7"] * e7
    z5 = e10 + k["k9"] * e9
    z6 = e12 + k["k11"] * e11
    z7 = e14 + k["k13"] * e13

    S_theta, C_theta = math.sin(_sat(x9)), math.cos(_sat(x9))
    S_phi, C_phi = math.sin(x7), math.cos(x7)
    S_psi, C_psi = math.sin(x11), math.cos(x11)

    den1 = C_psi * C_phi * S_theta + S_psi * S_phi
    den2 = C_phi * S_psi * S_theta - C_psi * S_phi
    den3 = C_theta * C_phi
    den1 = den1 if abs(den1) > 1e-3 else 1e-3 * (1 if den1 >= 0 else -1)
    den2 = den2 if abs(den2) > 1e-3 else 1e-3 * (1 if den2 >= 0 else -1)
    den3 = den3 if abs(den3) > 1e-3 else 1e-3 * (1 if den3 >= 0 else -1)

    Uf1 = (-M * x12 * x4 + M * x10 * x6 + M * G * S_theta - Ty + N_DIST["Nx"]
           - M * k["k2"] * z1 - M * e1 - M * k["k1"]) / den1
    Uf2 = (-M * x12 * x2 + M * x8 * x6 + M * G * C_theta * S_phi - Tx + N_DIST["Ny"]
           - M * e3 - M * k["k4"] * z2 - M * k["k3"]) / den2
    Uf3 = (-M * x10 * x12 + M * x8 * x4 - M * G * C_theta * C_phi - Tz + N_DIST["Nz"]
           - M * e5 - M * k["k6"] * z3 - M * k["k5"]) / den3

    # 原文用角度 x7/x9/x11 做角速度反馈（量纲不一致）；修正版改回角速度 x8/x10/x12
    fb_phi = x8 if fix_law else x7
    fb_the = x10 if fix_law else x9
    fb_psi = x12 if fix_law else x11

    U_phi = IXX * (-k["k8"] * z4 - fb_phi - k["k7"]) + x10 * x12 * IYY - x10 * x12 * IZZ + N_DIST["N_phi"]
    U_theta = IYY * (-k["k10"] * z5 - fb_the - k["k9"]) - x8 * x12 * IXX + x8 * x12 * IZZ + N_DIST["N_theta"]
    U_psi = IZZ * (-k["k12"] * z6 - fb_psi - k["k11"]) - x8 * x10 * IXX + x8 * x10 * IYY + N_DIST["N_psi"]

    U_win = (-IW * e13 - IW * k["k14"] * z7 - IW * k["k13"]
             - R_W * T0 - R_W ** 2 * x5 * S_CABLE * RHO * G) / R_W

    dx = [0.0] * (14 + 2 * N_MASS)
    dx[0] = x2
    dx[2] = x4
    dx[4] = x6
    dx[1] = (Uf1 * den1 + M * x12 * x4 - M * x10 * x6 - M * G * S_theta + Ty - N_DIST["Nx"]) / M
    dx[3] = (Uf2 * den2 + M * x12 * x2 - M * x8 * x6 - M * G * C_theta * S_theta + Tx - N_DIST["Ny"]) / M
    dx[5] = (Uf3 * den3 + M * x10 * x2 - M * x8 * x4 + M * G * C_theta * C_phi + Tz - N_DIST["Nz"]) / M
    dx[6] = x8
    dx[8] = x10
    dx[10] = x12
    dx[7] = (U_phi - x10 * x12 * IYY + x10 * x12 * IZZ - N_DIST["N_phi"]) / IXX
    dx[9] = (U_theta + x8 * x12 * IXX - x8 * x12 * IZZ - N_DIST["N_theta"]) / IYY
    dx[11] = (U_psi + x8 * x10 * IXX - x8 * x10 * IYY - N_DIST["N_psi"]) / IZZ

    # 绞车
    dx[12] = x14
    dx[13] = (U_win * R_W / IW) + (T0 / IW) * R_W + (R_W ** 2 / IW) * x5 * S_CABLE * RHO * G

    # 缆绳抖动层（弹簧-阻尼，首尾固定，与原文 cableDynamics.m 一致）
    cab = x[14:]
    for i in range(N_MASS):
        if i in (0, N_MASS - 1):
            dx[14 + 2 * i] = cab[2 * i + 1]
            dx[14 + 2 * i + 1] = 0.0
        else:
            dx[14 + 2 * i] = cab[2 * i + 1]
            dx[14 + 2 * i + 1] = (-2 * K_SPRING * cab[2 * i] - D_DAMP * cab[2 * i + 1]
                                  + K_SPRING * (cab[2 * i + 2] + cab[2 * i - 2])) / M_MASS
    return dx


def rk4(x, dt, wp_idx, fix_law, pitch_ref):
    k1 = deriv(x, wp_idx, fix_law, pitch_ref)
    k2 = deriv([a + 0.5 * dt * b for a, b in zip(x, k1)], wp_idx, fix_law, pitch_ref)
    k3 = deriv([a + 0.5 * dt * b for a, b in zip(x, k2)], wp_idx, fix_law, pitch_ref)
    k4 = deriv([a + dt * b for a, b in zip(x, k3)], wp_idx, fix_law, pitch_ref)
    return [a + dt / 6 * (b1 + 2 * b2 + 2 * b3 + b4)
            for a, b1, b2, b3, b4 in zip(x, k1, k2, k3, k4)]


def run(fix_law: bool, pitch_ref: float, t_end: float = 30.0, dt: float = 0.002):
    x = [0.0] * (14 + 2 * N_MASS)
    x[4] = 0.5      # 初始高度
    x[12] = 0.5     # 初始缆长
    x[14 + N_MASS] = 1.0  # 缆绳微小初始扰动（同原文）
    x[14 + N_MASS + N_MASS // 2] = 0.1

    wp = 0
    t = 0.0
    log = []
    arrived = {}
    vmax = 0.0
    diverged = False
    while t < t_end:
        nxt = rk4(x, dt, wp, fix_law, pitch_ref)
        if any(math.isnan(v) or abs(v) > 1e6 for v in nxt):
            diverged = True
            break
        x = nxt
        t += dt
        vmax = max(vmax, math.sqrt(x[1] ** 2 + x[3] ** 2 + x[5] ** 2))
        target = WAYPOINTS[wp]
        if math.dist((x[0], x[2], x[4]), target) < 0.5 and wp < len(WAYPOINTS) - 1:
            arrived[wp] = t
            wp += 1
        if abs(t % 1.0) < dt / 2:
            log.append((t, x[0], x[2], x[4], x[12], wp))
    err = math.dist((x[0], x[2], x[4]), WAYPOINTS[wp])
    l_ref = math.sqrt(abs(2 * A_CAT * math.sinh(x[0] / (2 * A_CAT))) + x[4] ** 2)
    return dict(diverged=diverged, t=t, wp=wp, pos=(x[0], x[2], x[4]), vmax=vmax,
                arrived=arrived, err=err, l=x[12], l_ref=l_ref,
                l_err=abs(x[12] - l_ref), log=log)


if __name__ == "__main__":
    for label, fix, pitch in (("原文参数（角速度反馈用角度）", False, math.pi / 6),
                              ("修正A：仅改角速度反馈", True, math.pi / 6),
                              ("修正B：角速度反馈 + 俯仰参考 0", True, 0.0)):
        r = run(fix, pitch)
        print(f"\n=== {label} ===")
        if r["diverged"]:
            print(f"发散了，在 t={r['t']:.2f}s 中止")
            continue
        print(f"仿真 {r['t']:.0f}s 完成，航点 #{r['wp']}，位置 "
              f"({r['pos'][0]:.2f}, {r['pos'][1]:.2f}, {r['pos'][2]:.2f})")
        print(f"距目标 {r['err']:.2f} m｜缆长 {r['l']:.2f} m（期望 {r['l_ref']:.2f} m，差 {r['l_err']:.2f} m）")
        # 最后 5 秒的高度波动，作为稳定性指标
        tail = [p[3] for p in r["log"] if p[0] > r["t"] - 5]
        if tail:
            print(f"末段高度波动：min {min(tail):.2f} / max {max(tail):.2f} m")
        print(f"最高速度 {r['vmax']:.2f} m/s｜到达航点时刻 "
              + ", ".join(f"#{i+1}@{tt:.1f}s" for i, tt in sorted(r['arrived'].items())))
