"""DataFlash 日志速览：时长、模式、关键参数、振动、悬停段与 4 Hz 分量。

用法：
  python scripts/df_bin_report.py <日志或目录> [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

try:
    from pymavlink import mavutil
except ImportError:
    print("需要 pymavlink：python -m pip install pymavlink", file=sys.stderr)
    raise

KEY_PARAMS = [
    "MOT_THST_HOVER", "MOT_SPIN_MIN", "MOT_SPIN_ARM", "MOT_THST_EXPO", "MOT_HOVER_LEARN",
    "PSC_ACCZ_P", "PSC_ACCZ_I", "PSC_VELZ_P", "PSC_POSZ_P", "PSC_JERK_Z",
    "INS_ACCEL_FILTER", "INS_GYRO_FILTER", "INS_HNTCH_ENABLE",
    "LOIT_SPEED", "LOIT_ANG_MAX", "LOIT_BRK_DELAY", "LOIT_BRK_ACCEL", "LOIT_BRK_JERK",
    "ANGLE_MAX", "ATC_RAT_RLL_P", "ATC_RAT_RLL_D", "EK3_SRC1_POSZ",
]


def analyse(path: Path) -> dict:
    mlog = mavutil.mavlink_connection(str(path), robust_parsing=True)
    counts: Counter[str] = Counter()
    modes: list[tuple[float, int]] = []
    params: dict[str, float] = {}
    tho: list[tuple[float, float]] = []
    alt: list[tuple[float, float]] = []
    vibe: list[tuple[float, float, float, float]] = []
    accz: list[tuple[float, float]] = []
    us_times: list[float] = []
    ts_times: list[float] = []

    while True:
        msg = mlog.recv_match()
        if msg is None:
            break
        mtype = msg.get_type()
        counts[mtype] += 1
        t_us = getattr(msg, "TimeUS", None)
        if t_us:
            t = t_us / 1e6
            us_times.append(t)
        else:
            t = getattr(msg, "_timestamp", None)
            if t:
                ts_times.append(t)
        if mtype == "MODE" and t:
            modes.append((t, int(getattr(msg, "Mode", getattr(msg, "ModeNum", -1)))))
        elif mtype == "PARM":
            name = getattr(msg, "Name", "")
            if name in KEY_PARAMS:
                params[name] = round(float(getattr(msg, "Value", 0)), 4)
        elif mtype == "CTUN" and t:
            tho.append((t, float(getattr(msg, "ThO", 0))))
            alt.append((t, float(getattr(msg, "Alt", 0))))
        elif mtype == "VIBE" and t:
            vibe.append((t, float(getattr(msg, "VibeX", 0)), float(getattr(msg, "VibeY", 0)), float(getattr(msg, "VibeZ", 0))))
        elif mtype == "IMU" and t:
            if getattr(msg, "I", 0) == 0:
                accz.append((t, float(getattr(msg, "AccZ", 0))))

    clock = us_times if us_times else ts_times
    first_t = min(clock) if clock else None
    last_t = max(clock) if clock else None

    def series(rows):
        if not rows:
            return None, None
        arr = np.array(rows, dtype=float)
        t = arr[:, 0] - arr[0, 0]
        return t, arr[:, 1:]

    t_tho, v_tho = series(tho)
    t_alt, v_alt = series(alt)
    t_acc, v_acc = series(accz)
    t_vib, v_vib = series(vibe)

    hover_window = None
    four_hz = None
    if t_tho is not None and t_alt is not None and len(t_tho) > 20:
        a = v_alt[:, 0]
        # 找高度相对稳定的段落（滑动窗口方差最小且高度>1m）
        best = None
        win = 25.0
        for start in np.arange(0, max(t_tho[-1] - win, 0.1), 1.0):
            mask = (t_tho >= start) & (t_tho < start + win)
            if mask.sum() < 20:
                continue
            seg_alt = a[mask]
            if seg_alt.mean() < 1.0:
                continue
            score = np.nanstd(seg_alt)
            if best is None or score < best[0]:
                best = (score, start, start + win, float(seg_alt.mean()))
        if best:
            hover_window = {"start": round(best[1], 1), "end": round(best[2], 1),
                            "alt_mean": round(best[3], 2), "alt_std": round(float(best[0]), 3)}
            if t_acc is not None:
                mask = (t_acc >= best[1]) & (t_acc < best[2])
                if mask.sum() > 64:
                    seg_t = t_acc[mask]
                    seg_z = v_acc[mask, 0]
                    fs = 1.0 / np.median(np.diff(seg_t))
                    n = len(seg_z)
                    fft = np.abs(np.fft.rfft(seg_z - seg_z.mean())) / n * 2
                    freqs = np.fft.rfftfreq(n, 1.0 / fs)
                    band = (freqs >= 3.0) & (freqs <= 6.0)
                    if band.any():
                        idx = np.argmax(fft[band])
                        peak_f = float(freqs[band][idx])
                        peak_a = float(fft[band][idx])
                        four_hz = {
                            "sample_rate": round(float(fs), 2),
                            "peak_hz": round(peak_f, 2),
                            "peak_amp": round(peak_a, 3),
                            "energy_share_3_6": round(
                                float((fft[band] ** 2).sum() / max((fft ** 2).sum(), 1e-9)), 3),
                        }

    return {
        "file": path.name,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
        "duration_s": round((last_t - first_t), 1) if first_t and last_t else None,
        "messages": dict(counts.most_common(12)),
        "modes": sorted({m for _, m in modes}),
        "mode_switches": len(modes),
        "params": params,
        "tho": None if v_tho is None else {
            "min": round(float(v_tho.min()), 3), "max": round(float(v_tho.max()), 3),
            "mean": round(float(v_tho.mean()), 3)},
        "alt": None if v_alt is None else {
            "min": round(float(v_alt.min()), 2), "max": round(float(v_alt.max()), 2)},
        "vibe_max": None if v_vib is None else [round(float(x), 1) for x in v_vib.max(axis=0)],
        "hover": hover_window,
        "four_hz": four_hz,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    target = Path(args.target)
    files = sorted(target.glob("*.bin")) if target.is_dir() else [target]
    results = []
    for path in files:
        try:
            info = analyse(path)
        except Exception as exc:  # 单文件失败不阻断
            info = {"file": path.name, "error": str(exc)}
        results.append(info)
        print(json.dumps(info, ensure_ascii=False))

    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n写入 {args.json}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
