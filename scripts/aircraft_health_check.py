"""整机健康体检：固件、飞行包线、振动、GPS、EKF、电池、告警。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pymavlink import mavutil

BIN = Path(r"D:\wx_test\xwechat_files\wxid_ox5xlye12o3122_f7d6\msg\file\2026-11\2026-11-02 16-38-06.bin")
OUT = Path(r"D:\ai\deekseep\agent\data\jldh\health_final.json")
CACHE = Path(r"D:\ai\deekseep\agent\data\jldh\health_final.npz")

MODE_NAMES = {0: "Stabilize", 1: "Acro", 2: "AltHold", 3: "Auto", 4: "Guided", 5: "Loiter",
              6: "RTL", 7: "Circle", 9: "Land", 16: "PosHold", 17: "Brake", 21: "SmartRTL",
              23: "Follow", 26: "AutoTune"}
TYPES = ["MSG", "MODE", "CTUN", "GPS", "BAT", "VIBE", "ATT", "BARO", "ERR", "RCIN", "XKF1"]


def parse() -> dict:
    if CACHE.exists():
        return dict(np.load(CACHE, allow_pickle=True))
    m = mavutil.mavlink_connection(str(BIN), robust_parsing=True)
    rows = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        k = msg.get_type()
        if k == "MSG":
            rows[k].append((t, str(msg.Message)[:100]))
        elif k == "MODE":
            rows[k].append((t, int(msg.Mode)))
        elif k == "CTUN":
            rows[k].append((t, float(msg.ThO), float(msg.Alt)))
        elif k == "GPS":
            rows[k].append((t, float(msg.Spd), float(msg.HDop), int(msg.NSats), int(msg.Status)))
        elif k == "BAT":
            rows[k].append((t, float(msg.Volt), float(msg.Curr)))
        elif k == "VIBE":
            rows[k].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ),
                            int(getattr(msg, "Clip0", 0)), int(getattr(msg, "Clip1", 0)), int(getattr(msg, "Clip2", 0))))
        elif k == "ATT":
            rows[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw)))
        elif k == "BARO":
            rows[k].append((t, float(msg.Alt)))
        elif k == "ERR":
            rows[k].append((t, int(msg.Subsys)))
        elif k == "RCIN":
            rows[k].append((t, int(msg.C3)))
        elif k == "XKF1":
            rows[k].append((t, float(msg.PD)))
    out = {}
    for k, v in rows.items():
        if k == "MSG":
            out[k] = np.array(v, dtype=object)
        else:
            out[k] = np.array(v, dtype=float)
    np.savez(CACHE, **out)
    return out


def main() -> int:
    d = parse()
    report: dict = {}

    msgs = d.get("MSG", np.empty((0, 2), dtype=object))
    fw = ""
    alerts = []
    for t, text in msgs:
        if "ArduCopter" in text and not fw:
            fw = text
        low = text.lower()
        if any(s in low for s in ("prearm", "ekf", "failsafe", "fence", "compass", "vibration", "error", "critical")):
            alerts.append((round(float(t), 1), text))
    report["firmware"] = fw
    report["alerts"] = alerts[:20]

    mode = d["MODE"]
    report["duration_s"] = round(float(mode[-1, 0]), 1)
    report["modes"] = {MODE_NAMES.get(int(k), str(int(k))): int(v)
                       for k, v in zip(*np.unique(mode[:, 1], return_counts=True))}

    ctun = d["CTUN"]
    report["alt_range"] = [round(float(ctun[:, 2].min()), 2), round(float(ctun[:, 2].max()), 2)]

    gps = d["GPS"]
    report["speed_max"] = round(float(gps[:, 1].max()), 2)
    report["hdop_min_max"] = [round(float(gps[:, 2].min()), 2), round(float(gps[:, 2].max()), 2)]
    report["sats_min"] = int(gps[:, 3].min()) if len(gps) else None
    report["fix_counts"] = {int(k): int(v) for k, v in zip(*np.unique(gps[:, 4], return_counts=True))}

    bat = d["BAT"]
    report["volt"] = [round(float(bat[:, 1].min()), 2), round(float(bat[:, 1].max()), 2)]
    report["current_max"] = round(float(bat[:, 2].max()), 1)
    if len(bat) > 1:
        dt = np.diff(bat[:, 0]).sum()
        report["mah_est"] = round(float(np.trapz(bat[:, 2], bat[:, 0]) / 3.6), 0)

    vibe = d["VIBE"]
    report["vibe_max"] = [round(float(vibe[:, i].max()), 1) for i in range(1, 4)]
    report["vibe_clip"] = [int(vibe[:, i].sum()) for i in range(4, 7)]

    att = d["ATT"]
    tilt = np.sqrt(att[:, 1] ** 2 + att[:, 2] ** 2)
    report["tilt_max"] = round(float(tilt.max()), 1)

    baro = d["BARO"]
    diff = baro[:, 1].mean() - ctun[:, 2].mean()
    report["baro_ekf_diff_mean"] = round(float(diff), 2)
    # 首尾差
    if len(baro) > 100:
        k = 200
        first = baro[:k, 1].mean() - ctun[:k, 2].mean()
        last = baro[-k:, 1].mean() - ctun[-k:, 2].mean()
        report["baro_ekf_drift"] = round(float(last - first), 2)

    # 悬停窗口（Loiter + 速度<0.5）
    idx = np.searchsorted(mode[:, 0], gps[:, 0], side="right") - 1
    loiter = mode[np.clip(idx, 0, len(mode) - 1), 1] == 5
    stable = (gps[:, 1] < 0.5) & loiter
    t = gps[:, 0]
    wins, start = [], None
    for i in range(len(t)):
        if stable[i] and start is None:
            start = t[i]
        if not stable[i] and start is not None:
            if t[i] - start >= 20:
                wins.append((start, t[i]))
            start = None
    slopes = []
    for a, b in wins:
        c = ctun[(ctun[:, 0] >= a) & (ctun[:, 0] <= b)]
        if len(c) > 30:
            slopes.append(round(float(np.polyfit(c[:, 0] - a, c[:, 2], 1)[0] * 60), 2))
    report["hover_windows"] = len(wins)
    report["hover_slopes_m_per_min"] = slopes[:10]

    # RC 输入活跃度（判断是否有人飞）
    rc = d.get("RCIN")
    if rc is not None and len(rc):
        report["rc_throttle_range"] = [int(rc[:, 1].min()), int(rc[:, 1].max())]

    err = d.get("ERR")
    if err is not None and len(err):
        report["err_subsys"] = {int(k): int(v) for k, v in zip(*np.unique(err[:, 1], return_counts=True))}

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
