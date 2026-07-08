"""AI garment recolouring — photoreal comparison portraits.

Generates each comparison portrait independently with an image-editing model
(one API call per colour), following the professional retouching brief below:
only the garment changes, the person and scene stay pixel-identical. The app
assembles the results itself (grids + the board PNG), which gives far more
consistent output than asking a model to compose the whole board in one image.

Supported: OpenAI (gpt-image-1) and Google (Gemini image). Anthropic models
do not generate images, so the app falls back to the local luminance-
preserving recolour for that provider.
"""

from __future__ import annotations

import base64
import io
import os

from PIL import Image

# ----------------------------------------------------------------------------
# the retouching brief sent with every edit
# ----------------------------------------------------------------------------
GARMENT_EDIT_PROMPT = """You are a professional photo retoucher. This is a
precise IMAGE EDITING task on the supplied photograph — not a redesign.

TASK: Recolour ONLY the garment worn on the torso (shirt / polo / sweater /
jacket / blazer / coat / t-shirt) to {name} ({hex}). The result must look
like the person actually owns and is wearing clothing of that colour.

IDENTITY PRESERVATION — these must remain identical to the original:
face, eyes, nose, lips, jawline, hair (style, volume, texture), facial hair,
skin tone, skin texture, expression, hands, body proportions, pose, camera
angle, perspective, background, lighting, shadows, white balance, image
sharpness, and crop. The person must remain instantly recognizable. Never
beautify, stylize, age, or de-age.

GARMENT REALISM — recreate only the garment in the new colour, preserving
its wrinkles, seams, stitching, fabric texture, folds, shadows, and
highlights so the clothing looks naturally worn.

NEVER: tint the entire image, overlay a transparent colour, recolour the
skin, hair, background, or furniture, apply a global filter, colour wash,
or gradient overlay, or change the exposure.

Output the edited photograph only."""

# ----------------------------------------------------------------------------
# v3 — one-shot luxury editorial board (whole infographic in one generation)
# ----------------------------------------------------------------------------
BOARD_PROMPT_V3 = """LUXURY PERSONAL COLOUR ANALYSIS BOARD — Version 3.0
Editorial / Fashion Consultant Edition

You are simultaneously: a certified Personal Colour Analyst, a professional
Fashion Stylist, an award-winning Editorial Graphic Designer, an Apple Human
Interface designer, a luxury magazine art director, and a professional
fashion photographer.

Your task is to create ONE premium infographic that looks like it belongs in
a luxury fashion consultation book. The final result should resemble work
from House of Colour, Color Me Beautiful, Vogue Style Guide, GQ Editorial,
Apple Product Marketing, and high-end fashion consultation agencies.

The design quality is MORE IMPORTANT than the amount of information. The
page should feel clean, premium, modern and luxurious. DO NOT create a
software dashboard. DO NOT create a report. DO NOT create a spreadsheet.
Create a beautiful editorial infographic.

LAYOUT STYLE
Large cards. Large margins. Rounded corners. Soft shadows. Thin borders.
Elegant typography. Minimal text. Large visuals. Editorial spacing. White
background. Premium appearance. Every section should feel like a magazine
layout. Avoid clutter. Avoid tiny elements.

PHOTO RULES
Use ONLY the uploaded portrait. The person's identity MUST remain identical.
Never change: face, eyes, nose, lips, jaw, hair, hairstyle, expression,
pose, body, hands, camera angle, lighting, shadows, background. Only
clothing colours may change. Do NOT tint the image. Do NOT overlay colours.
Replace the actual clothing naturally: wrinkles, fabric, texture, buttons,
collar, stitching, shadows must remain realistic.

PAGE STRUCTURE
Approximately 40% beautiful photography, 40% colour palettes, 20% icons and
labels. Very little text. Maximum 2-3 words per label.

SECTION 1 — ORIGINAL PORTRAIT
Large portrait. Luxury portrait framing. Rounded image. Soft shadow.

SECTION 2 — COLOUR PROFILE
Modern circular gauges: Warm-Cool, Deep-Light, Soft-Bright, Contrast.
Display the detected season (e.g. DEEP AUTUMN) and its key features
(undertone, value, chroma, contrast).

SECTION 3 — BEST NEUTRALS
Beautiful large circular swatches.

SECTION 4 — BEST COLOURS (visually dominant)
Generate 12-16 identical portraits: same face, same crop, same pose, same
lighting, same background — ONLY the clothing changes, one recommended
colour each. Place a small green circular check icon on each. Do NOT use
thick borders. Do NOT use large icons.

SECTION 5 — AVOID COLOURS
Generate 10-12 identical portraits, only clothing changes, one avoid colour
each, with a small red circular X icon.

SECTION 6 — MASTER PALETTE
Beautiful grouped colour swatches: Neutrals, Blues, Greens, Earth, Burgundy,
Accent. Perfect spacing. Perfect alignment.

SECTION 7 — BEST CLOTHING
Instead of product-catalog images, render elegant floating clothing in
recommended colours: suit, blazer, dress shirt, polo, crew neck, sweater,
leather jacket, overcoat. Soft shadows. Premium studio lighting.

SECTION 8 — ACCESSORIES
Elegant product photography: watch, leather belt, wallet, shoes, tie, bag.
Brown leather. Dark leather. Premium materials.

SECTION 9 — METALS
Minimal icons. Recommended / optional / avoid metal finishes.

SECTION 10 — STYLE GUIDE
Simple icon row of do / don't labels, maximum 3 words each.

TYPOGRAPHY
Luxury editorial typography. Large titles. Small captions. No paragraphs.
No explanations.

VISUAL PRIORITY
Photography first. Colour second. Text third. Clean enough to print.

NEGATIVE PROMPT — Do NOT: create a dashboard, create charts with excessive
labels, create spreadsheets, use bright gradients, tint entire images,
recolour the background, recolour skin, recolour hair, distort clothing,
crop faces differently, change facial expression, generate different
people, or make the portraits inconsistent.

FINAL GOAL
Create ONE luxury fashion consultation board that could be sold as a
premium personal colour analysis report — a professionally designed
editorial infographic rather than an AI-generated collage, suitable for
commercial printing, portfolio presentation, or a paid styling
consultation. Portrait orientation, print quality."""


# ----------------------------------------------------------------------------
# v4 — universal one-shot board (person-adaptive, dynamic seasonal colours)
# ----------------------------------------------------------------------------
BOARD_PROMPT_V4 = """AI PERSONAL COLOUR ANALYSIS — Universal Prompt, Version 4.0

You are an internationally recognized Personal Colour Analyst, Fashion
Consultant, Professional Photo Editor, and Editorial Graphic Designer.

Your job is to analyze ANY uploaded portrait and create a premium,
magazine-quality personal colour analysis board. The design should resemble
a luxury fashion consultation rather than an AI report. Never assume the
person's gender, age, ethnicity, clothing style, or colour season —
everything must be determined from the uploaded portrait.

INPUT
The user uploads ONE portrait. Automatically analyze: gender presentation
(only if useful for styling), estimated age group, face shape, hair colour,
hair depth, hair texture, eye colour, skin tone, skin undertone, skin
depth, contrast level, colour chroma, and overall colour harmony. Do not
guess randomly — use the uploaded portrait only.

IDENTITY PRESERVATION
The person's identity MUST remain unchanged. Never modify: face, eyes,
nose, lips, jaw, hair, hairstyle, hair texture, facial hair, expression,
skin tone, skin texture, body proportions, hands, pose, camera angle,
perspective, background, lighting, shadows. The subject must remain
instantly recognizable.

ALLOWED CHANGES
Only modify clothing and accessories for styling comparisons. Preserve
realistic fabric texture, folds, seams, stitching, buttons, wrinkles,
reflections, and shadows. Never tint the entire image, overlay transparent
colours, recolour skin, hair, or the background, or apply global filters.

STEP 1 — DETERMINE PERSONAL COLOUR SEASON
Automatically determine the best matching seasonal palette from the 12
classic seasons (Light/True/Bright Spring, Light/Soft/Cool Summer,
Soft/True/Deep Autumn, Deep/Cool/Bright Winter). Provide confidence
internally and use the best matching palette.

STEP 2 — BUILD COLOUR PROFILE
Modern visual indicators for Warm-Cool, Light-Deep, Soft-Bright, and
Low-High Contrast. Display season, undertone, contrast, depth, chroma.
Minimal text.

STEP 3 — BEST NEUTRAL COLOURS
Generate neutrals dynamically (e.g. Navy, Charcoal, Espresso, Chocolate,
Stone, Camel, Taupe, Cream, Ivory, Warm Grey, Cool Grey) — choose only
colours appropriate for the detected season.

STEP 4 — BEST COLOUR COMPARISON
Generate 12-16 comparison portraits: same face, expression, crop, pose,
lighting, and background — only the clothing changes. Select colours
dynamically for the detected season (e.g. Deep Autumn: Forest Green, Rust,
Olive, Chocolate, Camel, Deep Teal, Mustard, Burgundy · Soft Summer: Dusty
Rose, Slate Blue, Soft Navy, Lavender, Muted Teal, Mauve, Soft Plum, Cool
Taupe · Bright Spring: Coral, Turquoise, Bright Navy, Emerald, Golden
Yellow, Bright Peach, Aqua, Warm Green). Use small green check icons.

STEP 5 — COLOURS TO AVOID
Generate 10-12 comparison portraits, same person / crop / lighting, only
clothing changes. Choose poor matches for the detected season (e.g. Deep
Autumn: pastels, neon pink, icy blue, pure white, cool grey, bright purple
· Soft Summer: bright orange, neon green, golden yellow, black, electric
blue · Bright Winter: olive, muted brown, dusty beige, mustard, warm
camel). Use small red X icons.

STEP 6 — MASTER COLOUR PALETTE
Grouped swatches; groups depend on the detected season (Neutrals, Accent
Colours, Blues, Greens, Reds, Purples, Earth Tones…). Every season gets a
different palette.

STEP 7 — BEST CLOTHING
Generate clothing suited to the uploaded portrait. Business attire → suit,
blazer, dress shirt, tie. Casual → t-shirt, sweater, jacket, polo.
Feminine presentation → blouse, dress, cardigan, blazer, skirt. Masculine
presentation → suit, blazer, henley, polo, sweater. Do not force business
clothing — choose naturally.

STEP 8 — ACCESSORIES
Recommend accessories matching the detected palette (watch, belt, shoes,
wallet, bag, scarf, jewelry, tie, eyewear) — only items appropriate for
the uploaded portrait.

STEP 9 — BEST METALS
Recommend metals dynamically (gold, rose gold, silver, platinum, bronze,
brass, gunmetal, white gold) — choose those that harmonize with the
detected undertone.

STEP 10 — STYLE GUIDE
Simple icon recommendations (e.g. ✓ Tonal Dressing, ✓ Earth Tones,
✓ Rich Contrast, ✓ Soft Contrast, ✓ Matte Texture, ✓ Bold Colours) —
only those appropriate for the detected season.

DESIGN STYLE
Apple-inspired, luxury editorial, fashion magazine, minimal, premium.
Large white space, rounded cards, soft shadows, elegant typography,
magazine layout. Avoid dashboard or spreadsheet appearance and excessive
text. Photography roughly 40-50% of the page, colour palettes ~30%, icons
and labels ~20%.

OUTPUT
Generate ONE premium infographic containing: original portrait, colour
profile, seasonal analysis, best neutrals, best-colour comparison
portraits, avoid-colour comparison portraits, dynamic seasonal palette,
recommended clothing, recommended accessories, recommended metals, and a
quick styling guide. The result should look like a premium personal colour
consultation delivered by a professional fashion consultant. Every
recommendation must be based entirely on the uploaded portrait."""

# registry of board-prompt versions shown in the UI (newest first — the
# first entry is the default selection)
BOARD_PROMPTS = {
    "v4.0 — Universal (latest)": BOARD_PROMPT_V4,
    "v3.0 — Editorial / Fashion Consultant": BOARD_PROMPT_V3,
}
DEFAULT_BOARD_PROMPT = next(iter(BOARD_PROMPTS))


def _season_context(season_name: str, season: dict, result: dict) -> str:
    """Analysis block appended to the v3 prompt so the board uses the
    already-detected season instead of re-guessing it."""
    names = lambda key: ", ".join(n for n, _ in season[key])  # noqa: E731
    return f"""

ANALYSIS CONTEXT — already performed on this portrait; use these results.
Season: {season_name}
Undertone: {result['undertone']} · Warm {result['warm']}/100 ·
Depth {result['depth']}/100 · Chroma {result['chroma']}/100 ·
Contrast {result['contrast']}/100
Best neutrals: {names('neutrals')}
Best colours: {names('best')}
Avoid colours: {names('avoid')}"""


# image-editing models per provider (first entry is the default)
EDIT_MODELS = {
    "OpenAI (GPT)": ["gpt-image-1"],
    "Google (Gemini)": ["gemini-2.5-flash-image"],
}

_ENV = {"OpenAI (GPT)": "OPENAI_API_KEY", "Google (Gemini)": "GOOGLE_API_KEY"}


def supports_image_edit(provider: str) -> bool:
    return provider in EDIT_MODELS


def resolve_key(provider: str, api_key: str | None) -> str:
    return api_key or os.environ.get(_ENV.get(provider, ""), "")


def _prep(img: Image.Image, fmt: str) -> io.BytesIO:
    img = img.convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format=fmt, quality=92)
    buf.name = f"portrait.{fmt.lower()}"
    buf.seek(0)
    return buf


def edit_with_openai(img: Image.Image, name: str, hx: str, api_key: str,
                     model: str = "gpt-image-1") -> Image.Image:
    from openai import OpenAI  # lazy import, keeps the app runnable without it

    client = OpenAI(api_key=api_key)
    result = client.images.edit(
        model=model,
        image=_prep(img, "PNG"),
        prompt=GARMENT_EDIT_PROMPT.format(name=name, hex=hx),
        size="auto",
    )
    return Image.open(io.BytesIO(base64.b64decode(result.data[0].b64_json)))


def edit_with_google(img: Image.Image, name: str, hx: str, api_key: str,
                     model: str = "gemini-2.5-flash-image") -> Image.Image:
    from google import genai  # lazy import, keeps the app runnable without it
    from google.genai import types

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=_prep(img, "JPEG").getvalue(),
                                  mime_type="image/jpeg"),
            GARMENT_EDIT_PROMPT.format(name=name, hex=hx),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"]),
    )
    for part in resp.candidates[0].content.parts:
        if getattr(part, "inline_data", None) and part.inline_data.data:
            return Image.open(io.BytesIO(part.inline_data.data))
    raise RuntimeError("Gemini returned no image")


_EDIT_DISPATCH = {
    "OpenAI (GPT)": edit_with_openai,
    "Google (Gemini)": edit_with_google,
}


def ai_recolor(img: Image.Image, name: str, hx: str, provider: str,
               api_key: str, model: str | None = None,
               max_size: int = 420) -> Image.Image:
    """One independent garment edit; returns a thumbnail-sized portrait."""
    fn = _EDIT_DISPATCH[provider]
    out = fn(img, name, hx, api_key, model or EDIT_MODELS[provider][0])
    out = out.convert("RGB")
    out.thumbnail((max_size, max_size), Image.LANCZOS)
    return out


def generate_board_ai(img: Image.Image, season_name: str, season: dict,
                      result: dict, provider: str, api_key: str,
                      model: str | None = None,
                      prompt_version: str = DEFAULT_BOARD_PROMPT) -> Image.Image:
    """One-shot editorial board: the model composes the whole infographic
    from the portrait in a single generation, using the selected prompt
    version from BOARD_PROMPTS."""
    base = BOARD_PROMPTS.get(prompt_version, BOARD_PROMPTS[DEFAULT_BOARD_PROMPT])
    prompt = base + _season_context(season_name, season, result)
    model = model or EDIT_MODELS[provider][0]

    if provider == "OpenAI (GPT)":
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        result_ = client.images.edit(
            model=model,
            image=_prep(img, "PNG"),
            prompt=prompt,
            size="1024x1536",   # portrait orientation, per the brief
            quality="high",
        )
        return Image.open(io.BytesIO(base64.b64decode(result_.data[0].b64_json)))

    if provider == "Google (Gemini)":
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=_prep(img, "JPEG").getvalue(),
                                      mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"]),
        )
        for part in resp.candidates[0].content.parts:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return Image.open(io.BytesIO(part.inline_data.data))
        raise RuntimeError("Gemini returned no image")

    raise ValueError(f"{provider} does not support image generation")
