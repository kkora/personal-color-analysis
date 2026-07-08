"""Portrait colour analysis.

Two paths:
  1. Vision model (if an API key is available) — accurate seasonal analysis of
     undertone, hair depth, eye colour, contrast, chroma, value. Supported
     providers: Anthropic (Claude), OpenAI (GPT), Google (Gemini) — see
     PROVIDERS below.
  2. Offline heuristic (no key) — pixel sampling estimate from src.imaging.

Both return the same dict shape consumed by app.py:
  { season, warm, depth, chroma, contrast, undertone, hair_depth,
    eye_color, summary, source }
"""

from __future__ import annotations

import base64
import io
import json
import os

from PIL import Image

from src.imaging import heuristic_analysis
from src.palettes import SEASON_NAMES, classify

# ----------------------------------------------------------------------------
# provider config
# ----------------------------------------------------------------------------
# Each provider lists its API-key environment variable and the vision-capable
# models offered in the UI. The first model in each list is the default.
PROVIDERS = {
    "Anthropic (Claude)": {
        "env": "ANTHROPIC_API_KEY",
        "models": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"],
        "label": "Claude vision",
    },
    "OpenAI (GPT)": {
        "env": "OPENAI_API_KEY",
        "models": ["gpt-5.5", "gpt-5.4-mini", "gpt-4o"],
        "label": "OpenAI vision",
    },
    "Google (Gemini)": {
        "env": "GOOGLE_API_KEY",
        "models": ["gemini-2.5-pro", "gemini-2.5-flash"],
        "label": "Gemini vision",
    },
}

DEFAULT_PROVIDER = "Anthropic (Claude)"


def provider_names() -> list[str]:
    return list(PROVIDERS.keys())


def models_for(provider: str) -> list[str]:
    return PROVIDERS[provider]["models"]


def default_model(provider: str) -> str:
    return PROVIDERS[provider]["models"][0]


_PROMPT = f"""You are a professional personal colour analyst.
Analyze the person in this portrait and respond with ONLY a JSON object
(no markdown fences, no preamble) with exactly these keys:

  "undertone": "warm" | "cool" | "neutral-warm" | "neutral-cool"
  "hair_depth": "light" | "medium" | "deep"
  "eye_color": short description, e.g. "dark brown"
  "warm": 0-100      (0 = very cool, 100 = very warm)
  "depth": 0-100     (0 = very light colouring, 100 = very deep)
  "chroma": 0-100    (0 = very soft/muted, 100 = very bright/clear)
  "contrast": 0-100  (0 = low contrast between features, 100 = very high)
  "season": one of {SEASON_NAMES}
  "summary": one sentence, max 18 words, describing why this season fits.

Base everything strictly on the visible skin undertone, hair, eyes, and the
contrast between them. Pick the single closest season."""


def _img_to_bytes(img: Image.Image) -> tuple[bytes, str]:
    img = img.convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"


def _img_to_b64(img: Image.Image) -> tuple[str, str]:
    raw, media_type = _img_to_bytes(img)
    return base64.standard_b64encode(raw).decode(), media_type


def _parse(text: str, source: str) -> dict:
    """Turn a model's raw JSON reply into the app's result dict."""
    text = text.replace("```json", "").replace("```", "").strip()
    out = json.loads(text)

    if out.get("season") not in SEASON_NAMES:
        out["season"] = classify(out.get("warm", 50),
                                 out.get("depth", 50),
                                 out.get("chroma", 50))
    out["source"] = source
    return out


def analyze_with_claude(img: Image.Image, api_key: str,
                        model: str = "claude-sonnet-4-6") -> dict:
    import anthropic  # imported lazily so the app runs without the SDK

    data, media_type = _img_to_b64(img)
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type,
                            "data": data}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    return _parse(text, "Claude vision")


def analyze_with_openai(img: Image.Image, api_key: str,
                        model: str = "gpt-5.5") -> dict:
    from openai import OpenAI  # imported lazily so the app runs without the SDK

    data, media_type = _img_to_b64(img)
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        max_completion_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:{media_type};base64,{data}"}},
            ],
        }],
    )
    return _parse(resp.choices[0].message.content, "OpenAI vision")


def analyze_with_google(img: Image.Image, api_key: str,
                        model: str = "gemini-2.5-pro") -> dict:
    from google import genai  # imported lazily so the app runs without the SDK
    from google.genai import types

    raw, media_type = _img_to_bytes(img)
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=raw, mime_type=media_type),
            _PROMPT,
        ],
    )
    return _parse(resp.text, "Gemini vision")


_DISPATCH = {
    "Anthropic (Claude)": analyze_with_claude,
    "OpenAI (GPT)": analyze_with_openai,
    "Google (Gemini)": analyze_with_google,
}


def analyze_offline(img: Image.Image) -> dict:
    h = heuristic_analysis(img)
    season = classify(h["warm"], h["depth"], h["chroma"])
    undertone = ("warm" if h["warm"] >= 62 else
                 "cool" if h["warm"] <= 38 else
                 "neutral-warm" if h["warm"] > 50 else "neutral-cool")
    return dict(
        season=season, warm=h["warm"], depth=h["depth"],
        chroma=h["chroma"], contrast=h["contrast"],
        undertone=undertone, hair_depth=h["hair_depth"],
        eye_color=h["eye_color"],
        summary="Estimated from pixel sampling — add an API key for a "
                "professional-grade analysis.",
        source="Offline heuristic",
    )


def analyze(img: Image.Image, api_key: str | None = None,
            provider: str = DEFAULT_PROVIDER,
            model: str | None = None) -> dict:
    """Analyze a portrait with the chosen provider, falling back to offline.

    ``api_key`` overrides the provider's environment variable. ``model``
    overrides the provider's default model.
    """
    cfg = PROVIDERS.get(provider, PROVIDERS[DEFAULT_PROVIDER])
    key = api_key or os.environ.get(cfg["env"], "")
    if key:
        fn = _DISPATCH[provider]
        try:
            if model:
                return fn(img, key, model)
            return fn(img, key)
        except Exception as exc:  # network / auth / parse errors
            out = analyze_offline(img)
            out["summary"] = f"API analysis failed ({type(exc).__name__}); " \
                             f"showing offline estimate."
            return out
    return analyze_offline(img)
