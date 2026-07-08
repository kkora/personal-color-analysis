"""Portrait colour analysis.

Two paths:
  1. Claude vision (if an Anthropic API key is available) — accurate seasonal
     analysis of undertone, hair depth, eye colour, contrast, chroma, value.
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


def _img_to_b64(img: Image.Image) -> tuple[str, str]:
    img = img.convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


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
    text = text.replace("```json", "").replace("```", "").strip()
    out = json.loads(text)

    if out.get("season") not in SEASON_NAMES:
        out["season"] = classify(out.get("warm", 50),
                                 out.get("depth", 50),
                                 out.get("chroma", 50))
    out["source"] = "Claude vision"
    return out


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


def analyze(img: Image.Image, api_key: str | None = None) -> dict:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        try:
            return analyze_with_claude(img, key)
        except Exception as exc:  # network / auth / parse errors
            out = analyze_offline(img)
            out["summary"] = f"API analysis failed ({type(exc).__name__}); " \
                             f"showing offline estimate."
            return out
    return analyze_offline(img)
