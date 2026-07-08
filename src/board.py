"""Full colour-board compositor.

Renders the complete analysis as ONE shareable PNG in an infographic layout:
portrait + colour profile rings + best neutrals on the top row, then the
best/avoid comparison-portrait grids (real recoloured shirts with ✓/✗ badges),
grouped colour palette, clothing & accessory tiles, metals, and a quick style
guide. Everything is drawn with PIL — no extra API calls.
"""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ----------------------------------------------------------------------------
# palette of the board itself
# ----------------------------------------------------------------------------
PAPER = "#F0EEE8"
CARD = "#FFFFFF"
BORDER = "#E4E1D9"
INK = "#1D1B17"
MUTED = "#8C867C"
GREEN = "#2E7D4F"
RED = "#C0392B"
AMBER = "#C9973F"

W = 2080          # canvas width
M = 36            # outer margin
G = 28            # gap between cards
PAD = 30          # card inner padding
RADIUS = 26       # card corner radius

THUMB_W, THUMB_H = 222, 266   # comparison-portrait cell
GRID_COLS = 8


# ----------------------------------------------------------------------------
# fonts (Windows / Linux / macOS, graceful fallback)
# ----------------------------------------------------------------------------
_FONT_PATHS = {
    ("serif", False): ["georgia.ttf", "DejaVuSerif.ttf",
                       "/System/Library/Fonts/Supplemental/Georgia.ttf"],
    ("serif", True): ["georgiab.ttf", "DejaVuSerif-Bold.ttf",
                      "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"],
    ("sans", False): ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf",
                      "/System/Library/Fonts/Supplemental/Arial.ttf"],
    ("sans", True): ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf",
                     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}
_font_cache: dict = {}


def _font(size: int, bold: bool = False, serif: bool = False):
    key = (size, bold, serif)
    if key not in _font_cache:
        f = None
        for name in _FONT_PATHS[("serif" if serif else "sans", bold)]:
            try:
                f = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        if f is None:
            try:
                f = ImageFont.load_default(size)
            except TypeError:
                f = ImageFont.load_default()
        _font_cache[key] = f
    return _font_cache[key]


def _tw(d: ImageDraw.ImageDraw, text: str, font) -> int:
    box = d.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _ctext(d, cx, y, text, font, fill=INK):
    """Draw text horizontally centred on cx."""
    d.text((cx - _tw(d, text, font) / 2, y), text, fill=fill, font=font)


def _tracked(d, cx, y, text, font, fill=INK, spacing=3):
    """Letter-spaced, centred caps — used for card titles."""
    text = text.upper()
    total = sum(_tw(d, ch, font) + spacing for ch in text) - spacing
    x = cx - total / 2
    for ch in text:
        d.text((x, y), ch, fill=fill, font=font)
        x += _tw(d, ch, font) + spacing


# ----------------------------------------------------------------------------
# drawing primitives
# ----------------------------------------------------------------------------
def _card(d, x, y, w, h):
    d.rounded_rectangle([x, y, x + w, y + h], radius=RADIUS,
                        fill=CARD, outline=BORDER, width=2)


def _header_band(d, x, y, w, color):
    """Coloured title band across the top of a card."""
    d.rounded_rectangle([x, y, x + w, y + 64 + RADIUS], radius=RADIUS,
                        fill=color)
    d.rectangle([x, y + 64 - RADIUS, x + w, y + 64], fill=color)


def _badge(d, cx, cy, ok: bool, r=19):
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=GREEN if ok else RED, outline="#FFFFFF", width=3)
    if ok:
        d.line([(cx - 8, cy + 1), (cx - 2, cy + 7), (cx + 9, cy - 7)],
               fill="#FFFFFF", width=4, joint="curve")
    else:
        d.line([(cx - 7, cy - 7), (cx + 7, cy + 7)], fill="#FFFFFF", width=4)
        d.line([(cx - 7, cy + 7), (cx + 7, cy - 7)], fill="#FFFFFF", width=4)


def _mark(d, cx, cy, kind: str, r=17):
    """Outlined ✓ / ✗ / △ marker used in the style guide and metals."""
    color = {"ok": GREEN, "no": RED, "warn": AMBER}[kind]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
    if kind == "ok":
        d.line([(cx - 7, cy + 1), (cx - 2, cy + 6), (cx + 8, cy - 6)],
               fill=color, width=4, joint="curve")
    elif kind == "no":
        d.line([(cx - 6, cy - 6), (cx + 6, cy + 6)], fill=color, width=4)
        d.line([(cx - 6, cy + 6), (cx + 6, cy - 6)], fill=color, width=4)
    else:
        d.polygon([(cx, cy - 7), (cx - 8, cy + 6), (cx + 8, cy + 6)],
                  outline=color, width=3)


def _ring(d, cx, cy, r, frac, color, width=11):
    d.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill="#ECE9E2",
          width=width)
    d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * frac,
          fill=color, width=width)


def _rounded_thumb(img: Image.Image, w: int, h: int, r=16) -> Image.Image:
    thumb = ImageOps.fit(img.convert("RGB"), (w, h), Image.LANCZOS)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=r, fill=255)
    out = Image.new("RGB", (w, h), CARD)
    out.paste(thumb, (0, 0), mask)
    return out


def _swatch_circle(d, cx, cy, r, hx):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hx,
              outline="#00000018", width=1)


def _axis_word(value: int, low: str, high: str, mid="Neutral") -> str:
    return high if value >= 60 else (low if value <= 40 else mid)


# ----------------------------------------------------------------------------
# section renderers — each draws at (x, y) and returns the height used
# ----------------------------------------------------------------------------
def _draw_portrait_card(img, d, x, y, w, h, portrait):
    _card(d, x, y, w, h)
    inner = _rounded_thumb(portrait, w - 2 * PAD + 8, h - 2 * PAD + 8, r=18)
    img.paste(inner, (x + PAD - 4, y + PAD - 4))


def _draw_profile_card(img, d, x, y, w, h, season_name, season, result):
    _card(d, x, y, w, h)
    cx = x + w / 2
    _tracked(d, cx, y + 26, "Colour Profile", _font(26, bold=True))

    rows = [
        ("WARM / COOL", result["warm"], "#D98A4B",
         _axis_word(result["warm"], "Cool", "Warm")),
        ("DEEP / LIGHT", result["depth"], "#3A2E24",
         _axis_word(result["depth"], "Light", "Deep", "Medium")),
        ("SOFT / BRIGHT", result["chroma"], "#C9973F",
         _axis_word(result["chroma"], "Muted", "Bright", "Soft")),
        ("CONTRAST", result["contrast"], "#1B1B1B",
         "High" if result["contrast"] >= 70 else
         ("Medium-High" if result["contrast"] >= 50 else
          ("Medium" if result["contrast"] >= 35 else "Low"))),
    ]
    ry = y + 84
    for label, value, color, word in rows:
        _ring(d, x + PAD + 34, ry + 30, 30, value / 100, color)
        d.text((x + PAD + 92, ry + 12), label, fill=INK, font=_font(24, bold=True))
        tw = _tw(d, word, _font(24))
        d.text((x + w - PAD - tw, ry + 12), word, fill="#55524B", font=_font(24))
        ry += 82

    d.line([x + PAD, ry + 6, x + w - PAD, ry + 6], fill=BORDER, width=2)
    _tracked(d, cx, ry + 24, "Season", _font(20, bold=True), fill=MUTED)
    _ctext(d, cx, ry + 52, season_name.upper(), _font(46, bold=True, serif=True),
           fill=season["best"][0][1])

    feats = [
        (f'{result["undertone"].title()}', "Undertone",
         "#D98A4B" if result["warm"] >= 50 else "#7FA8D9"),
        (rows[1][3], "Value", "#1F2A44" if result["depth"] >= 50 else "#E8DFD2"),
        (rows[2][3], "Chroma", rows[2][2]),
        (rows[3][3], "Contrast", "#3A3D42"),
    ]
    fy = ry + 130
    fw = (w - 2 * PAD) / 4
    for i, (word, label, color) in enumerate(feats):
        fx = x + PAD + fw * i + fw / 2
        _swatch_circle(d, fx, fy + 26, 26, color)
        _ctext(d, fx, fy + 62, word, _font(20, bold=True))
        _ctext(d, fx, fy + 88, label, _font(18), fill=MUTED)


def _draw_neutrals_card(d, x, y, w, h, neutrals):
    _card(d, x, y, w, h)
    _tracked(d, x + w / 2, y + 26, "Best Neutrals", _font(26, bold=True))
    ry = y + 92
    step = (h - 110) / len(neutrals)
    for name, hx in neutrals:
        _swatch_circle(d, x + PAD + 30, ry + step / 2 - 4, 27, hx)
        d.text((x + PAD + 78, ry + step / 2 - 19), name, fill=INK,
               font=_font(25))
        ry += step


def _grid_card_height(n: int) -> int:
    rows = math.ceil(n / GRID_COLS)
    return 64 + PAD + rows * (THUMB_H + 46) + PAD - 18


def _draw_portrait_grid_card(img, d, x, y, w, title, thumbs, ok):
    h = _grid_card_height(len(thumbs))
    _card(d, x, y, w, h)
    _header_band(d, x, y, w, GREEN if ok else RED)
    _tracked(d, x + w / 2, y + 17, title, _font(25, bold=True), fill="#FFFFFF")

    gap = (w - 2 * PAD - GRID_COLS * THUMB_W) / (GRID_COLS - 1)
    for i, (name, hx, thumb) in enumerate(thumbs):
        cx = x + PAD + (i % GRID_COLS) * (THUMB_W + gap)
        cy = y + 64 + PAD + (i // GRID_COLS) * (THUMB_H + 46)
        img.paste(_rounded_thumb(thumb, THUMB_W, THUMB_H), (int(cx), int(cy)))
        _badge(d, cx + THUMB_W - 27, cy + 27, ok)
        _ctext(d, cx + THUMB_W / 2, cy + THUMB_H + 8, name, _font(21))
    return h


def _palette_card_height(groups: dict) -> int:
    heights = []
    for i in range(0, len(groups), 3):
        row = list(groups.values())[i:i + 3]
        heights.append(max(34 + math.ceil(len(c) / 6) * 96 for c in row))
    return 80 + sum(heights) + 18 * len(heights)


def _draw_palette_card(d, x, y, w, groups):
    h = _palette_card_height(groups)
    _card(d, x, y, w, h)
    _tracked(d, x + w / 2, y + 26, "Colour Palette", _font(26, bold=True))
    gy = y + 80
    col_w = (w - 2 * PAD - 2 * G) / 3
    items = list(groups.items())
    for i in range(0, len(items), 3):
        row = items[i:i + 3]
        row_h = 0
        for j, (gname, chips) in enumerate(row):
            gx = x + PAD + j * (col_w + G)
            _tracked(d, gx + col_w / 2, gy, gname, _font(19, bold=True),
                     fill=MUTED, spacing=2)
            chip_w = (col_w - 5 * 10) / 6
            for k, (name, hx) in enumerate(chips):
                ccx = gx + (k % 6) * (chip_w + 10)
                ccy = gy + 34 + (k // 6) * 96
                d.rounded_rectangle([ccx, ccy, ccx + chip_w, ccy + 62],
                                    radius=10, fill=hx, outline="#00000014")
            row_h = max(row_h, 34 + math.ceil(len(chips) / 6) * 96)
        gy += row_h + 18
    return h


def _draw_tile_card(d, x, y, w, h, title, items):
    """Clothing / accessory tiles: colour block + item + colour name."""
    _card(d, x, y, w, h)
    _tracked(d, x + w / 2, y + 26, title, _font(26, bold=True))
    per_row = 5 if len(items) > 8 else 4
    gap = 16
    tile_w = (w - 2 * PAD - (per_row - 1) * gap) / per_row
    ty = y + 82
    for i, (item, cname, hx) in enumerate(items):
        tx = x + PAD + (i % per_row) * (tile_w + gap)
        yy = ty + (i // per_row) * 196
        d.rounded_rectangle([tx, yy, tx + tile_w, yy + 118], radius=14,
                            fill=hx, outline="#00000014")
        _ctext(d, tx + tile_w / 2, yy + 128, item, _font(22, bold=True))
        _ctext(d, tx + tile_w / 2, yy + 156, cname, _font(19), fill=MUTED)


def _draw_metals_card(d, x, y, w, h, metals):
    _card(d, x, y, w, h)
    _tracked(d, x + w / 2, y + 26, "Best Metals", _font(26, bold=True))
    ry = y + 84
    for kind, entries in (("ok", metals["yes"]), ("warn", metals["caution"]),
                          ("no", metals["no"])):
        for name, hx in entries:
            d.rounded_rectangle([x + PAD, ry, x + w - PAD, ry + 56],
                                radius=14, outline=BORDER, width=2)
            _swatch_circle(d, x + PAD + 34, ry + 28, 18, hx)
            d.text((x + PAD + 66, ry + 14), name, fill=INK, font=_font(23))
            _mark(d, x + w - PAD - 34, ry + 28, kind, r=15)
            ry += 66


def _draw_style_card(d, x, y, w, h, tips_yes, tips_no):
    _card(d, x, y, w, h)
    _tracked(d, x + w / 2, y + 26, "Quick Style Guide", _font(26, bold=True))
    ry = y + 84
    for kind, tips in (("ok", tips_yes), ("no", tips_no)):
        for t in tips:
            prefix = "" if kind == "ok" else "Avoid "
            d.rounded_rectangle([x + PAD, ry, x + w - PAD, ry + 56],
                                radius=14, outline=BORDER, width=2,
                                fill="#FBFAF7" if kind == "ok" else "#FDF6F5")
            _mark(d, x + PAD + 30, ry + 28, kind, r=15)
            d.text((x + PAD + 62, ry + 14), prefix + t, fill=INK,
                   font=_font(23))
            ry += 66


# ----------------------------------------------------------------------------
# public entry point
# ----------------------------------------------------------------------------
CLOTHING = ["Suit", "Blazer", "Shirt", "Polo", "Sweater",
            "Turtleneck", "Jacket", "Coat", "Henley", "T-Shirt"]
ACCESSORIES = ["Watch Strap", "Belt", "Wallet", "Shoes",
               "Tie", "Pocket Square", "Bag", "Sunglasses"]


def render_board(portrait: Image.Image, season_name: str, season: dict,
                 result: dict,
                 best_thumbs: list[tuple[str, str, Image.Image]],
                 avoid_thumbs: list[tuple[str, str, Image.Image]]) -> bytes:
    """Compose the full analysis into one PNG and return its bytes.

    best_thumbs / avoid_thumbs are (colour name, hex, recoloured portrait)
    triples — the recolouring is done by the caller so its cache is reused.
    """
    inner_w = W - 2 * M
    col3 = (inner_w - 2 * G) / 3
    h_row1 = 660
    h_best = _grid_card_height(len(best_thumbs))
    h_avoid = _grid_card_height(len(avoid_thumbs))
    h_palette = _palette_card_height(season["groups"])
    h_tiles = 82 + math.ceil(len(CLOTHING) / 5) * 196 + 8
    metal_count = sum(len(v) for v in season["metals"].values())
    tip_count = len(season["tips_yes"]) + len(season["tips_no"])
    h_bottom = 84 + max(metal_count, tip_count) * 66 + 12

    total_h = int(M + h_row1 + G + h_best + G + h_avoid + G + h_palette
                  + G + h_tiles + G + h_bottom + M)
    img = Image.new("RGB", (W, total_h), PAPER)
    d = ImageDraw.Draw(img, "RGBA")

    # row 1 — portrait / profile / neutrals
    y = M
    _draw_portrait_card(img, d, M, y, int(col3), h_row1, portrait)
    _draw_profile_card(img, d, int(M + col3 + G), y, int(col3), h_row1,
                       season_name, season, result)
    _draw_neutrals_card(d, int(M + 2 * (col3 + G)), y, int(col3), h_row1,
                        season["neutrals"])
    y += h_row1 + G

    # comparison grids
    y += _draw_portrait_grid_card(img, d, M, y, inner_w,
                                  "Best Colours — Wear These",
                                  best_thumbs, ok=True) + G
    y += _draw_portrait_grid_card(img, d, M, y, inner_w,
                                  "Avoid Colours — Wear These Less",
                                  avoid_thumbs, ok=False) + G

    # palette
    y += _draw_palette_card(d, M, y, inner_w, season["groups"]) + G

    # clothing / accessories
    half = (inner_w - G) / 2
    pal = season["best"] + season["neutrals"]
    clothing = [(item, *pal[(i * 3) % len(pal)])
                for i, item in enumerate(CLOTHING)]
    leather = [c for c in season["neutrals"] if c[0] not in
               ("Cream", "Ivory", "Pure White", "Porcelain")] or season["neutrals"]
    accessories = [(item, *leather[(i * 2) % len(leather)])
                   for i, item in enumerate(ACCESSORIES)]
    _draw_tile_card(d, M, y, int(half), h_tiles, "Best Clothing", clothing)
    _draw_tile_card(d, int(M + half + G), y, int(half), h_tiles,
                    "Accessories", accessories)
    y += h_tiles + G

    # metals / style guide
    _draw_metals_card(d, M, y, int(half), h_bottom, season["metals"])
    _draw_style_card(d, int(M + half + G), y, int(half), h_bottom,
                     season["tips_yes"], season["tips_no"])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
