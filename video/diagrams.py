"""Schematic graphics for the explainer video, drawn frame by frame with Pillow.

Each `draw_*` function takes the time `t` in seconds into the shot and returns a 1920x1080 RGB image.
They are schematics, not data: nothing here is a measurement. Colours match the project site
(amber = surface change, cyan = ice, pink = AIS gap).
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
SS = 2  # draw at 2x and downsample for smooth lines and text
BG = (7, 24, 42)
GRID = (14, 42, 66)
WHITE = (240, 248, 252)
MUTED = (159, 216, 238)
SOFT = (150, 178, 196)
CYAN = (123, 223, 242)
PINK = (255, 107, 122)
AMBER = (255, 180, 84)
GREEN = (131, 243, 199)

FONT_DIR = "C:/Windows/Fonts/"


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    name = ("consolab.ttf" if bold else "consola.ttf") if mono else ("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(FONT_DIR + name, size * SS)


def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def ease(v: float) -> float:
    v = clamp01(v)
    return v * v * (3 - 2 * v)


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W * SS, H * SS), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 120):
        d.line([(x * SS, 0), (x * SS, H * SS)], fill=GRID, width=SS)
    for y in range(0, H, 120):
        d.line([(0, y * SS), (W * SS, y * SS)], fill=GRID, width=SS)
    return img, d


def finish(img: Image.Image) -> Image.Image:
    return img.resize((W, H), Image.LANCZOS)


def text(d: ImageDraw.ImageDraw, xy: tuple[float, float], s: str, size: int, fill, bold: bool = False,
         mono: bool = False, anchor: str = "la", alpha: float = 1.0, bg: tuple[int, int, int] = BG) -> None:
    if alpha < 1.0:
        fill = tuple(round(bg[i] + (fill[i] - bg[i]) * alpha) for i in range(3))
    d.text((xy[0] * SS, xy[1] * SS), s, font=font(size, bold, mono), fill=fill, anchor=anchor)


# ---------------------------------------------------------------- 1. a gap in an AIS track
def _track_point(x: float) -> tuple[float, float]:
    return x, 470 + 95 * math.sin(x / 250.0) + 40 * math.sin(x / 97.0)


def draw_gap(t: float, duration: float) -> Image.Image:
    img, d = canvas()
    text(d, (120, 90), "A vessel's AIS track (schematic)", 44, MUTED, bold=True)
    x_a, x_b, x_end = 160, 830, 1760  # gap runs from x_b to x_c
    x_c = 1120
    draw = ease(t / 1.6)  # the track draws itself left to right
    reach = x_a + (x_end - x_a) * draw

    def seg(xs: float, xe: float, color, dashed: bool = False) -> None:
        xe = min(xe, reach)
        if xe <= xs:
            return
        pts = [_track_point(x) for x in range(int(xs), int(xe) + 1, 4)]
        if not dashed:
            d.line([(px * SS, py * SS) for px, py in pts], fill=color, width=7 * SS, joint="curve")
        else:
            for i in range(0, len(pts) - 6, 12):
                d.line([(p[0] * SS, p[1] * SS) for p in pts[i:i + 6]], fill=color, width=7 * SS)

    seg(x_a, x_b, CYAN)
    seg(x_b, x_c, PINK, dashed=True)
    seg(x_c, x_end, CYAN)
    # position reports as dots
    for x in list(range(x_a, x_b, 70)) + list(range(x_c, x_end + 1, 70)):
        if x <= reach:
            px, py = _track_point(x)
            d.ellipse([(px - 9) * SS, (py - 9) * SS, (px + 9) * SS, (py + 9) * SS], fill=BG, outline=CYAN, width=4 * SS)
    # gap markers appear once the track has reached them
    if reach > x_b:
        px, py = _track_point(x_b)
        d.ellipse([(px - 14) * SS, (py - 14) * SS, (px + 14) * SS, (py + 14) * SS], fill=PINK)
    if reach > x_c:
        px, py = _track_point(x_c)
        d.ellipse([(px - 14) * SS, (py - 14) * SS, (px + 14) * SS, (py + 14) * SS], fill=PINK)
        mid = _track_point((x_b + x_c) / 2)
        pulse = 0.5 + 0.5 * math.sin(t * 6)
        text(d, (mid[0], mid[1] - 120), "?", 120, PINK, bold=True, anchor="mm", alpha=0.6 + 0.4 * pulse)
        text(d, (mid[0], 650), "Gap event: 12 hours or more", 38, PINK, bold=True, anchor="mm")
    # what the project does and does not say
    a = ease((t - 1.8) / 0.5)
    if a > 0:
        text(d, (960, 705), "Possible causes: reception, equipment, power, other.", 40, WHITE, anchor="ma", alpha=a)
        text(d, (960, 765), "The cause is not established.", 44, AMBER, bold=True, anchor="ma", alpha=a)
    return finish(img)


# ---------------------------------------------------------------- 2. a changed pixel
def _tundra(rng: random.Random) -> tuple[int, int, int]:
    base = rng.choice([(96, 104, 76), (112, 112, 84), (84, 96, 70), (124, 118, 92), (70, 86, 66)])
    j = rng.randint(-8, 8)
    return tuple(max(0, min(255, c + j)) for c in base)  # type: ignore[return-value]


def draw_pixel(t: float, duration: float) -> Image.Image:
    img, d = canvas()
    cols, rows, cell = 10, 6, 78
    gx = (W - (2 * cols * cell + 260)) // 2
    gy = 190
    changed = {(6, 2), (7, 2), (6, 3), (7, 3)}
    rng = random.Random(7)
    base = [[_tundra(rng) for _ in range(cols)] for _ in range(rows)]
    for side, title in ((0, "Summer, first year"), (1, "Summer, later year")):
        x0 = gx + side * (cols * cell + 260)
        text(d, (x0 + cols * cell / 2, gy - 70), title, 40, MUTED, bold=True, anchor="ma")
        for r in range(rows):
            for c in range(cols):
                appear = ease((t - 0.05 * (r + c) * 0.5) / 0.4)
                if appear <= 0:
                    continue
                colr = base[r][c]
                if side == 1 and (c, r) in changed:
                    k = ease((t - 1.3) / 0.7)
                    colr = tuple(round(colr[i] + (AMBER[i] - colr[i]) * k) for i in range(3))
                colr = tuple(round(BG[i] + (colr[i] - BG[i]) * appear) for i in range(3))
                d.rectangle([(x0 + c * cell) * SS, (gy + r * cell) * SS,
                             (x0 + (c + 1) * cell - 3) * SS, (gy + (r + 1) * cell - 3) * SS], fill=colr)
    # arrow between the grids
    ax0 = gx + cols * cell + 50
    ax1 = ax0 + 160
    ay = gy + rows * cell / 2
    d.line([(ax0 * SS, ay * SS), ((ax1 - 14) * SS, ay * SS)], fill=SOFT, width=6 * SS)
    d.polygon([(ax1 * SS, ay * SS), ((ax1 - 30) * SS, (ay - 18) * SS), ((ax1 - 30) * SS, (ay + 18) * SS)], fill=SOFT)
    # highlight on the changed block
    k = ease((t - 1.6) / 0.5)
    if k > 0:
        x0 = gx + (cols * cell + 260)
        bx0, by0 = x0 + 6 * cell - 8, gy + 2 * cell - 8
        bx1, by1 = x0 + 8 * cell + 5, gy + 4 * cell + 5
        pulse = 0.5 + 0.5 * math.sin(t * 6)
        d.rectangle([bx0 * SS, by0 * SS, bx1 * SS, by1 * SS], outline=WHITE, width=int((5 + 2 * pulse) * SS))
        text(d, ((bx0 + bx1) / 2, by1 + 22), "Large spectral change", 34, AMBER, bold=True, anchor="ma", alpha=k)
    a = ease((t - 2.0) / 0.5)
    if a > 0:
        text(d, (960, 690), "A threshold flags a candidate. It is not a finding.", 42, WHITE, anchor="ma", alpha=a)
        text(d, (960, 748), "It needs visual and documentary confirmation.", 44, AMBER, bold=True, anchor="ma", alpha=a)
    return finish(img)


# ---------------------------------------------------------------- 3. stated limits
LIMITS = [
    ("Cloud cover and polar night", "optical imagery is limited to clear summer scenes"),
    ("Radar thresholds", "backscatter depends on wind, ice type and viewing angle"),
    ("Nearshore AIS gaps", "the provider treats them as unreliable close to shore"),
    ("Coarse masks and sensors", "coast masks, projections and pixel size can mislead"),
]


def draw_limits(t: float, duration: float) -> Image.Image:
    img, d = canvas()
    text(d, (160, 110), "Limits the project states", 56, MUTED, bold=True)
    for i, (head, sub) in enumerate(LIMITS):
        a = ease((t - 0.25 - i * 0.6) / 0.45)
        if a <= 0:
            continue
        y = 240 + i * 135
        slide = (1 - a) * 40
        d.rectangle([(160 + slide) * SS, y * SS, (172 + slide) * SS, (y + 100) * SS],
                    fill=tuple(round(BG[c] + (AMBER[c] - BG[c]) * a) for c in range(3)))
        text(d, (210 + slide, y - 4), head, 52, WHITE, bold=True, alpha=a)
        text(d, (210 + slide, y + 58), sub, 36, SOFT, alpha=a)
    return finish(img)


# ---------------------------------------------------------------- 4. reproducible: the real verify output
CMD = "python -m arctic_passage_atlas verify"
VERIFY = [
    "PASS site files: 9 present",
    "PASS processed files: 9 present",
    "PASS manifest checksums: valid",
    "PASS publication mode: demo across manifest and summaries",
    "PASS demo labelling: present on every public page",
    "PASS GeoJSON structure: valid",
]


def draw_terminal(t: float, duration: float) -> Image.Image:
    img, d = canvas()
    x0, y0, x1, y1 = 180, 110, 1740, 770
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], radius=18 * SS, fill=(4, 14, 26), outline=GRID, width=3 * SS)
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, (y0 + 54) * SS], radius=18 * SS, fill=(14, 36, 58))
    for i, c in enumerate(((255, 107, 122), AMBER, GREEN)):
        d.ellipse([(x0 + 28 + i * 34) * SS, (y0 + 18) * SS, (x0 + 46 + i * 34) * SS, (y0 + 36) * SS], fill=c)
    text(d, (x0 + 150, y0 + 8), "arctic-passage-atlas", 30, SOFT)
    typed = int(clamp01(t / 1.1) * len(CMD))
    cursor = "_" if int(t * 3) % 2 == 0 else " "
    text(d, (x0 + 40, y0 + 90), "$ " + CMD[:typed] + (cursor if typed < len(CMD) or t < 1.3 else ""), 38, WHITE, mono=True)
    for i, line in enumerate(VERIFY):
        a = ease((t - 1.3 - i * 0.28) / 0.2)
        if a <= 0:
            continue
        y = y0 + 150 + i * 66
        text(d, (x0 + 40, y), "PASS", 38, GREEN, bold=True, mono=True, alpha=a, bg=(4, 14, 26))
        text(d, (x0 + 40 + 130, y), line[5:], 38, WHITE, mono=True, alpha=a, bg=(4, 14, 26))
    return finish(img)


# ---------------------------------------------------------------- 5. credits
CREDITS = [
    ("NASA", "Scientific Visualization Studio, Goddard Space Flight Center, GIBS imagery", AMBER),
    ("U.S. Geological Survey", "Landsat composite and the sea-ice photograph", CYAN),
    ("U.S. Coast Guard", "The icebreaker photograph", GREEN),
    ("All imagery is public domain", "Sources are listed in docs and in the video's build script", MUTED),
    ("Narration and music", "AI-generated: voice-over and instrumental backdrop", PINK),
]


def draw_credits(t: float, duration: float) -> Image.Image:
    img, d = canvas()
    text(d, (160, 100), "Imagery and sound", 56, MUTED, bold=True)
    for i, (head, sub, colour) in enumerate(CREDITS):
        a = ease((t - 0.3 - i * 0.9) / 0.5)
        if a <= 0:
            continue
        y = 235 + i * 118
        slide = (1 - a) * 40
        d.rectangle([(160 + slide) * SS, y * SS, (172 + slide) * SS, (y + 84) * SS],
                    fill=tuple(round(BG[c] + (colour[c] - BG[c]) * a) for c in range(3)))
        text(d, (210 + slide, y - 6), head, 48, WHITE, bold=True, alpha=a)
        text(d, (210 + slide, y + 48), sub, 34, SOFT, alpha=a)
    return finish(img)
