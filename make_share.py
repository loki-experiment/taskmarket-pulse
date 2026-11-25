#!/usr/bin/env python3
"""Render site/img/share.png (1200x630) from site/data.json.

Uses only the brand kit's fonts and colours, and only numbers that are in
data.json, so the share card can never drift from the dashboard.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "brand")
if not os.path.isdir(KIT):
    KIT = os.environ.get("BRAND_KIT", KIT)

GROUND = (18, 16, 14)
MAROON = (58, 20, 32)
CREAM = (239, 233, 226)
MUTED = (176, 167, 157)
MAGENTA = (231, 64, 121)
LINE = (69, 62, 55)


def font(name, size):
    return ImageFont.truetype(os.path.join(KIT, name), size)


def glow(img):
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(0, w, 2):
            d = math.hypot((x - w * 0.12) / (w * 0.75), (y + h * 0.15) / (h * 0.85))
            a = max(0.0, 1.0 - d)
            a = a * a * 0.95
            r = int(GROUND[0] + (MAROON[0] - GROUND[0]) * a)
            g = int(GROUND[1] + (MAROON[1] - GROUND[1]) * a)
            b = int(GROUND[2] + (MAROON[2] - GROUND[2]) * a)
            px[x, y] = (r, g, b)
            px[x + 1, y] = (r, g, b)


def main():
    data = json.load(open(os.path.join(HERE, "site", "data.json")))
    # the aggregate endpoints are market-wide, so the card is too
    rows30 = data["chains"]["4217"]["series"]["30d"]
    paid = sum(int(r["paidVolume"]) for r in rows30) / 1e6
    posted = sum(int(r["rewardVolume"]) for r in rows30) / 1e6
    open_tasks = sum(data["chains"][c]["open"]["count"] for c in data["chains"])

    img = Image.new("RGB", (1200, 630), GROUND)
    glow(img)
    d = ImageDraw.Draw(img)

    lock = Image.open(os.path.join(KIT, "taskmarket-lockup.png")).convert("RGBA")
    lw = 260
    lock = lock.resize((lw, int(lock.height * lw / lock.width)), Image.LANCZOS)
    img.paste(lock, (72, 56), lock)

    f_h = font("InstrumentSerif-Regular.ttf", 92)
    f_hi = font("InstrumentSerif-Italic.ttf", 92)
    f_body = font("InterTight-Variable.ttf", 30)
    f_mono = font("DepartureMono-Regular.otf", 26)
    f_num = font("InstrumentSerif-Regular.ttf", 62)
    f_lab = font("InterTight-Variable.ttf", 22)

    x, y = 72, 176
    d.text((x, y), "The market,", font=f_h, fill=CREAM)
    w1 = d.textlength("The market, ", font=f_h)
    d.text((x + w1, y), "live.", font=f_hi, fill=MAGENTA)
    d.text((x, y + 118), "Open tasks, agent activity, and rewards paid — on Base and Tempo.",
           font=f_body, fill=MUTED)

    # three real numbers, straight from data.json (Tempo, 30 days)
    stats = [
        ("open tasks, both chains", format(open_tasks, ",d")),
        ("rewards posted, 30 days", format(round(posted), ",d")),
        ("rewards paid, 30 days", format(round(paid), ",d")),
    ]
    bx, by = 72, 380
    for i, (lab, val) in enumerate(stats):
        cx = bx + i * 360
        d.line([(cx, by - 22), (cx + 40, by - 22)], fill=LINE, width=2)
        d.text((cx, by - 4), val, font=f_num, fill=CREAM)
        d.text((cx, by + 74), lab, font=f_lab, fill=MUTED)

    d.text((72, 566), "taskmarket.dev", font=f_mono, fill=CREAM)
    d.text((470, 566), "Made for a paid Taskmarket bounty. Not an official Taskmarket product.",
           font=ImageFont.truetype(os.path.join(KIT, "InterTight-Variable.ttf"), 18), fill=MUTED)

    out = os.path.join(HERE, "site", "img", "share.png")
    img.save(out, optimize=True)
    print("wrote", out, os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main()
