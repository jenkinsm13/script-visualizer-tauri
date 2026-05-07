"""FastAPI sidecar for the Script Visualizer Tauri app.

Endpoints:
  GET  /healthz                       liveness
  POST /parse                         {text: str} → {scenes: SceneDTO[]}
  POST /render                        {scene_idx, prompt, style?} → {image_url, status}
  GET  /styles                        list of style presets
  GET  /scenes/{i}/preview.png        rendered storyboard image (when /render done)
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from src import ScriptParser
from src.ai import prompt_gen as _prompt_gen  # noqa: F401  used in /generate-prompt
from src.core import shotlist as _shotlist  # noqa: F401  used in /parse-shotlist
from src.core.scene import Scene


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("script-visualizer")

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".cache" / "renders"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory store of rendered images keyed by render_id (uuid).
_renders: dict[str, bytes] = {}


app = FastAPI(title="script-visualizer", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------- DTOs


class CharacterDTO(BaseModel):
    name: str
    description: str = ""
    emotional_state: str = "neutral"


class LocationDTO(BaseModel):
    name: str
    setting_type: str
    description: str = ""
    time_of_day: str = "unknown"


class VisualStyleDTO(BaseModel):
    tone: str = "neutral"
    lighting: str = "natural"
    atmosphere_keywords: list[str] = []


class SceneDTO(BaseModel):
    number: int
    heading: str
    location: LocationDTO
    characters: list[CharacterDTO]
    action_descriptions: list[str]
    dialogue: list[tuple[str, str]]
    visual_style: VisualStyleDTO
    transitions: list[str]
    base_prompt: str


def _scene_to_dto(s: Scene) -> SceneDTO:
    return SceneDTO(
        number=s.number,
        heading=s.heading,
        location=LocationDTO(
            name=s.location.name,
            setting_type=s.location.setting_type,
            description=s.location.description,
            time_of_day=s.location.time_of_day.value,
        ),
        characters=[
            CharacterDTO(
                name=c.name,
                description=c.description,
                emotional_state=str(c.emotional_state),
            )
            for c in s.characters
        ],
        action_descriptions=s.action_descriptions,
        dialogue=[(d[0], d[1]) for d in s.dialogue],
        visual_style=VisualStyleDTO(
            tone=s.visual_style.tone.value,
            lighting=s.visual_style.lighting,
            atmosphere_keywords=s.visual_style.atmosphere_keywords,
        ),
        transitions=s.transitions,
        base_prompt=s.generate_base_prompt(),
    )


# ---------------------------------------------------------------------- routes


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "project": "script-visualizer"}


class ParseRequest(BaseModel):
    text: str


class ParseResponse(BaseModel):
    scenes: list[SceneDTO]


@app.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest) -> ParseResponse:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="empty screenplay text")
    parser = ScriptParser()
    scenes = parser.parse_script(req.text)
    return ParseResponse(scenes=[_scene_to_dto(s) for s in scenes])


# ------- shot list -------


class ShotListRequest(BaseModel):
    """Either text (pasted shot list) OR pdf_base64 (PDF bytes b64-encoded)."""

    text: Optional[str] = None
    pdf_base64: Optional[str] = None


@app.post("/parse-shotlist", response_model=ParseResponse)
def parse_shotlist(req: ShotListRequest) -> ParseResponse:
    """Parse a shot list into one Scene-shaped card per shot.

    Each numbered line under an INT./EXT. heading becomes its own card —
    distinct from /parse, where each scene aggregates many shots.
    """
    if req.pdf_base64:
        try:
            pdf_bytes = base64.b64decode(req.pdf_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"bad pdf_base64: {exc}")
        scenes = _shotlist.parse_shot_list_pdf(pdf_bytes)
    elif req.text and req.text.strip():
        scenes = _shotlist.parse_shot_list(req.text)
    else:
        raise HTTPException(status_code=400, detail="provide either text or pdf_base64")
    if not scenes:
        raise HTTPException(
            status_code=422,
            detail="no shots detected — expecting headers like 'INT. LOCATION - TIME' "
            "followed by numbered lines '1) DESCRIPTION'",
        )
    return ParseResponse(scenes=[_scene_to_dto(s) for s in scenes])


# ------- styles -------

# Built-in style presets. The UI picks one and we append its modifiers to
# the base scene prompt at render time.
_STYLES: list[dict] = [
    {
        "id": "cinematic",
        "name": "Cinematic",
        "description": "Anamorphic, shallow depth of field, color graded.",
        "modifiers": "cinematic still, anamorphic lens, shallow depth of field, "
        "professional color grade, film grain, dramatic lighting",
    },
    {
        "id": "storyboard-pencil",
        "name": "Pencil Storyboard",
        "description": "Black-and-white sketch, classic storyboard style.",
        "modifiers": "rough pencil storyboard sketch, black and white, "
        "loose hatching, animation pre-production aesthetic",
    },
    {
        "id": "storyboard-marker",
        "name": "Marker Storyboard",
        "description": "Color marker storyboard with tonal washes.",
        "modifiers": "color marker storyboard, copic markers, tonal washes, "
        "key-frame illustration, professional storyboard art",
    },
    {
        "id": "concept-art",
        "name": "Concept Art",
        "description": "Painterly, atmospheric, like a film concept piece.",
        "modifiers": "atmospheric concept art, matte painting, dramatic lighting, "
        "rich color palette, cinematic composition",
    },
    {
        "id": "noir",
        "name": "Film Noir",
        "description": "High contrast black-and-white, hard shadows.",
        "modifiers": "film noir, black and white, high contrast, hard shadows, "
        "venetian blind light patterns, 1940s cinematography",
    },
]


class StyleDTO(BaseModel):
    id: str
    name: str
    description: str
    modifiers: str


@app.get("/styles", response_model=list[StyleDTO])
def styles() -> list[StyleDTO]:
    return [StyleDTO(**s) for s in _STYLES]


# ------- LLM prompt generation -------


class GeneratePromptRequest(BaseModel):
    """Generate an image-gen prompt from a shot, via local LLM (Ollama).

    Pass a SceneDTO-shaped subset; we use it to build the LLM input. Model
    defaults to env SV_PROMPT_MODEL → OLLAMA_MODEL_PROMPT → nemotron3:33b.
    """

    heading: str
    setting: str
    time_of_day: str = "unknown"
    characters: list[str] = []
    description: str
    model: Optional[str] = None
    # Project-wide subject glossary, e.g. "BRONCO = 6th-gen Ford Bronco SUV,
    # red, 4-door". Injected verbatim into the LLM input so character/vehicle
    # /prop identity stays consistent across shots in the same project.
    glossary: Optional[str] = None


class GeneratePromptResponse(BaseModel):
    text: str
    model: str
    elapsed_seconds: float


@app.post("/generate-prompt", response_model=GeneratePromptResponse)
def generate_prompt(req: GeneratePromptRequest) -> GeneratePromptResponse:
    import time as _time

    t0 = _time.time()
    try:
        result = _prompt_gen.generate_prompt_for_shot(
            heading=req.heading,
            setting=req.setting,
            time_of_day=req.time_of_day,
            characters=req.characters,
            description=req.description,
            model=req.model,
            glossary=req.glossary,
        )
    except RuntimeError as exc:
        # prompt_gen raises RuntimeError with user-readable detail —
        # surface it directly.
        raise HTTPException(status_code=503, detail=str(exc))
    return GeneratePromptResponse(
        text=result.text,
        model=result.model,
        elapsed_seconds=round(_time.time() - t0, 2),
    )


# ------- render -------


_DEFAULT_W = int(os.environ.get("SV_RENDER_WIDTH", "1920"))
_DEFAULT_H = int(os.environ.get("SV_RENDER_HEIGHT", "1080"))


class RenderRequest(BaseModel):
    scene_idx: int
    prompt: str
    style_id: Optional[str] = None
    width: int = _DEFAULT_W
    height: int = _DEFAULT_H
    negative_prompt: str = ""
    # Reference images for character/style/composition consistency. Each is
    # a base64-encoded PNG/JPEG. Flux Kontext accepts up to ~4 references.
    reference_images: list[str] = []


class RenderResponse(BaseModel):
    render_id: str
    status: str  # "ok" | "stub" | "error"
    image_url: str  # client GETs this to fetch the PNG
    full_prompt: str
    backend: str  # which backend produced the image
    detail: str = ""


def _resolve_style(style_id: Optional[str]) -> str:
    if not style_id:
        return ""
    for s in _STYLES:
        if s["id"] == style_id:
            return s["modifiers"]
    return ""


def _placeholder_png(width: int, height: int, label: str) -> bytes:
    """Render a placeholder PNG with the prompt text — used when no image
    backend is configured. The user gets visible feedback that the pipeline
    works end-to-end even before they wire up SD/Flux/ComfyUI/Replicate.
    """
    from PIL import Image, ImageDraw, ImageFont  # lazy import — heavy

    img = Image.new("RGB", (width, height), color=(30, 32, 40))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 20)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    # Title
    draw.text(
        (24, 24),
        "[ no image backend configured ]",
        fill=(255, 200, 90),
        font=font,
    )
    # Prompt — wrapped naively
    margin = 24
    max_width = width - 2 * margin
    y = 70
    line = ""
    for word in label.split():
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=small)
        if bbox[2] - bbox[0] > max_width:
            draw.text((margin, y), line, fill=(220, 220, 220), font=small)
            y += 22
            line = word
            if y > height - 30:
                break
        else:
            line = test
    if line and y <= height - 30:
        draw.text((margin, y), line, fill=(220, 220, 220), font=small)

    import io

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _render_via_fal(
    prompt: str, w: int, h: int, refs: list[str]
) -> Optional[tuple[bytes, str]]:
    """Cloud Flux Kontext via fal.ai — kept disabled for now (user wants
    fully local). Re-enable by setting FAL_KEY and uncommenting in render().
    """
    # Cloud disabled. The path stays here as a stub so /render's chain of
    # backends keeps a place for it; flip the early return when we're
    # ready to opt into cloud as a fallback (not the default).
    _ = (prompt, w, h, refs)  # silence unused
    return None


# Flux.2 dev wants different defaults than SD 1.5 / SDXL — lower CFG,
# moderate step count. Override per request or via env.
_RENDER_STEPS = int(os.environ.get("SV_RENDER_STEPS", "30"))
_RENDER_CFG = float(os.environ.get("SV_RENDER_CFG", "4.5"))
# When references are passed, denoising_strength controls how much the
# output deviates from the reference. ~0.7 = strong influence kept;
# 0.4 = mostly the prompt, references guide style/composition.
_RENDER_DENOISE = float(os.environ.get("SV_RENDER_DENOISE", "0.7"))


async def _render_via_a1111(
    prompt: str,
    negative: str,
    w: int,
    h: int,
    refs: Optional[list[str]] = None,
) -> Optional[bytes]:
    """Render via AUTOMATIC1111-compatible API at SD_URL.

    Routes through /sdapi/v1/txt2img when no references, or
    /sdapi/v1/img2img when refs are provided. DrawThings exposes both
    endpoints and natively supports Flux.2 multi-image conditioning by
    accepting multiple init_images. If only one reference is passed,
    it's used as a single init image. Returns None on connection
    failure so the caller can fall back to other backends.
    """
    base = os.environ.get("SD_URL")
    if not base:
        return None

    refs = refs or []
    common: dict = {
        "prompt": prompt,
        "negative_prompt": negative,
        "width": w,
        "height": h,
        "steps": _RENDER_STEPS,
        "cfg_scale": _RENDER_CFG,
    }

    try:
        # Flux.2 dev at 1920×1080 on Apple Silicon takes 60-90s; 300s
        # gives headroom for first-call cold model load.
        async with httpx.AsyncClient(timeout=300.0) as client:
            if refs:
                payload = {
                    **common,
                    "init_images": refs,
                    "denoising_strength": _RENDER_DENOISE,
                }
                endpoint = f"{base.rstrip('/')}/sdapi/v1/img2img"
            else:
                payload = common
                endpoint = f"{base.rstrip('/')}/sdapi/v1/txt2img"
            r = await client.post(endpoint, json=payload)
            r.raise_for_status()
            data = r.json()
            imgs = data.get("images") or []
            if imgs:
                return base64.b64decode(imgs[0])
    except Exception as exc:  # noqa: BLE001
        log.warning("A1111 render failed: %s: %s", type(exc).__name__, exc)
    return None


async def _render_via_replicate(prompt: str, w: int, h: int) -> Optional[bytes]:
    """Try Replicate (Flux) if REPLICATE_API_TOKEN is set."""
    token = os.environ.get("REPLICATE_API_TOKEN")
    if not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                "https://api.replicate.com/v1/predictions",
                headers={
                    "Authorization": f"Token {token}",
                    "Prefer": "wait",
                },
                json={
                    "version": "black-forest-labs/flux-schnell",
                    "input": {
                        "prompt": prompt,
                        "aspect_ratio": "16:9",
                        "output_format": "png",
                        "num_outputs": 1,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            urls = data.get("output") or []
            if isinstance(urls, str):
                urls = [urls]
            if urls:
                img = await client.get(urls[0])
                img.raise_for_status()
                return img.content
    except Exception as exc:  # noqa: BLE001
        log.warning("Replicate render failed: %s: %s", type(exc).__name__, exc)
    return None


@app.post("/render", response_model=RenderResponse)
async def render(req: RenderRequest) -> RenderResponse:
    style_modifiers = _resolve_style(req.style_id)
    full_prompt = f"{req.prompt}, {style_modifiers}" if style_modifiers else req.prompt

    img_bytes: Optional[bytes] = None
    backend = "stub"
    detail = ""

    # Try real backends in order of preference, falling back to a placeholder.
    img_bytes = await _render_via_a1111(
        full_prompt,
        req.negative_prompt,
        req.width,
        req.height,
        refs=req.reference_images,
    )
    if img_bytes:
        backend = "a1111+refs" if req.reference_images else "a1111"
    if img_bytes is None:
        img_bytes = await _render_via_replicate(full_prompt, req.width, req.height)
        if img_bytes:
            backend = "replicate"
    if img_bytes is None:
        img_bytes = _placeholder_png(req.width, req.height, full_prompt)
        backend = "stub"
        detail = (
            "No image backend configured. Set SD_URL=http://localhost:7860 for "
            "AUTOMATIC1111, or REPLICATE_API_TOKEN=… for Flux. The placeholder "
            "image is the prompt rendered as text."
        )

    render_id = str(uuid.uuid4())
    _renders[render_id] = img_bytes
    # Persist to disk so renders survive restarts.
    (CACHE_DIR / f"{render_id}.png").write_bytes(img_bytes)

    return RenderResponse(
        render_id=render_id,
        status="ok",
        image_url=f"/renders/{render_id}.png",
        full_prompt=full_prompt,
        backend=backend,
        detail=detail,
    )


@app.get("/renders/{render_id}.png")
def get_render(render_id: str) -> Response:
    img = _renders.get(render_id)
    if img is None:
        # Try disk cache.
        path = CACHE_DIR / f"{render_id}.png"
        if path.exists():
            img = path.read_bytes()
            _renders[render_id] = img
    if img is None:
        raise HTTPException(status_code=404, detail="render not found")
    return Response(
        content=img,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
