"""生成小鲸鱼表情包 PNG（本机自产，无版权素材，纯几何绘制）

输出：D:/ruanjian/qq-bridge/state/memes/*.png
用法：python scripts/make_stickers.py
"""
from __future__ import annotations

import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = r"D:\ruanjian\qq-bridge\state\memes"
SIZE = 512
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]

# (文件名, 主文案, 副文案, 鲸鱼表情)
STICKERS = [
    ("wally_zaide.png", "在的", "", "normal"),
    ("wally_xiangxiang.png", "让我想想", "", "think"),
    ("wally_xiaosi.png", "笑死", "哈哈哈", "laugh"),
    ("wally_wuyu.png", "无语", "……", "flat"),
    ("wally_nanguo.png", "难过", "呜呜", "sad"),
    ("wally_zhenjing.png", "震惊", "啊？", "shock"),
    ("wally_e.png", "好饿", "白米饭", "hungry"),
    ("wally_shuile.png", "睡了", "先眯一会", "sleep"),
    ("wally_dongle.png", "懂了", "原来如此", "normal"),
    ("wally_666.png", "666", "行家啊", "laugh"),
    ("wally_wenhao.png", "？", "", "flat"),
    ("wally_leile.png", "累了", "歇会儿", "tired"),
    ("wally_baifan.png", "白饭", "= token", "hungry"),
    ("wally_fuwuqi.png", "服务器繁忙", "", "flat"),
    ("wally_dianzan.png", "点赞", "整挺好", "laugh"),
    ("wally_wanan.png", "晚安", "早点睡", "sleep"),
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def gradient(size: int, top=(226, 241, 255), bottom=(178, 214, 250)) -> Image.Image:
    img = Image.new("RGB", (size, size), top)
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (size, y)], fill=c)
    return img


def draw_whale(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, mood: str) -> None:
    body = (58, 122, 214)
    belly = (233, 244, 255)
    # 身体
    d.ellipse([cx - r, cy - int(r * 0.78), cx + r, cy + int(r * 0.78)], fill=body)
    # 肚皮
    d.ellipse([cx - int(r * 0.75), cy - int(r * 0.15), cx + int(r * 0.75), cy + int(r * 0.72)], fill=belly)
    # 尾巴
    tail = [
        (cx + int(r * 0.86), cy - int(r * 0.05)),
        (cx + int(r * 1.55), cy - int(r * 0.55)),
        (cx + int(r * 1.42), cy + int(r * 0.12)),
        (cx + int(r * 1.55), cy + int(r * 0.62)),
        (cx + int(r * 0.8), cy + int(r * 0.3)),
    ]
    d.polygon(tail, fill=body)
    # 眼睛
    ey = cy - int(r * 0.2)
    eye_r = max(6, int(r * 0.11))
    for ex in (cx - int(r * 0.34), cx + int(r * 0.3)):
        if mood == "sleep":
            d.arc([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], 200, 340, fill=(20, 40, 80), width=4)
        elif mood == "laugh":
            d.arc([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], 190, 350, fill=(20, 40, 80), width=5)
        elif mood == "sad":
            d.arc([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], 20, 160, fill=(20, 40, 80), width=4)
        elif mood == "shock":
            d.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=(255, 255, 255), outline=(20, 40, 80), width=3)
            d.ellipse([ex - eye_r // 2, ey - eye_r // 2, ex + eye_r // 2, ey + eye_r // 2], fill=(20, 40, 80))
        elif mood == "flat":
            d.rectangle([ex - eye_r, ey - 3, ex + eye_r, ey + 3], fill=(20, 40, 80))
        else:
            d.ellipse([ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r], fill=(255, 255, 255), outline=(20, 40, 80), width=2)
            d.ellipse([ex - eye_r // 2, ey - eye_r // 2 + 1, ex + eye_r // 2, ey + eye_r // 2 + 1], fill=(20, 40, 80))
    # 嘴
    mx, my = cx - int(r * 0.05), cy + int(r * 0.28)
    if mood == "laugh":
        d.arc([mx - int(r * 0.28), my - int(r * 0.25), mx + int(r * 0.28), my + int(r * 0.15)], 10, 170, fill=(20, 40, 80), width=5)
    elif mood == "sad":
        d.arc([mx - int(r * 0.22), my + int(r * 0.02), mx + int(r * 0.22), my + int(r * 0.3)], 190, 350, fill=(20, 40, 80), width=4)
    elif mood == "shock":
        d.ellipse([mx - int(r * 0.1), my, mx + int(r * 0.1), my + int(r * 0.24)], outline=(20, 40, 80), width=4)
    elif mood != "flat":
        d.arc([mx - int(r * 0.2), my - int(r * 0.1), mx + int(r * 0.2), my + int(r * 0.18)], 20, 160, fill=(20, 40, 80), width=4)
    # 喷水（好奇/开心）
    if mood in ("normal", "laugh"):
        hy = cy - int(r * 1.0)
        for dx, dy, rr in ((0, -18, 7), (-14, -30, 5), (14, -30, 5)):
            d.ellipse([cx + dx - rr, hy + dy - rr, cx + dx + rr, hy + dy + rr], fill=(150, 205, 250))
        d.arc([cx - int(r * 0.2), cy - int(r * 1.05), cx + int(r * 0.2), cy - int(r * 0.85)], 340, 200, fill=body, width=6)
    # 疲惫：汗滴
    if mood == "tired":
        d.ellipse([cx + int(r * 0.62), cy - int(r * 0.55), cx + int(r * 0.78), cy - int(r * 0.25)], fill=(150, 205, 250))
    if mood == "hungry":
        d.ellipse([cx + int(r * 0.5), cy + int(r * 0.6), cx + int(r * 0.72), cy + int(r * 0.78)], fill=(255, 236, 170))


def draw_text(d, text, sub):
    f1 = load_font(74 if len(text) <= 3 else 52)
    f2 = load_font(40)
    # 描边
    if text:
        w = d.textlength(text, font=f1)
        x = (SIZE - w) / 2
        y = SIZE - 150
        for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
            d.text((x + ox, y + oy), text, font=f1, fill=(255, 255, 255))
        d.text((x, y), text, font=f1, fill=(24, 56, 120))
    if sub:
        w = d.textlength(sub, font=f2)
        d.text(((SIZE - w) / 2, SIZE - 62), sub, font=f2, fill=(60, 96, 150))


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, text, sub, mood in STICKERS:
        img = gradient(SIZE)
        d = ImageDraw.Draw(img)
        draw_whale(d, SIZE // 2 - 10, 190, 118, mood)
        draw_text(d, text, sub)
        img.save(os.path.join(OUT_DIR, name), "PNG", optimize=True)
    print(f"生成 {len(STICKERS)} 张 -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
