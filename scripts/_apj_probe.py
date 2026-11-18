import base64, json, re, zlib
from pathlib import Path
for p in [Path(r"D:\ai\deekseep\WJ\固件\BC_FC_1.0.2.apj"), Path(r"D:\ai\deekseep\WJ\4.6.3固件\arducopter.apj")]:
    meta = json.loads(p.read_bytes())
    b = zlib.decompress(base64.b64decode(meta["image"]))
    print("\n==", p.name, len(b), "bytes")
    for pat in [b"Copter", b"ArduCopter", b"4.6", b"BC_FC", b"ChibiOS", b"V4."]:
        idx = b.find(pat)
        print(f"  {pat!r}: {'@'+str(idx) if idx>=0 else 'not found'}")
        if idx >= 0:
            print("     ctx:", b[max(0,idx-24):idx+48])
