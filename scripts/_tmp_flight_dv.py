import numpy as np

d = np.load(r"D:\ai\deekseep\agent\data\jldh\flight_1442.npz")
ctun, baro, bat = d["CTUN"], d["BARO"], d["BAT"]

print(f"{'时间':>6} {'高度范围':>14} {'ThO':>6} {'电压':>6} {'气压-EKF':>9}")
for t0 in np.arange(0, 1416, 120):
    c = ctun[(ctun[:, 0] >= t0) & (ctun[:, 0] < t0 + 120)]
    b = baro[(baro[:, 0] >= t0) & (baro[:, 0] < t0 + 120)]
    v = bat[(bat[:, 0] >= t0) & (bat[:, 0] < t0 + 120)]
    if len(c) < 5:
        continue
    diff = (b[:, 1].mean() - c[:, 2].mean()) if len(b) else float("nan")
    volt = v[:, 1].mean() if len(v) else float("nan")
    print(f"{t0:>6.0f} {c[:,2].min():>6.1f}~{c[:,2].max():<6.1f} {c[:,1].mean():>6.3f} {volt:>6.1f} {diff:>+9.2f}")

alt, t = ctun[:, 2], ctun[:, 0]
rate = np.gradient(alt, t)
print(f"\n最大爬升 {rate.max():.1f} m/s，最大下降 {rate.min():.1f} m/s")
print(f"最高点 {alt.max():.1f} m @ t={t[alt.argmax()]:.0f}s")
mask = ctun[:, 1] < 0.01
if mask.any():
    print(f"油门=0 时高度读数 {alt[mask].min():.2f}~{alt[mask].max():.2f} m")
