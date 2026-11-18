"""三份日志体检：悬停段的风扰响应、高度波动、振动与告警。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from pymavlink import mavutil

LOGS = [
    Path(r"C:\Users\84216\Desktop\00000019.BIN"),
    Path(r"C:\Users\84216\Desktop\00000020.BIN"),
    Path(r"C:\Users\84216\Desktop\00000021.BIN"),
]
CACHE = Path(r"D:\ai\deekseep\agent\data\jldh")
OUT = CACHE / "desk_logs.json"

MODE_NAMES = {0: "Stabilize", 1: "Acro", 2: "AltHold", 3: "Auto", 4: "Guided", 5: "Loiter",
              6: "RTL", 7: "Circle", 9: "Land", 16: "PosHold", 17: "Brake", 21: "SmartRTL",
              23: "Follow", 26: "AutoTune"}
TYPES = ["MSG", "MODE", "CTUN", "GPS", "BAT", "VIBE", "ATT", "BARO", "ERR"]


def parse(path: Path, key: str) -> dict:
    npz = CACHE / f"desk_{key}.npz"
    if npz.exists():
        return dict(np.load(npz, allow_pickle=True))
    m = mavutil.mavlink_connection(str(path), robust_parsing=True)
    rows = {k: [] for k in TYPES}
    while True:
        msg = m.recv_match(type=TYPES)
        if msg is None:
            break
        t = getattr(msg, "TimeUS", 0) / 1e6
        k = msg.get_type()
        if k == "MSG":
            rows[k].append((t, str(msg.Message)[:120]))
        elif k == "MODE":
            rows[k].append((t, int(msg.Mode)))
        elif k == "CTUN":
            rows[k].append((t, float(msg.ThO), float(msg.Alt), float(getattr(msg, "DAlt", 0))))
        elif k == "GPS":
            rows[k].append((t, float(msg.Spd), float(msg.HDop), int(msg.NSats), float(msg.Lat), float(msg.Lng)))
        elif k == "BAT":
            rows[k].append((t, float(msg.Volt), float(msg.Curr)))
        elif k == "VIBE":
            rows[k].append((t, float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ),
                            int(getattr(msg, "Clip0", 0)) + int(getattr(msg, "Clip1", 0)) + int(getattr(msg, "Clip2", 0))))
        elif k == "ATT":
            rows[k].append((t, float(msg.Roll), float(msg.Pitch), float(msg.Yaw),
                            float(getattr(msg, "DesRoll", 0)), float(getattr(msg, "DesPitch", 0))))
        elif k == "BARO":
            rows[k].append((t, float(msg.Alt)))
        elif k == "ERR":
            rows[k].append((t, int(msg.Subsys)))
    out = {}
    for k, v in rows.items():
        out[k] = np.array(v, dtype=object) if k == "MSG" else np.array(v, dtype=float)
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(npz, **out)
    return out


def analyse(path: Path, key: str) -> dict:
    d = parse(path, key)
    rep = {"file": path.name}
    msgs = d.get("MSG", np.empty((0, 2), dtype=object))
    fw, alerts = "", []
    for t, text in msgs:
        if "ArduCopter" in text and not fw:
            fw = text
        low = text.lower()
        if any(s in low for s in ("prearm", "failsafe", "ekf", "compass", "vibration", "fence")):
            alerts.append([round(float(t), 1), str(text)])
    rep["firmware"] = fw
    rep["alerts"] = alerts[:12]

    mode, ctun, gps, att = d["MODE"], d["CTUN"], d["GPS"], d["ATT"]
    vibe, bat, baro = d["VIBE"], d["BAT"], d["BARO"]
    rep["duration_s"] = round(float(ctun[-1, 0]), 1)
    rep["modes"] = {MODE_NAMES.get(int(k), str(int(k))): int(v)
                    for k, v in zip(*np.unique(mode[:, 1], return_counts=True))}
    rep["alt_range"] = [round(float(ctun[:, 2].min()), 2), round(float(ctun[:, 2].max()), 2)]
    rep["volt"] = [round(float(bat[:, 1].min()), 2), round(float(bat[:, 1].max()), 2)]
    rep["vibe_max"] = [round(float(vibe[:, i].max()), 1) for i in range(1, 4)]
    rep["vibe_clip"] = int(vibe[:, -1].sum())
    rep["sats_min"] = int(gps[:, 3].min()) if len(gps) else None

    # 悬停判定：Loiter + 速度<1.0 + 高度>2，至少 30 s
    idx = np.searchsorted(mode[:, 0], gps[:, 0], side="right") - 1
    loit = mode[np.clip(idx, 0, len(mode) - 1), 1] == 5
    stable = loit & (gps[:, 1] < 1.0)
    t = gps[:, 0]
    wins, start = [], None
    for i in range(len(t)):
        if stable[i] and start is None:
            start = t[i]
        if not stable[i] and start is not None:
            if t[i] - start >= 30:
                wins.append((start, t[i]))
            start = None
    if start is not None and t[-1] - start >= 30:
        wins.append((start, t[-1]))

    hover = []
    for a, b in wins:
        c = ctun[(ctun[:, 0] >= a) & (ctun[:, 0] <= b)]
        gg = gps[(gps[:, 0] >= a) & (gps[:, 0] <= b)]
        aa = att[(att[:, 0] >= a) & (att[:, 0] <= b)]
        if len(c) < 100 or len(aa) < 100:
            continue
        tilt = np.sqrt(aa[:, 1] ** 2 + aa[:, 2] ** 2)
        yaw_rate = np.gradient(np.degrees(np.unwrap(np.radians(aa[:, 3]))), aa[:, 0])
        hover.append({
            "start": round(a, 1), "dur": round(b - a, 1),
            "alt_mean": round(float(c[:, 2].mean()), 2),
            "alt_std": round(float(c[:, 2].std()), 2),
            "alt_pp": round(float(np.percentile(c[:, 2], 95) - np.percentile(c[:, 2], 5)), 2),
            "tilt_mean": round(float(tilt.mean()), 2),
            "tilt_std": round(float(tilt.std()), 2),
            "tilt_p95": round(float(np.percentile(tilt, 95)), 2),
            "tilt_max": round(float(tilt.max()), 1),
            "yaw_rate_rms": round(float(np.sqrt(np.mean(yaw_rate ** 2))), 1),
            "alt_rate_std": round(float(np.std(np.gradient(c[:, 2], c[:, 0]))), 2),
        })
    rep["hover_segments"] = hover

    bdiff = baro[:len(ctun), 1] - ctun[:len(ctun), 2] if len(baro) else np.array([])
    if len(bdiff):
        rep["baro_ekf"] = [round(float(bdiff[:200].mean()), 2), round(float(bdiff[-200:].mean()), 2)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    return rep


def main() -> int:
    res = []
    for p in LOGS:
        key = p.stem[-2:]
        print(f"分析 {p.name} ...", flush=True)
        try:
            res.append(analyse(p, key))
        except Exception as exc:
            res.append({"file": p.name, "error": str(exc)})
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
