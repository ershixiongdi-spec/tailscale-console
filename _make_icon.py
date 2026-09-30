# -*- coding: utf-8 -*-
"""生成应用图标 app.ico（沿用界面里的九宫格圆点标识）。

注意：PIL 存 ICO 时只能从「基础图」往小缩放，所以必须拿最大的 256px 作基础图，
      否则只会写出 16px 一档（踩过一次坑）。
"""
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT_TOP = (99, 91, 214)
ACCENT_BOT = (145, 132, 245)
OUT = Path(__file__).resolve().parent / "web" / "app.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def make(size: int) -> Image.Image:
    scale = 8  # 先大尺寸画，再缩小，边缘更顺滑
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # 竖向渐变底
    grad = Image.new("RGBA", (1, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        k = y / max(s - 1, 1)
        gd.point((0, y), fill=(
            round(ACCENT_TOP[0] + (ACCENT_BOT[0] - ACCENT_TOP[0]) * k),
            round(ACCENT_TOP[1] + (ACCENT_BOT[1] - ACCENT_TOP[1]) * k),
            round(ACCENT_TOP[2] + (ACCENT_BOT[2] - ACCENT_TOP[2]) * k),
            255,
        ))
    grad = grad.resize((s, s))

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    pad = s * 0.235
    step = (s - pad * 2) / 2
    r = s * 0.072
    for row in range(3):
        for col in range(3):
            cx, cy = pad + col * step, pad + row * step
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.LANCZOS)


base = make(256)
base.save(OUT, format="ICO", sizes=SIZES)

check = Image.open(OUT)
print("sizes in ico:", sorted(check.info.get("sizes", [])))
print("file:", OUT, OUT.stat().st_size, "bytes")
