"""Shot-list parser.

A shot list is structured as scene headers (INT./EXT. LOCATION - TIME)
followed by numbered shots (1) DESCRIPTION, 2) DESCRIPTION, ...). Each
numbered shot is one storyboard frame — distinct from a screenplay
scene (which can span many shots).

We map each shot to a Scene-shaped object so the existing /render
pipeline + storyboard grid works unchanged. The "scene number" in the
output is actually the shot's flat index across the whole list (1, 2, …).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import pymupdf

from .parser import _detect_time, _detect_tone, _split_heading
from .scene import (
    Character,
    Location,
    Scene,
    VisualStyle,
)


_SHOT_LINE = re.compile(r"^\s*(\d+)\s*[\.\)]\s+(.+?)\s*$")


@dataclass
class _ShotEntry:
    flat_index: int  # 1-based across the whole list
    scene_index: int  # 1-based scene grouping
    shot_in_scene: int  # 1-based within its scene
    scene_heading: str
    location: Location
    description: str  # the shot's prose


def parse_shot_list(content: str) -> List[Scene]:
    """Parse a shot list (plain text) into a flat list of shots, each
    represented as a Scene so it can flow through the rest of the pipeline.
    """
    lines = content.splitlines()
    shots: List[_ShotEntry] = []

    current_heading: Optional[str] = None
    current_location: Optional[Location] = None
    scene_idx = 0
    shot_in_scene = 0

    pending_buffer: List[str] = []  # lines belonging to the previous shot

    def _flush_pending(into_shot: Optional[_ShotEntry]) -> None:
        if into_shot is None or not pending_buffer:
            return
        extra = " ".join(s.strip() for s in pending_buffer if s.strip())
        if extra:
            into_shot.description = f"{into_shot.description} {extra}".strip()
        pending_buffer.clear()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # Scene header?
        if stripped:
            parts = _split_heading(stripped)
            if parts:
                _flush_pending(shots[-1] if shots else None)
                setting_type, location_name, time_text = parts
                current_heading = stripped
                current_location = Location(
                    name=location_name,
                    setting_type=setting_type.upper(),
                    description=stripped,
                    time_of_day=_detect_time(time_text or location_name),
                )
                scene_idx += 1
                shot_in_scene = 0
                continue

        # Shot line?
        m = _SHOT_LINE.match(stripped) if stripped else None
        if m and current_location is not None:
            _flush_pending(shots[-1] if shots else None)
            shot_in_scene += 1
            shots.append(
                _ShotEntry(
                    flat_index=len(shots) + 1,
                    scene_index=scene_idx,
                    shot_in_scene=shot_in_scene,
                    scene_heading=current_heading or "",
                    location=current_location,
                    description=m.group(2).strip(),
                )
            )
            continue

        # Continuation line for the most recent shot (PDFs sometimes wrap a
        # single shot's description across two lines). Only buffer once we've
        # already seen at least one shot — otherwise pre-shot title-page
        # text gets folded into shot 1.
        if stripped and shots:
            pending_buffer.append(stripped)

    # Final flush
    _flush_pending(shots[-1] if shots else None)

    # Build Scene objects (one per shot)
    out: List[Scene] = []
    for entry in shots:
        style = VisualStyle(tone=_detect_tone(entry.description))
        chars = _extract_named_subjects(entry.description)
        scene = Scene(
            number=entry.flat_index,
            heading=f"{entry.scene_heading} — shot {entry.shot_in_scene}",
            location=entry.location,
            characters=chars,
            action_descriptions=[entry.description],
            visual_style=style,
        )
        out.append(scene)
    return out


def parse_shot_list_pdf(pdf_bytes: bytes) -> List[Scene]:
    """Convenience: read a PDF's text via PyMuPDF, then parse_shot_list."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        text = "\n".join(p.get_text("text") or "" for p in doc)
    finally:
        doc.close()
    return parse_shot_list(text)


# Subject extraction: shot list prose is mostly ALL-CAPS, so capitalization
# alone tells us nothing. Strategy: walk the line token-by-token, treat
# cinematography/grammar tokens as separators, and the contiguous runs of
# remaining tokens are the noun-phrase subjects ("ELIZA", "FORD EMBLUM",
# "TOY BRONCO"). Discard anything inside parentheses (camera-rig asides
# like "(GO PRO?)").
_SUBJECT_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9'\-/]{0,}")
_STOPWORDS: set[str] = {
    # Scene-header / structural
    "INT",
    "EXT",
    "INT/EXT",
    "EXT/INT",
    "CONT",
    "ALT",
    "VO",
    "OS",
    "POV",
    "TO",
    "AS",
    # Shot sizes / framing
    "CU",
    "ECU",
    "MCU",
    "MS",
    "WS",
    "EWS",
    "MEDIUM",
    "WIDE",
    "CLOSE",
    "TIGHT",
    "FULL",
    "LONG",
    "SHORT",
    "SHOT",
    "FRAME",
    "RACK",
    "INSERT",
    "ESTABLISHING",
    # Camera moves / angles
    "DRONE",
    "STEADICAM",
    "HANDHELD",
    "DOLLY",
    "PAN",
    "TILT",
    "TRACK",
    "TRACKING",
    "CRANE",
    "ZOOM",
    "PUSH",
    "PULL",
    "REVERSE",
    "REVEAL",
    "ANGLE",
    "HIGH",
    "LOW",
    "OVERHEAD",
    "TOP-DOWN",
    "TOP",
    "DOWN",
    "UP",
    "FRONT",
    "BACK",
    "SIDE",
    "PROFILE",
    "TWO",
    "THREE",
    "FOUR",
    "OVER",
    # Composition / direction
    "FG",
    "BG",
    "MG",
    "MFG",
    "RFG",
    "LFG",
    # Common shot-list adjectives
    "CLEAN",
    "HERO",
    "DIRTY",
    "MASTER",
    "SLOW",
    "FAST",
    "MO",
    "MOTION",
    "STILL",
    "STATIC",
    "MOVING",
    "HARD",
    "SOFT",
    "QUICK",
    # Cuts / transitions
    "CUT",
    "FADE",
    "DISSOLVE",
    "SMASH",
    # Brand / pro / asides
    "GO",
    "PRO",
    "GOPRO",
    "ALSO",
    "MAYBE",
    # Common prepositions / glue (in caps)
    "ON",
    "OF",
    "OFF",
    "AT",
    "IN",
    "OUT",
    "INTO",
    "ONTO",
    "FROM",
    "BY",
    "FOR",
    "WITH",
    "AND",
    "OR",
    "BUT",
    "THE",
    "A",
    "AN",
    "HER",
    "HIS",
    "THEY",
    "THEM",
    "IT",
    "IT'S",
    "ITS",
    "THIS",
    "THAT",
    "THESE",
    "THOSE",
    "ALL",
    "WAY",
    "ALONG",
    "TOWARDS",
    "AWAY",
    # Page metadata
    "PAGE",
    "OF",
    "V",
    "V.1",
    "V.2",
    "V.3",
    "BY",
}


def _extract_named_subjects(text: str) -> List[Character]:
    # Drop parenthetical asides — they're camera/rig commentary.
    cleaned = re.sub(r"\([^)]*\)", " ", text)
    seen: list[str] = []
    current: list[str] = []
    for tok in _SUBJECT_TOKEN_RE.findall(cleaned):
        if not tok or tok in _STOPWORDS or len(tok) <= 1:
            if current:
                joined = " ".join(current)
                if joined and joined not in seen:
                    seen.append(joined)
                current = []
            continue
        current.append(tok)
    if current:
        joined = " ".join(current)
        if joined and joined not in seen:
            seen.append(joined)
    return [Character(name=n) for n in seen[:5]]
