"""Draw the SAT-xtreme icon (a flame with a thermometer) into custom_components/sat_xtreme/brand/.

Usage: python dev/make_icon.py custom_components/sat_xtreme/brand
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

N = 2048  # draw large, scale down for smooth edges


def bezier(p0, p1, p2, p3, steps=80):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return pts


def flame():
    s = N / 100
    segs = [
        ((50, 4), (54, 22), (82, 34), (84, 62)),     # tip to right shoulder
        ((84, 62), (86, 84), (68, 97), (50, 97)),    # right side to bottom
        ((50, 97), (32, 97), (14, 84), (16, 62)),    # bottom to left side
        ((16, 62), (17, 48), (27, 40), (31, 30)),    # left side up
        ((31, 30), (35, 40), (37, 46), (42, 46)),    # small inner curl
        ((42, 46), (44, 32), (40, 18), (50, 4)),     # back to the tip
    ]
    pts = []
    for seg in segs:
        pts += bezier(*[(x * s, y * s) for x, y in seg])
    return pts


def gradient(top, bottom):
    img = Image.new("RGBA", (N, N))
    d = ImageDraw.Draw(img)
    for y in range(N):
        t = y / N
        d.line([(0, y), (N, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    return img


def main(out: Path):
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).polygon(flame(), fill=255)
    icon = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    icon.paste(gradient((255, 167, 38), (230, 74, 25)), (0, 0), mask)

    d = ImageDraw.Draw(icon)
    s = N / 100
    white = (255, 255, 255, 255)
    red = (230, 74, 25, 255)
    # thermometer: stem and bulb in white, mercury in red
    d.rounded_rectangle([44 * s, 40 * s, 56 * s, 78 * s], radius=6 * s, fill=white)
    d.ellipse([39.5 * s, 70 * s, 60.5 * s, 91 * s], fill=white)
    d.rounded_rectangle([47.5 * s, 55 * s, 52.5 * s, 80 * s], radius=2.5 * s, fill=red)
    d.ellipse([43.5 * s, 74 * s, 56.5 * s, 87 * s], fill=red)
    # scale marks
    for y in (46, 52, 58, 64):
        d.rounded_rectangle([57.5 * s, (y - 0.9) * s, 62 * s, (y + 0.9) * s], radius=0.9 * s, fill=white)

    icon = icon.crop(icon.getbbox())
    side = max(icon.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(icon, ((side - icon.width) // 2, (side - icon.height) // 2))
    out.mkdir(parents=True, exist_ok=True)
    square.resize((256, 256), Image.LANCZOS).save(out / "icon.png")
    square.resize((512, 512), Image.LANCZOS).save(out / "icon@2x.png")


main(Path(sys.argv[1]))
