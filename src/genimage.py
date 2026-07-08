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
