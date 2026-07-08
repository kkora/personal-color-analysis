"""Personal Colour Analysis Board — Streamlit app.

Upload a portrait → get a diagram-first, luxury-consultant style colour board:
season classification, axis gauges, neutrals, best/avoid comparison portraits,
master palette, metals, style tips, combinations, and a downloadable
shopping palette.
"""

import json

import streamlit as st
from PIL import Image, ImageOps

from src.analysis import analyze, models_for, provider_names
from src.board import render_board
from src.genimage import EDIT_MODELS, ai_recolor, resolve_key, supports_image_edit
from src.imaging import palette_sheet, recolor_shirt
from src.palettes import SEASONS

st.set_page_config(page_title="Personal Colour Analysis",
                   page_icon="🎨", layout="wide")

# ----------------------------------------------------------------------------
# design system
# ----------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family:'Inter',-apple-system,sans-serif; }
.stApp { background:#FFFFFF; }
.block-container { padding-top:2.2rem; max-width:1180px; }

.eyebrow { font-size:11px; letter-spacing:.22em; text-transform:uppercase;
  color:#9A948B; font-weight:600; margin-bottom:2px; }
h1.board-title { font-family:'Fraunces',serif; font-weight:600; font-size:44px;
  color:#141414; margin:0 0 4px 0; letter-spacing:-.01em; }
.season-chip { display:inline-block; padding:10px 26px; border-radius:999px;
  font-family:'Fraunces',serif; font-size:26px; font-weight:600;
  letter-spacing:.02em; color:#fff; }

.card { background:#FFFFFF; border:1px solid #ECEAE5; border-radius:22px;
  padding:26px 28px; box-shadow:0 8px 28px rgba(20,20,20,.05); }
.section-label { font-size:11px; letter-spacing:.2em; text-transform:uppercase;
  color:#B0AAA0; font-weight:600; }
.section-title { font-family:'Fraunces',serif; font-size:26px; font-weight:600;
  color:#161616; margin:2px 0 14px 0; }

.gauge-row { display:flex; align-items:center; gap:14px; margin:14px 0; }
.gauge-label { width:64px; font-size:12px; color:#6E6A63; font-weight:500; text-align:right; }
.gauge-label.r { text-align:left; }
.gauge-track { flex:1; height:8px; border-radius:99px; position:relative; }
.gauge-dot { position:absolute; top:50%; transform:translate(-50%,-50%);
  width:20px; height:20px; border-radius:50%; background:#161616;
  border:4px solid #fff; box-shadow:0 2px 8px rgba(0,0,0,.28); }

.swatch { width:76px; height:76px; border-radius:50%;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,.06), 0 6px 16px rgba(20,20,20,.10);
  margin:0 auto; }
.swatch-name { text-align:center; font-size:12px; font-weight:500;
  color:#3A3630; margin-top:8px; }
.chip { height:52px; border-radius:12px;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,.05); }
.chip-name { font-size:11px; color:#6E6A63; margin-top:5px; font-weight:500; }

.badge { position:absolute; top:8px; right:8px; width:30px; height:30px;
  border-radius:50%; display:flex; align-items:center; justify-content:center;
  font-size:15px; font-weight:700; color:#fff;
  box-shadow:0 3px 8px rgba(0,0,0,.22); z-index:2; }
.badge.ok { background:#1E8A4C; } .badge.no { background:#C63A2F; }
.pframe { position:relative; border-radius:16px; overflow:hidden;
  box-shadow:0 8px 22px rgba(20,20,20,.10); }
.pname { text-align:center; font-size:12px; font-weight:500; color:#3A3630;
  margin:7px 0 14px 0; }

.tip { display:flex; align-items:center; gap:10px; padding:12px 14px;
  border-radius:14px; background:#FAF9F7; border:1px solid #F0EEE9;
  font-size:13px; font-weight:500; color:#33302B; margin-bottom:10px; }
.tip .ic { font-size:16px; }
.tip.no { background:#FDF6F5; border-color:#F6E4E1; }

.combo { border:1px solid #ECEAE5; border-radius:16px; padding:14px;
  text-align:center; }
.combo-bar { display:flex; height:56px; border-radius:12px; overflow:hidden;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,.05); }
.combo-name { font-size:11.5px; color:#6E6A63; margin-top:9px; font-weight:500; }

.metal { display:flex; align-items:center; gap:12px; padding:10px 14px;
  border-radius:14px; border:1px solid #ECEAE5; margin-bottom:9px; }
.metal-dot { width:34px; height:34px; border-radius:50%;
  box-shadow:inset 0 -6px 10px rgba(0,0,0,.18), inset 0 5px 8px rgba(255,255,255,.5); }
.metal-name { font-size:13px; font-weight:500; color:#33302B; flex:1; }
.metal-mark { font-size:15px; font-weight:700; }

div[data-testid="stFileUploader"] section { border-radius:18px;
  border:1.5px dashed #D8D4CC; background:#FBFAF8; }
hr { border-color:#F0EEE9; }
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# render helpers
# ----------------------------------------------------------------------------
def section(label: str, title: str):
    st.markdown(f'<div class="section-label">{label}</div>'
                f'<div class="section-title">{title}</div>',
                unsafe_allow_html=True)


def gauge(left: str, right: str, value: int, grad: str):
    st.markdown(f"""
    <div class="gauge-row">
      <div class="gauge-label">{left}</div>
      <div class="gauge-track" style="background:{grad};">
        <div class="gauge-dot" style="left:{value}%;"></div>
      </div>
      <div class="gauge-label r">{right}</div>
    </div>""", unsafe_allow_html=True)


def swatch_row(items, per_row=8, big=True):
    cls, name_cls = ("swatch", "swatch-name") if big else ("chip", "chip-name")
    for i in range(0, len(items), per_row):
        cols = st.columns(per_row)
        for col, (name, hx) in zip(cols, items[i:i + per_row]):
            with col:
                st.markdown(
                    f'<div class="{cls}" style="background:{hx};"></div>'
                    f'<div class="{name_cls}" style="text-align:center;">{name}</div>',
                    unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _shirt(img_bytes: bytes, hx: str) -> Image.Image:
    img = Image.open(__import__("io").BytesIO(img_bytes))
    img = ImageOps.exif_transpose(img)
    return recolor_shirt(img, hx)


@st.cache_data(show_spinner=False)
def _shirt_ai(img_bytes: bytes, name: str, hx: str, provider: str,
              model: str, key: str) -> Image.Image:
    img = Image.open(__import__("io").BytesIO(img_bytes))
    img = ImageOps.exif_transpose(img)
    return ai_recolor(img, name, hx, provider, key, model)


def shirt_img(img_bytes: bytes, name: str, hx: str) -> Image.Image:
    """Comparison portrait for one colour, using the selected engine."""
    if ai_mode and not st.session_state.get("ai_edit_failed"):
        try:
            return _shirt_ai(img_bytes, name, hx, provider, edit_model,
                             edit_key)
        except Exception as exc:  # auth / quota / safety-block errors
            st.session_state["ai_edit_failed"] = True
            st.warning(f"AI garment edit failed ({type(exc).__name__}) — "
                       "showing local recolours instead.")
    return _shirt(img_bytes, hx)


def portrait_grid(img_bytes: bytes, colors, ok: bool, per_row=4):
    mark, cls = ("✓", "ok") if ok else ("✗", "no")
    for i in range(0, len(colors), per_row):
        cols = st.columns(per_row)
        for col, (name, hx) in zip(cols, colors[i:i + per_row]):
            with col:
                st.markdown(f'<div class="pframe">'
                            f'<div class="badge {cls}">{mark}</div>',
                            unsafe_allow_html=True)
                st.image(shirt_img(img_bytes, name, hx),
                         use_container_width=True)
                st.markdown(f'</div><div class="pname">{name}</div>',
                            unsafe_allow_html=True)


def combo_bar(hexes, name):
    segs = "".join(f'<div style="flex:1;background:{h};"></div>' for h in hexes)
    st.markdown(f'<div class="combo"><div class="combo-bar">{segs}</div>'
                f'<div class="combo-name">{name}</div></div>',
                unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# sidebar
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Settings")
    provider = st.selectbox("AI provider", provider_names(),
                            help="Choose which vision model performs the "
                                 "seasonal analysis. Without a key, a pixel-"
                                 "sampling estimate is used.")
    model = st.selectbox("Model", models_for(provider))
    api_key = st.text_input(f"{provider} API key (optional)", type="password",
                            help="With a key, the selected model performs the "
                                 "seasonal analysis. Without one, a pixel-"
                                 "sampling estimate is used.")
    st.caption("The portrait never leaves your machine unless you provide "
               f"an API key, in which case it is sent to the {provider} API "
               "for analysis only.")
    ai_toggle = st.toggle(
        "AI garment recolour (photoreal)",
        value=False,
        help="Generate every comparison portrait independently with the "
             "provider's image-edit model — identical person, real fabric "
             "folds. Needs an OpenAI or Google key. Slower, and billed "
             "per image (28 edits per analysis).")
    edit_key = resolve_key(provider, api_key or None)
    edit_model = EDIT_MODELS.get(provider, [""])[0]
    ai_mode = ai_toggle and supports_image_edit(provider) and bool(edit_key)
    if ai_toggle and not supports_image_edit(provider):
        st.warning("Claude doesn't offer image editing — switch the provider "
                   "to OpenAI or Google for AI recolours.")
    elif ai_toggle and not edit_key:
        st.warning("Add an API key to enable AI garment recolours.")
    manual = st.selectbox("Override season (optional)",
                          ["Auto-detect"] + list(SEASONS.keys()))

# ----------------------------------------------------------------------------
# header + upload
# ----------------------------------------------------------------------------
st.markdown('<div class="eyebrow">Personal Colour Analysis</div>',
            unsafe_allow_html=True)
st.markdown('<h1 class="board-title">Your Colour Board</h1>',
            unsafe_allow_html=True)
st.caption("Upload a portrait in natural light, facing the camera, "
           "shoulders visible.")

upload = st.file_uploader("Portrait", type=["jpg", "jpeg", "png", "webp"],
                          label_visibility="collapsed")

if not upload:
    st.info("Upload a portrait to generate the board.")
    st.stop()

img_bytes = upload.getvalue()
portrait = ImageOps.exif_transpose(
    Image.open(__import__("io").BytesIO(img_bytes))).convert("RGB")

with st.spinner("Analyzing colouring…"):
    result = analyze(portrait, api_key or None, provider=provider, model=model)

season_name = manual if manual != "Auto-detect" else result["season"]
season = SEASONS[season_name]
accent = season["best"][0][1]

# ----------------------------------------------------------------------------
# Section 1 + 2 — portrait & colour profile
# ----------------------------------------------------------------------------
c1, c2 = st.columns([5, 7], gap="large")
with c1:
    section("Section 01", "Original Portrait")
    st.image(portrait, use_container_width=True)
with c2:
    section("Section 02", "Colour Profile")
    conf = result.get("confidence")
    src_line = f'{season["tagline"]} · {result["source"]}'
    if conf:
        src_line += f' · {conf}% confidence'
    st.markdown(f'<span class="season-chip" style="background:{accent};">'
                f'{season_name.upper()}</span>'
                f'<div style="margin-top:6px;color:#8A857C;font-size:13px;">'
                f'{src_line}</div>',
                unsafe_allow_html=True)
    st.write("")
    gauge("Cool", "Warm", result["warm"],
          "linear-gradient(90deg,#7FA8D9,#E8DFD2,#D98A4B)")
    gauge("Light", "Deep", result["depth"],
          "linear-gradient(90deg,#F2EDE3,#B5A98F,#3A2E24)")
    gauge("Soft", "Bright", result["chroma"],
          "linear-gradient(90deg,#B9B3AB,#C9B27A,#E0662E)")
    gauge("Low", "High", result["contrast"],
          "linear-gradient(90deg,#DDD9D2,#8E8A83,#1B1B1B)")
    m1, m2, m3 = st.columns(3)
    m1.metric("Undertone", result["undertone"].title())
    m2.metric("Hair Depth", str(result["hair_depth"]).title())
    m3.metric("Eyes", str(result["eye_color"]).title())
    st.caption(result["summary"])

st.divider()

# ----------------------------------------------------------------------------
# Section 3 — best neutrals
# ----------------------------------------------------------------------------
section("Section 03", "Best Neutrals")
swatch_row(season["neutrals"], per_row=8)
st.divider()

# ----------------------------------------------------------------------------
# Section 4 / 5 — comparison portraits
# ----------------------------------------------------------------------------
section("Section 04", "Your Best Colours")
st.caption("Identical portrait — only the shirt colour changes.")
portrait_grid(img_bytes, season["best"], ok=True)
st.divider()

section("Section 05", "Colours to Avoid")
portrait_grid(img_bytes, season["avoid"], ok=False)
st.divider()

# ----------------------------------------------------------------------------
# Section 6 — master palette
# ----------------------------------------------------------------------------
section("Section 06", "Master Colour Palette")
groups = list(season["groups"].items())
for i in range(0, len(groups), 3):
    cols = st.columns(3, gap="large")
    for col, (gname, chips) in zip(cols, groups[i:i + 3]):
        with col:
            st.markdown(f"**{gname}**")
            swatch_row(chips, per_row=3, big=False)
st.divider()

# ----------------------------------------------------------------------------
# Section 7 / 8 — clothing & accessories
# ----------------------------------------------------------------------------
CLOTHING = ["Suit", "Blazer", "Shirt", "Polo", "Sweater",
            "Turtleneck", "Jacket", "Coat", "Henley", "T-Shirt"]
ACCESSORIES = ["Watch", "Belt", "Wallet", "Shoes",
               "Tie", "Pocket Square", "Bag", "Sunglasses"]
ICONS = {"Suit": "🤵", "Blazer": "🧥", "Shirt": "👔", "Polo": "👕",
         "Sweater": "🧶", "Turtleneck": "🧣", "Jacket": "🧥", "Coat": "🧥",
         "Henley": "👕", "T-Shirt": "👕", "Watch": "⌚", "Belt": "➰",
         "Wallet": "👝", "Shoes": "👞", "Tie": "👔", "Pocket Square": "🔲",
         "Bag": "💼", "Sunglasses": "🕶️"}

cA, cB = st.columns(2, gap="large")
with cA:
    section("Section 07", "Best Clothing")
    pal = (season["best"] + season["neutrals"])
    for i in range(0, len(CLOTHING), 5):
        cols = st.columns(5)
        for col, item in zip(cols, CLOTHING[i:i + 5]):
            name, hx = pal[(CLOTHING.index(item) * 3) % len(pal)]
            with col:
                st.markdown(
                    f'<div class="combo" style="background:{hx}1A;">'
                    f'<div style="font-size:30px;">{ICONS[item]}</div>'
                    f'<div class="chip" style="background:{hx};height:14px;'
                    f'margin-top:8px;"></div>'
                    f'<div class="combo-name">{item}<br>{name}</div></div>',
                    unsafe_allow_html=True)
with cB:
    section("Section 08", "Accessories")
    leather = [c for c in season["neutrals"] if c[0] not in
               ("Cream", "Ivory", "Pure White", "Porcelain")] or season["neutrals"]
    for i in range(0, len(ACCESSORIES), 4):
        cols = st.columns(4)
        for col, item in zip(cols, ACCESSORIES[i:i + 4]):
            name, hx = leather[(ACCESSORIES.index(item) * 2) % len(leather)]
            with col:
                st.markdown(
                    f'<div class="combo" style="background:{hx}14;">'
                    f'<div style="font-size:30px;">{ICONS[item]}</div>'
                    f'<div class="chip" style="background:{hx};height:14px;'
                    f'margin-top:8px;"></div>'
                    f'<div class="combo-name">{item}<br>{name}</div></div>',
                    unsafe_allow_html=True)
st.divider()

# ----------------------------------------------------------------------------
# Section 9 / 10 — metals & style tips
# ----------------------------------------------------------------------------
cM, cT = st.columns(2, gap="large")
with cM:
    section("Section 09", "Metals")
    for name, hx in season["metals"]["yes"]:
        st.markdown(f'<div class="metal"><div class="metal-dot" '
                    f'style="background:{hx};"></div>'
                    f'<div class="metal-name">{name}</div>'
                    f'<div class="metal-mark" style="color:#1E8A4C;">✓</div></div>',
                    unsafe_allow_html=True)
    for name, hx in season["metals"]["caution"]:
        st.markdown(f'<div class="metal"><div class="metal-dot" '
                    f'style="background:{hx};"></div>'
                    f'<div class="metal-name">{name}</div>'
                    f'<div class="metal-mark" style="color:#C9973F;">△</div></div>',
                    unsafe_allow_html=True)
    for name, hx in season["metals"]["no"]:
        st.markdown(f'<div class="metal" style="opacity:.6;">'
                    f'<div class="metal-dot" style="background:{hx};"></div>'
                    f'<div class="metal-name">{name}</div>'
                    f'<div class="metal-mark" style="color:#C63A2F;">✗</div></div>',
                    unsafe_allow_html=True)
with cT:
    section("Section 10", "Style Tips")
    for t in season["tips_yes"]:
        st.markdown(f'<div class="tip"><span class="ic" '
                    f'style="color:#1E8A4C;">✓</span>{t}</div>',
                    unsafe_allow_html=True)
    for t in season["tips_no"]:
        st.markdown(f'<div class="tip no"><span class="ic" '
                    f'style="color:#C63A2F;">✗</span>{t}</div>',
                    unsafe_allow_html=True)
st.divider()

# ----------------------------------------------------------------------------
# Bonus — glasses & hair
# ----------------------------------------------------------------------------
cG, cH = st.columns(2, gap="large")
with cG:
    section("Bonus", "Glasses & Frames")
    swatch_row(season["glasses"], per_row=4)
with cH:
    section("Bonus", "Hair & Beard Tones")
    swatch_row(season["hair"], per_row=4)
st.divider()

# ----------------------------------------------------------------------------
# Bonus — suit & casual combinations
# ----------------------------------------------------------------------------
from src.palettes import C as COLORS  # noqa: E402

section("Bonus", "Suit · Shirt · Tie")
cols = st.columns(4, gap="medium")
for col, (suit, shirt, tie) in zip(cols, season["suit_combos"]):
    with col:
        combo_bar([COLORS[suit], COLORS[shirt], COLORS[tie]],
                  f"{suit} + {shirt} + {tie}")
st.write("")

section("Bonus", "Casual Combinations")
cols = st.columns(4, gap="medium")
for col, (c1n, top, c2n, bottom) in zip(cols, season["casual"]):
    with col:
        combo_bar([COLORS[c1n], COLORS[c2n]],
                  f"{c1n} {top} + {c2n} {bottom}")
st.divider()

# ----------------------------------------------------------------------------
# Bonus — shopping palette + exports
# ----------------------------------------------------------------------------
section("Bonus", "Shopping Palette")
seen, shopping = set(), []
for group in ([season["neutrals"], season["best"]] +
              list(season["groups"].values())):
    for name, hx in group:
        if name not in seen:
            seen.add(name)
            shopping.append((name, hx))
shopping = shopping[:48]
swatch_row(shopping, per_row=8, big=False)

st.write("")
d1, d2, _ = st.columns([2, 2, 5])
with d1:
    st.download_button(
        "Download palette PNG",
        data=palette_sheet(season_name, shopping),
        file_name=f"{season_name.lower().replace(' ', '-')}-palette.png",
        mime="image/png", use_container_width=True)
with d2:
    st.download_button(
        "Download palette JSON",
        data=json.dumps({"season": season_name,
                         "profile": {k: result[k] for k in
                                     ("warm", "depth", "chroma", "contrast",
                                      "undertone")},
                         "swatches": [{"name": n, "hex": h}
                                      for n, h in shopping]}, indent=2),
        file_name=f"{season_name.lower().replace(' ', '-')}-palette.json",
        mime="application/json", use_container_width=True)

st.divider()

# ----------------------------------------------------------------------------
# Bonus — full board image (one shareable PNG)
# ----------------------------------------------------------------------------
section("Bonus", "Full Board Image")
st.caption("The complete analysis composed into a single shareable image — "
           "portrait, profile, comparison grids, palette, clothing, metals "
           "and style guide.")


@st.cache_data(show_spinner=False)
def _board_png(img_bytes: bytes, season_name: str, result: dict,
               engine: tuple) -> bytes:
    portrait = ImageOps.exif_transpose(
        Image.open(__import__("io").BytesIO(img_bytes))).convert("RGB")
    season = SEASONS[season_name]
    best = [(n, hx, shirt_img(img_bytes, n, hx)) for n, hx in season["best"]]
    avoid = [(n, hx, shirt_img(img_bytes, n, hx)) for n, hx in season["avoid"]]
    return render_board(portrait, season_name, season, result, best, avoid)


_ai_live = ai_mode and not st.session_state.get("ai_edit_failed")
engine_sig = (_ai_live, provider if _ai_live else "", edit_model if _ai_live else "")
with st.spinner("Composing board image…"):
    board_png = _board_png(img_bytes, season_name, result, engine_sig)
st.image(board_png, use_container_width=True)
st.download_button(
    "Download board PNG",
    data=board_png,
    file_name=f"{season_name.lower().replace(' ', '-')}-board.png",
    mime="image/png")

st.caption("Colour analysis is styling guidance, not a scientific measurement. "
           "Lighting and camera white balance affect results.")
