"""批量解析机队日志，输出每架的固件、时长、高度、振动、电压、模式与告警。"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pymavlink import mavutil

ROOT = Path(r"D:\ai\deekseep\WJ")
OUT = Path(r"D:\ai\deekseep\agent\data\jldh\fleet_logs.json")

MODE_NAMES = {
    0: "Stabilize", 2: "AltHold", 3: "Auto", 4: "Guided", 5: "Loiter", 6: "RTL",
    7: "Circle", 9: "Land", 16: "PosHold", 17: "Brake", 21: "SmartRTL", 23: "Follow",
}


def analyse(path: Path) -> dict:
    m = mavutil.mavlink_connection(str(path), robust_parsing=True)
    fw = ""
    msgs, modes = [], Counter()
    alt, spd, volt, vibe = [], [], [], 0.0
    clip = 0
    t0 = tmax = 0.0
    first = True
    while True:
        msg = m.recv_match()
        if msg is None:
            break
        typ = msg.get_type()
        t = getattr(msg, "TimeUS", None)
        if t:
            t = t / 1e6
            if first:
                t0, first = t, False
            tmax = max(tmax, t - t0)
        if typ == "MSG":
            text = str(getattr(msg, "Message", "")).strip()
            if "ArduCopter" in text and not fw:
                fw = text
            if any(k in text for k in ("PreArm", "EKF", "Failsafe", "fence", "Compass")):
                msgs.append(text[:80])
        elif typ == "MODE":
            modes[MODE_NAMES.get(int(msg.Mode), str(msg.Mode))] += 1
        elif typ == "CTUN":
            alt.append(float(msg.Alt))
        elif typ == "GPS":
            spd.append(float(msg.Spd))
        elif typ == "BAT":
            volt.append(float(msg.Volt))
        elif typ == "VIBE":
            v = max(float(msg.VibeX), float(msg.VibeY), float(msg.VibeZ))
            vibe = max(vibe, v)
            clip += int(getattr(msg, "Clip0", 0)) + int(getattr(msg, "Clip1", 0)) + int(getattr(msg, "Clip2", 0))
    return {
        "name": path.stem,
        "firmware": fw,
        "duration": round(tmax, 1),
        "alt_max": round(max(alt), 1) if alt else None,
        "spd_max": round(max(spd), 1) if spd else None,
        "vibe_max": round(vibe, 1),
        "vibe_clip": clip,
        "volt": [round(min(volt), 1), round(max(volt), 1)] if volt else None,
        "modes": dict(modes),
        "alerts": msgs[:8],
    }


def main() -> int:
    results = []
    for d in sorted(ROOT.iterdir()):
        if not d.is_dir() or d.name in {"固件", "4.6.3固件"}:
            continue
        files = sorted({f.resolve() for f in d.rglob("*") if f.suffix.lower() == ".bin"})
        for f in files:
            try:
                info = analyse(f)
                info["aircraft"] = d.name
                info["file"] = str(f)
                results.append(info)
                print(f"OK {d.name}/{f.name} fw={info['firmware']} dur={info['duration']}s "
                      f"alt={info['alt_max']} vibe={info['vibe_max']}", flush=True)
            except Exception as exc:
                print(f"FAIL {d.name}/{f.name}: {exc}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n写入 {OUT} ({len(results)} 架)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
