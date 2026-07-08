"""Image utilities for the colour analysis board.

- recolor_shirt: tints the lower (clothing) region of a portrait to a target
  colour while preserving luminance, so every comparison portrait is identical
  except for shirt colour.
- heuristic_analysis: offline fallback that samples the face/hair regions to
  estimate warmth, depth, chroma, and contrast.
- palette_sheet: renders a shopping-ready swatch sheet as a PNG.
"""

from __future__ import annotations

import colorsys
import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(arr: np.ndarray) -> np.ndarray:
    return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]


# ----------------------------------------------------------------------------
# shirt recolouring
# ----------------------------------------------------------------------------

def recolor_shirt(img: Image.Image, hex_color: str, max_size: int = 420) -> Image.Image:
    """Return a copy of the portrait with the clothing region tinted.

    The clothing mask is a soft vertical gradient covering roughly the lower
    38%% of the frame, feathered so the transition is invisible at thumbnail
    size. Target colour is applied in a luminance-preserving way, which keeps
    fabric shading and folds intact.
    """
    img = img.convert("RGB")
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    arr = np.asarray(img).astype(np.float32)
    h, w, _ = arr.shape

    # soft mask: 0 above the shoulder line, ramping to 1 at the bottom
    shoulder = int(h * 0.62)
    feather = max(int(h * 0.10), 8)
    ys = np.arange(h, dtype=np.float32)
    ramp = np.clip((ys - shoulder) / feather, 0.0, 1.0)
    mask = np.repeat(ramp[:, None], w, axis=1)

    # narrow the mask away from the image edges slightly less at the bottom
    # (clothing usually spans the full width near the bottom of a portrait)
    lum = _luminance(arr) / 255.0
    target = np.array(hex_to_rgb(hex_color), dtype=np.float32)
    t_h, t_l, t_s = colorsys.rgb_to_hls(*(target / 255.0))

    # luminance-preserving recolour: keep original lightness variation,
    # centre it on the target colour's lightness
    lum_centered = lum - lum.mean() * 0 + 0  # keep raw luminance
    new_l = np.clip(t_l + (lum_centered - 0.55) * 0.55, 0.03, 0.97)

    hls = np.empty((h, w, 3), dtype=np.float32)
    hls[..., 0] = t_h
    hls[..., 1] = new_l
    hls[..., 2] = t_s

    # vectorised HLS -> RGB
    hh, ll, ss = hls[..., 0], hls[..., 1], hls[..., 2]

    def _channel(m1, m2, hue):
        hue = hue % 1.0
        out = np.where(hue < 1 / 6, m1 + (m2 - m1) * hue * 6.0,
              np.where(hue < 1 / 2, m2,
              np.where(hue < 2 / 3, m1 + (m2 - m1) * (2 / 3 - hue) * 6.0, m1)))
        return out

    m2 = np.where(ll <= 0.5, ll * (1.0 + ss), ll + ss - ll * ss)
    m1 = 2.0 * ll - m2
    r = _channel(m1, m2, hh + 1 / 3)
    g = _channel(m1, m2, hh)
    b = _channel(m1, m2, hh - 1 / 3)
    recolored = np.stack([r, g, b], axis=-1) * 255.0

    mask3 = mask[..., None]
    out = arr * (1.0 - mask3) + recolored * mask3
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


# ----------------------------------------------------------------------------
# offline heuristic analysis
# ----------------------------------------------------------------------------

def heuristic_analysis(img: Image.Image) -> dict:
    """Estimate colour-season axes by sampling face and hair regions.

    This is a deliberately simple fallback used when no API key is supplied.
    It samples the central face region for skin tone and the top band for
    hair, then derives warm/depth/chroma/contrast scores on a 0-100 scale.
    """
    img = img.convert("RGB")
    img.thumbnail((300, 300), Image.LANCZOS)
    arr = np.asarray(img).astype(np.float32)
    h, w, _ = arr.shape

    face = arr[int(h * 0.28):int(h * 0.55), int(w * 0.32):int(w * 0.68)]
    hair = arr[int(h * 0.02):int(h * 0.16), int(w * 0.25):int(w * 0.75)]

    skin = face.reshape(-1, 3)
    # keep plausibly skin-like pixels (drop very dark / very bright outliers)
    lum = _luminance(skin.reshape(-1, 1, 3)).ravel()
    keep = (lum > 40) & (lum < 245)
    if keep.sum() > 50:
        skin = skin[keep]
    r, g, b = skin.mean(axis=0)

    hsv = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    skin_lum = 0.299 * r + 0.587 * g + 0.114 * b
    hair_lum = float(_luminance(hair).mean()) if hair.size else skin_lum

    # warmth: red-vs-blue balance of skin, scaled
    warm = float(np.clip(50 + (r - b) * 0.9, 0, 100))
    # depth: darker overall complexion + hair => higher depth
    depth = float(np.clip(100 - (0.55 * skin_lum + 0.45 * hair_lum) / 2.4, 0, 100))
    # chroma: saturation of the skin sample (typical skin sits ~0.25-0.55)
    chroma = float(np.clip((hsv[1] * 100 - 18) * 1.7, 0, 100))
    # contrast: |skin - hair| luminance gap
    contrast = float(np.clip(abs(skin_lum - hair_lum) / 1.6, 0, 100))

    return dict(warm=round(warm), depth=round(depth),
                chroma=round(chroma), contrast=round(contrast),
                skin_rgb=(int(r), int(g), int(b)),
                eye_color="—", hair_depth="Deep" if hair_lum < 90 else
                ("Medium" if hair_lum < 160 else "Light"))


# ----------------------------------------------------------------------------
# shopping palette sheet (PNG export)
# ----------------------------------------------------------------------------

def palette_sheet(title: str, swatches: list[tuple[str, str]],
                  cols: int = 6, cell: int = 220) -> bytes:
    """Render named swatches into a print-ready PNG and return the bytes."""
    rows = (len(swatches) + cols - 1) // cols
    pad, header = 60, 140
    w = cols * cell + pad * 2
    h = rows * (cell + 70) + pad * 2 + header
    img = Image.new("RGB", (w, h), "#FFFFFF")
    d = ImageDraw.Draw(img)

    try:
        f_title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        f_label = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        f_hex = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except OSError:
        f_title = f_label = f_hex = ImageFont.load_default()

    d.text((pad, pad), title, fill="#111114", font=f_title)
    d.text((pad, pad + 66), "Shopping Palette", fill="#8A8178", font=f_label)

    for i, (name, hx) in enumerate(swatches):
        cx = pad + (i % cols) * cell
        cy = pad + header + (i // cols) * (cell + 70)
        d.rounded_rectangle([cx + 10, cy, cx + cell - 10, cy + cell - 40],
                            radius=28, fill=hx, outline="#E8E5DF", width=2)
        d.text((cx + 14, cy + cell - 30), name, fill="#26262B", font=f_label)
        d.text((cx + 14, cy + cell + 4), hx.upper(), fill="#9AA0A8", font=f_hex)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
