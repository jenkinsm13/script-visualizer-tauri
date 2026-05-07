"""LLM-driven shot-to-prompt generation via Ollama.

A shot list says things like "CU ON FORD EMBLEM ON BACK HATCH" or
"WIDE OF BRONCO BACKING OUT". Those are *production* directives — they
describe what the camera does, not what the resulting still image
contains. An image-gen model needs the latter.

This module asks a local LLM (default nemotron3:33b) to translate a
shot's description + scene context into a prompt that describes the
*frame* — subject, composition, lighting, mood — without camera-action
language.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx


OLLAMA_URL = os.environ.get("OLLAMA_API_BASE", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get(
    "SV_PROMPT_MODEL", os.environ.get("OLLAMA_MODEL_PROMPT", "nemotron3:33b")
)
DEFAULT_NUM_PREDICT = int(os.environ.get("SV_PROMPT_NUM_PREDICT", "4096"))
# Reasoning models (nemotron, qwen-reasoner, etc.) burn many tokens on
# internal reasoning before emitting visible output. 512 is often not
# enough for them to even reach the final answer; 4096 is comfortable.
DEFAULT_NUM_CTX = int(os.environ.get("SV_PROMPT_NUM_CTX", "8192"))
REQUEST_TIMEOUT = float(os.environ.get("SV_PROMPT_TIMEOUT", "180"))


# The system prompt is the load-bearing part of this whole feature. It
# must steer the model toward static-frame description without losing
# the cinematographic intent of the shot. Tuned for short, declarative
# image-gen prompts (Flux / SD / DALL-E style) — not paragraphs.
SYSTEM_PROMPT = """You are a cinematic concept artist translating a film
shot into a single still-frame image-generation prompt.

A shot description uses production language — camera moves, framing
calls, abbreviations like CU/MS/WS, directorial intent. An image
generator can't render a "dolly in" or "tracking shot"; it renders ONE
frozen frame. Your job is to turn the shot description into a description
of THAT frozen frame.

Rules:
1. Output ONE prompt as a single line of comma-separated phrases. No
   preamble, no commentary, no quotes, no markdown — just the prompt.

2. Lead with the subject (what's most prominent in frame), then composition
   (close-up / medium shot / wide shot / over-the-shoulder), then setting,
   then lighting/mood, then technical modifiers (lens, film stock, grain).

3. Translate framing abbreviations: CU → close-up, MS → medium shot,
   WS → wide shot, ECU → extreme close-up. Drop camera-MOVE language
   entirely (no "dolly in", "pan", "tracking shot"). The result is one
   static frame.

4. **NEVER quote brand or product names as if they're text on the object.**
   Modern image models render quoted nouns as literal text. Instead,
   describe the VISUAL appearance of the logo/badge/emblem.

   ❌ BAD:  "FORD EMBLEM close-up on tailgate"
            (renders "FORD EMBLEM" as text on the car)
   ✅ GOOD: "close-up of the chrome script Ford badge centered on the
            tailgate of a [vehicle from glossary]"

   ❌ BAD:  "Coca-Cola can on the table"  (renders the actual logo wrong)
   ✅ GOOD: "close-up of a red soda can with white script logo, on a table"

5. **Pick ONE environment.** A shot is in EITHER an interior OR an
   exterior, never both. The slugline INT./EXT. is a HINT — it tells you
   which physical location the production crew was at — but the SHOT
   DESCRIPTION's visual cues are authoritative. Treat exterior cues as
   overriding the slugline:

   Words that signal **EXTERIOR** of a vehicle (regardless of slugline):
     hood, grille, bumper, fender, panel, headlights, taillights,
     license plate, tire(s), wheel(s), back hatch, tailgate, door
     (when described from outside, e.g. "side of the door"), emblem,
     badge, paint, dust, mud on the body.

   Words that signal **INTERIOR** of a vehicle:
     dashboard, steering wheel, seat, seatbelt, mirror, rear-view,
     windshield (from inside), passenger, driver, gear stick, console,
     headliner.

   If the shot says "CU on emblem on back hatch", that's exterior even
   if the slugline is INT. — the badge lives on the outside surface.

   Don't combine "interior of [vehicle]" + "inside [building]". That's
   nonsense — pick one based on the shot.

6. **If a glossary is provided, its specs are MANDATORY.** Copy year,
   color, generation, and other identifiers verbatim. Do NOT invent
   alternative years (no "1969 White") or alternative colors when the
   glossary already pins them. Only describe traits the glossary or
   shot description specifies.

7. **Preserve character names** as in the shot (ELIZA, STEPH). For
   vehicles/products, replace the all-caps shorthand with the
   glossary's full description on first mention; afterwards a short
   reference is fine.

8. Use the scene heading (INT./EXT., location, time of day) to set
   environment and lighting. EXT. ... MORNING → "soft golden morning
   sunlight, long shadows". INT. ... NIGHT → "low warm practical
   lighting, deep shadows".

9. Don't invent age, appearance, mood, or weather not in the shot
   description, scene heading, or glossary.

10. Keep total length under ~60 words. Long prompts perform worse.

11. Do NOT add quality-booster cliches ("8k resolution", "trending on
    artstation", "highly detailed") — the style preset adds those.

EXAMPLE:

  Scene heading: INT. BRONCO / SUBURBAN HOUSE - MORNING — shot 1
  Shot description: CU ON FORD EMBLUM ON BACK HATCH
  Glossary: BRONCO = 6th-gen Ford Bronco SUV, red, 4-door, 2023 model

  Good output:
  close-up of the chrome Ford script badge centered on the rear tailgate of a red 2023 6th-generation Ford Bronco SUV, parked in a suburban driveway, soft morning sunlight across the panel, faint reflection of the house, shallow depth of field, 35mm

  Why it works:
    - Visual description of the badge, not "FORD EMBLEM" text-quoted.
    - Vehicle taken from the glossary verbatim (red 2023 6th-gen).
    - One environment: exterior driveway, not "inside the house".
    - No invented year (1969) or color (white).
"""


USER_TEMPLATE = """SHOT TO TRANSLATE:

Scene heading: {heading}
Setting: {setting} ({time_of_day})
Characters in scene: {characters}
Shot description: {description}
{glossary_block}
Generate the image-gen prompt now (one line, no preamble):"""


@dataclass
class GeneratedPrompt:
    text: str
    model: str
    raw_response: str


def _ollama_generate(
    prompt: str,
    *,
    system: str,
    model: str,
    num_predict: int,
    num_ctx: int,
) -> str:
    """Call Ollama's /api/generate with explicit options. Returns the
    response text. Raises RuntimeError on any failure mode the caller
    should surface."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "temperature": 0.7,
            "top_p": 0.9,
        },
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            r = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Ollama not reachable at {OLLAMA_URL}. Is it running? "
            f"`ollama serve` to start it."
        ) from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            f"Ollama request timed out after {REQUEST_TIMEOUT:.0f}s. "
            f"Is the {model} model loaded? `ollama run {model}` to warm it."
        ) from exc
    except httpx.HTTPStatusError as exc:
        body = ""
        try:
            body = exc.response.text[:300]
        except Exception:
            pass
        raise RuntimeError(
            f"Ollama returned {exc.response.status_code}: {body or exc}"
        ) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Ollama returned non-JSON: {exc}") from exc

    text = (data.get("response") or "").strip()
    if not text:
        raise RuntimeError(
            f"Ollama returned an empty response (model={model}). "
            f"Try a different model or restart Ollama."
        )
    return text


def _clean_prompt(raw: str) -> str:
    """Strip likely-LLM-junk from the response: fences, quotes, leading
    'Prompt:' labels, trailing periods etc."""
    s = raw.strip()
    # Strip fences
    if s.startswith("```"):
        # Drop opening fence (and optional language tag)
        s = s.split("\n", 1)[1] if "\n" in s else s
        # Drop closing fence
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # Drop matching outer quotes
    for q in ('"', "'", "“", "”"):
        if s.startswith(q) and s.endswith(q) and len(s) >= 2:
            s = s[1:-1].strip()
    # Strip leading labels like "Prompt:" or "Image prompt:"
    for prefix in ("prompt:", "image prompt:", "output:", "result:"):
        if s.lower().startswith(prefix):
            s = s[len(prefix) :].lstrip()
    # Sometimes the model emits multiple lines — keep the first non-empty.
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if lines:
        s = lines[0]
    return s


def generate_prompt_for_shot(
    *,
    heading: str,
    setting: str,
    time_of_day: str,
    characters: list[str],
    description: str,
    model: Optional[str] = None,
    glossary: Optional[str] = None,
) -> GeneratedPrompt:
    """Translate a single shot description into an image-gen prompt.

    glossary: optional project-level subject reference, e.g.
      "BRONCO = 6th-gen Ford Bronco SUV, red, 4-door"
      "ELIZA = woman 30s, brown hair, denim jacket"
    Injected into the LLM input so named entities resolve consistently.
    """
    use_model = model or DEFAULT_MODEL
    glossary_block = (
        f"\nProject subject glossary (treat these as the canonical look):\n{glossary.strip()}\n"
        if glossary and glossary.strip()
        else ""
    )
    user = USER_TEMPLATE.format(
        heading=heading,
        setting=setting,
        time_of_day=time_of_day,
        characters=", ".join(characters) if characters else "(none specified)",
        description=description,
        glossary_block=glossary_block,
    )
    raw = _ollama_generate(
        user,
        system=SYSTEM_PROMPT,
        model=use_model,
        num_predict=DEFAULT_NUM_PREDICT,
        num_ctx=DEFAULT_NUM_CTX,
    )
    return GeneratedPrompt(
        text=_clean_prompt(raw),
        model=use_model,
        raw_response=raw,
    )
