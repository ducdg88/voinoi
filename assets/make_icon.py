"""Ve icon VoiNoi: chu voi dang noi, mieng ha to, he rang, voi gio cao, song am bay ra.

Chay: python assets/make_icon.py  (can Pillow). Tao assets/voinoi.ico va assets/voinoi.png.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

S = 2048  # ve lon roi thu nho cho net muot
OUT = Path(__file__).resolve().parent


def sc(v: float) -> int:
    return int(round(v * S / 1024))


def ellipse(draw: ImageDraw.ImageDraw, cx: float, cy: float, rx: float, ry: float, **kw: object) -> None:
    draw.ellipse((sc(cx - rx), sc(cy - ry), sc(cx + rx), sc(cy + ry)), **kw)


def bezier(p0, p1, p2, p3, steps: int = 400):
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        yield t, x, y


def tube(draw, curve, r0: float, r1: float, fill) -> None:
    for t, x, y in curve:
        r = r0 + (r1 - r0) * t
        ellipse(draw, x, y, r, r, fill=fill)


def layer() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def mask_of(img: Image.Image) -> Image.Image:
    return img.split()[3]


def main() -> None:
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # nen: o vuong bo tron, chuyen mau cam -> hong dam (noi bat tren thanh tac vu sang lan toi)
    bg = Image.new("RGBA", (S, S))
    top, bottom = (255, 159, 67), (219, 39, 119)
    px = bg.load()
    for y in range(S):
        for x in range(S):
            t = min(1.0, max(0.0, (x * 0.35 + y) / (S * 1.35)))
            px[x, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
    shape, d = layer()
    d.rounded_rectangle((sc(40), sc(40), sc(984), sc(984)), radius=sc(210), fill=(255, 255, 255, 255))
    canvas.paste(bg, (0, 0), mask_of(shape))
    background = canvas
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))  # tien canh (voi + song am), can giua sau

    body = (205, 214, 228, 255)
    shade = (160, 172, 192, 255)
    dark = (70, 80, 102, 255)

    # song am tu mieng bay ra (ve truoc de voi de len)
    waves, wd = layer()
    for i, (r, w) in enumerate(((140, 26), (205, 24), (270, 22))):
        alpha = 255 - i * 55
        wd.arc(
            (sc(700 - r), sc(655 - r), sc(700 + r), sc(655 + r)),
            start=-38, end=28, fill=(255, 255, 255, alpha), width=sc(w),
        )
    canvas.alpha_composite(waves)

    ele, ed = layer()
    # tai to phia sau
    ellipse(ed, 300, 500, 215, 270, fill=shade)
    ellipse(ed, 315, 505, 160, 210, fill=(236, 168, 190, 255))
    # dau
    ellipse(ed, 480, 470, 250, 240, fill=body)
    # ma phinh ben duoi
    ellipse(ed, 540, 615, 175, 160, fill=body)
    # voi gio cao, cuon o dau (thon dan)
    trunk = list(bezier((610, 470), (770, 470), (840, 260), (770, 150)))
    tube(ed, trunk, 90, 46, body)
    tip = list(bezier((770, 150), (745, 108), (688, 118), (698, 176), 120))
    tube(ed, tip, 46, 38, body)
    canvas.alpha_composite(ele)

    detail, dd = layer()
    # nep nhan tren voi
    for t0 in (0.35, 0.5, 0.65):
        _, x, y = next(p for p in bezier((610, 470), (770, 470), (840, 260), (770, 150)) if p[0] >= t0)
        r = 90 + (46 - 90) * t0
        dd.arc((sc(x - r * 0.9), sc(y - r * 0.9), sc(x + r * 0.9), sc(y + r * 0.9)),
               start=150, end=250, fill=shade, width=sc(9))
    # ngan tai
    dd.arc((sc(120), sc(260), sc(470), sc(740)), start=110, end=250, fill=(150, 162, 184, 255), width=sc(14))
    canvas.alpha_composite(detail)

    # mieng ha to nam gon trong mat: long mieng do sam, luoi hong, rang tren va rang duoi he ra
    mcx, mcy, mrx, mry = 585, 648, 118, 92
    mouth_mask, mm = layer()
    ellipse(mm, mcx, mcy, mrx, mry, fill=(255, 255, 255, 255))
    mouth, md = layer()
    ellipse(md, mcx, mcy, mrx + 20, mry + 20, fill=(110, 18, 40, 255))
    ellipse(md, mcx + 5, mcy + 78, 92, 52, fill=(244, 114, 182, 255))  # luoi
    ellipse(md, mcx + 5, mcy + 60, 12, 26, fill=(214, 84, 150, 255))  # ranh luoi
    for i, x in enumerate(range(mcx - 92, mcx + 92, 46)):  # rang tren
        md.rounded_rectangle((sc(x + 3), sc(mcy - mry - 10), sc(x + 43), sc(mcy - mry + 44 - abs(i - 1.5) * 8)),
                             radius=sc(11), fill=(255, 255, 255, 255))
    for i, x in enumerate(range(mcx - 60, mcx + 60, 42)):  # rang duoi
        md.rounded_rectangle((sc(x + 3), sc(mcy + mry - 36 + abs(i - 1) * 6), sc(x + 39), sc(mcy + mry + 10)),
                             radius=sc(10), fill=(255, 255, 255, 255))
    mouth_clipped = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mouth_clipped.paste(mouth, (0, 0), ImageChops.multiply(mask_of(mouth_mask), mask_of(mouth)))
    canvas.alpha_composite(mouth_clipped)
    lips, ld = layer()
    ld.ellipse((sc(mcx - mrx), sc(mcy - mry), sc(mcx + mrx), sc(mcy + mry)), outline=dark, width=sc(12))
    canvas.alpha_composite(lips)

    # mat to, long may nhuong len nhu dang noi hang say
    face, fd = layer()
    ellipse(fd, 515, 380, 48, 54, fill=(255, 255, 255, 255))
    ellipse(fd, 525, 388, 31, 37, fill=(30, 35, 52, 255))
    ellipse(fd, 537, 373, 11, 12, fill=(255, 255, 255, 255))
    fd.arc((sc(458), sc(290), sc(580), sc(360)), start=195, end=335, fill=dark, width=sc(14))
    # ma hong
    ellipse(fd, 420, 520, 44, 27, fill=(244, 114, 182, 150))
    canvas.alpha_composite(face)

    # can tien canh vao giua khung (voi dang lech len tren), phong nhe cho day dan
    box = canvas.getbbox()
    fg = canvas.crop(box)
    target = sc(900)
    ratio = min(target / fg.width, target / fg.height)
    fg = fg.resize((int(fg.width * ratio), int(fg.height * ratio)), Image.LANCZOS)
    canvas = background
    canvas.alpha_composite(fg, ((S - fg.width) // 2, (S - fg.height) // 2 + sc(6)))

    big = canvas.resize((1024, 1024), Image.LANCZOS)
    big.save(OUT / "voinoi.png")
    sizes = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]
    canvas.resize((256, 256), Image.LANCZOS).save(OUT / "voinoi.ico", sizes=sizes)
    print("saved", OUT / "voinoi.png", OUT / "voinoi.ico")


if __name__ == "__main__":
    main()
