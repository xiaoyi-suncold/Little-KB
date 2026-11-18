"""逐份解析飞行日志：时间线、模式、事件、极值。"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np
from pymavlink import mavutil

MODE_NAMES = {
    0: "Stabilize", 1: "Acro", 2: "AltHold", 3: "Auto", 4: "Guided", 5: "Loiter",
    6: "RTL", 7: "Circle", 9: "Land", 16: "PosHold", 17: "Brake", 20: "GuidedNoGPS",
    21: "SmartRTL", 22: "FlowHold", 23: "Follow", 24: "ZigZag", 25: "SystemID", 26: "AutoTune",
}


def analyse(path: Path) -> dict:
    m = mavutil.mavlink_connection(str(path), robust_parsing=True)
    msgs, errs, modes = [], Counter(), []
    alt, spd, volt, vibe_clip = [], [], [], 0
    alt_t = []
    t0 = None
    t_max = 0.0
    while True:
        msg = m.recv_match()
        if msg is None:
            break
        typ = msg.get_type()
        t = getattr(msg, "TimeUS", None)
        t = t / 1e6 if t else None
        if t:
            t0 = t if t0 is None else t0
            t_max = max(t_max, t - t0)
        if typ == "MODE" and t:
            modes.append((round(t - (t0 or 0), 1), MODE_NAMES.get(int(msg.Mode), str(msg.Mode))))
        elif typ == "CTUN":
            alt.append(float(msg.Alt))
            alt_t.append(round(t - (t0 or 0), 1))
        elif typ == "GPS":
            spd.append(float(msg.Spd))
        elif typ == "BAT":
            volt.append(float(msg.Volt))
        elif typ == "VIBE":
            vibe_clip += int(getattr(msg, "Clip0", 0)) + int(getattr(msg, "Clip1", 0)) + int(getattr(msg, "Clip2", 0))
        elif typ == "MSG":
            text = str(getattr(msg, "Message", "")).strip()
            if text:
                msgs.append(text)
        elif typ == "ERR":
            errs[str(getattr(msg, "Subsys", "?"))] += 1
    airborne = [i for i, a in enumerate(alt) if a > 1.0]
    return {
        "file": path.name,
        "duration": round(t_max, 1),
        "modes": modes,
        "alt": (round(min(alt), 2), round(max(alt), 2)) if alt else None,
        "takeoff": alt_t[airborne[0]] if airborne else None,
        "land": alt_t[airborne[-1]] if airborne else None,
        "air_time": round(alt_t[airborne[-1]] - alt_t[airborne[0]], 1) if airborne else 0,
        "spd_max": round(max(spd), 2) if spd else None,
        "volt": (round(min(volt), 1), round(max(volt), 1)) if volt else None,
        "vibe_clip": vibe_clip,
        "msgs": msgs[:12],
        "errs": dict(errs),
    }


def main() -> int:
    folder = Path(sys.argv[1])
    for p in sorted(folder.glob("*.bin")):
        info = analyse(p)
        print(f"\n=== {info['file']} ===")
        print(f"  时长 {info['duration']}s  高度 {info['alt']}  最大速度 {info['spd_max']} m/s  电压 {info['volt']}  VIBE 削顶 {info['vibe_clip']}")
        print(f"  模式序列：{info['modes']}")
        if info["msgs"]:
            print("  消息：")
            for t in info["msgs"]:
                print(f"    - {t}")
        if info["errs"]:
            print(f"  错误子系统：{info['errs']}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
