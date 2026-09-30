# -*- coding: utf-8 -*-
"""生成应用图标（沿用界面里的九宫格圆点标识）。

产物（都放在 web/ 下）：
  app.ico   Windows 用（PyInstaller --icon、窗口图标）
  app.icns  macOS 用（.app 包图标）
  app.png   512px 通用图（文档、README 用）

注意：PIL 存 ICO 时只能从「基础图」往小缩放，所以必须拿最大的 256px 作基础图，
      否则只会写出 16px 一档（踩过一次坑）。
"""
from pathlib import Path

from PIL import Image, ImageDraw

ACCENT_TOP = (99, 91, 214)
ACCENT_BOT = (145, 132, 245)
WEB = Path(__file__).resolve().parent / "web"
OUT = WEB / "app.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
# macOS .icns 需要的档位（Pillow 会挑能用的写进去）
ICNS_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)]


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

# macOS：先画一张 512 的，再写 .icns 与 png
big = make(512)
icns_path = WEB / "app.icns"
icns_ok = True
try:
    big.save(icns_path, format="ICNS", sizes=ICNS_SIZES)
except Exception as exc:  # noqa: BLE001
    icns_ok = False
    print("icns 生成失败（不致命，.app 会用默认图标）：", exc)

png_path = WEB / "app.png"
big.save(png_path, format="PNG")

check = Image.open(OUT)
print("sizes in ico :", sorted(check.info.get("sizes", [])))
print("ico          :", OUT, OUT.stat().st_size, "bytes")
print("icns         :", (icns_path.stat().st_size if icns_ok and icns_path.is_file() else "-"), "bytes")
print("png          :", png_path, png_path.stat().st_size, "bytes")
