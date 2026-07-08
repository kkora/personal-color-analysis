# Personal Colour Analysis Board

A diagram-first, luxury-consultant style personal colour analysis app built with Streamlit. Upload a portrait and get a complete visual colour board: seasonal classification, axis gauges, best/avoid comparison portraits (identical photo, only the shirt colour changes), master palette, metals, style tips, outfit combinations, and a downloadable shopping palette.

![Streamlit](https://img.shields.io/badge/Streamlit-app-FF4B4B) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB) ![License](https://img.shields.io/badge/License-MIT-green)

## What it produces

| Section | Content |
|---|---|
| 01 · Portrait | Original photo, untouched |
| 02 · Colour Profile | Warm↔Cool, Deep↔Light, Soft↔Bright, Contrast gauges + detected season |
| 03 · Best Neutrals | 8 wardrobe neutrals as large swatches |
| 04 · Best Colours | 16 comparison portraits with ✓ badges — same photo, recoloured shirt |
| 05 · Avoid Colours | 12 comparison portraits with ✗ badges |
| 06 · Master Palette | Grouped chips: Neutrals, Blues, Greens, Earth, Reds, Accents |
| 07 · Clothing | Suit, blazer, polo, sweater… in recommended colours |
| 08 · Accessories | Watch, belt, shoes, bag… matched to the palette |
| 09 · Metals | ✓ / △ / ✗ metal recommendations |
| 10 · Style Tips | Icon-led do / don't guidance |
| Bonus | Glasses & hair tones, suit+shirt+tie combos, casual outfits, 48-swatch shopping palette (PNG + JSON export) |

All 12 classic colour seasons are fully specified in [`src/palettes.py`](src/palettes.py).

## How the analysis works

Two engines, same output shape:

1. **Vision model** (recommended) — pick a provider and model in the sidebar and supply the matching API key. The model analyzes undertone, hair depth, eye colour, contrast, chroma and value from the portrait and picks the closest season. Supported providers:

   | Provider | Env var | Models |
   |---|---|---|
   | Anthropic (Claude) | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5` |
   | OpenAI (GPT) | `OPENAI_API_KEY` | `gpt-5.5`, `gpt-5.4-mini`, `gpt-4o` |
   | Google (Gemini) | `GOOGLE_API_KEY` | `gemini-2.5-pro`, `gemini-2.5-flash` |

2. **Offline heuristic** (no key needed) — pixel sampling of the face and hair regions estimates the four axes and maps them to the nearest season. Approximate, but fully local.

You can also override the detected season manually from the sidebar.

The shirt recolouring is luminance-preserving: a feathered mask over the clothing region re-hues the fabric to each target colour while keeping folds and shading, so every comparison portrait is pixel-identical except for shirt colour.

## Quick start

```bash
git clone https://github.com/<you>/personal-color-analysis.git
cd personal-color-analysis
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Optional — enable vision analysis by exporting the key for your chosen provider:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # Anthropic (Claude)
export OPENAI_API_KEY=sk-...          # OpenAI (GPT)
export GOOGLE_API_KEY=...             # Google (Gemini)
streamlit run app.py
```

or paste the key into the sidebar at runtime (it is never stored).

## Project structure

```
app.py                  Streamlit UI — the full board
src/palettes.py         Master colour library + 12 season definitions
src/analysis.py         Multi-provider vision analysis (Claude/GPT/Gemini) + offline fallback
src/imaging.py          Shirt recolouring, face sampling, palette PNG export
.streamlit/config.toml  Light editorial theme
```

## Deploy

Works out of the box on [Streamlit Community Cloud](https://streamlit.io/cloud): point it at `app.py`, and add the API key for your chosen provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GOOGLE_API_KEY`) under app secrets if you want vision analysis.

## Notes & limitations

- Colour analysis is styling guidance, not a scientific measurement — lighting and camera white balance strongly affect results.
- The offline heuristic assumes a roughly centred, front-facing portrait with the face in the upper-middle of the frame.
- Portraits are processed in memory only. With an API key, the image is sent to the selected provider's API for analysis; otherwise it never leaves your machine.

## License

MIT
