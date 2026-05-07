"""Screenplay parser — splits a script into Scenes the rest of the pipeline
can consume.

This is a deliberate simplification of the original parser, which depended on
many half-defined data classes and never ran end-to-end. We keep what's
load-bearing for image-prompt generation:

  - scene boundaries (INT./EXT. headers + time-of-day)
  - character cues (ALL-CAPS lines preceding dialogue)
  - dialogue lines (text immediately under a character cue)
  - action paragraphs (everything else inside a scene)

…and drop the speculative camera-motion / emotion / beat-duration analysis.
The downstream prompt builder already has reasonable defaults for those.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

from .scene import (
    Character,
    Emotion,
    Location,
    Scene,
    TimeOfDay,
    VisualStyle,
    VisualTone,
    Weather,
)


_SCENE_HEADER = re.compile(
    r"^\s*(?:\d+\s+)?(INT\.?|EXT\.?|INT/EXT\.?|EXT/INT\.?)\s+(.+?)\s*[-—]\s*(.+?)\s*$",
    re.IGNORECASE,
)
# Loose form: "INT. KITCHEN" with no time-of-day separator.
_SCENE_HEADER_NO_TIME = re.compile(
    r"^\s*(?:\d+\s+)?(INT\.?|EXT\.?|INT/EXT\.?|EXT/INT\.?)\s+(.+?)\s*$",
    re.IGNORECASE,
)
_CHARACTER_CUE = re.compile(r"^\s*([A-Z][A-Z0-9 .'\-]{1,40})(\s*\(.*\))?\s*$")
_PARENTHETICAL = re.compile(r"^\s*\((.*?)\)\s*$")
_TRANSITION = re.compile(
    r"^\s*(CUT TO:|FADE OUT[.:]?|FADE IN[.:]?|DISSOLVE TO:|SMASH CUT TO:)",
    re.IGNORECASE,
)


def _detect_time(text: str) -> TimeOfDay:
    t = text.lower()
    table = [
        (r"\b(dawn|sunrise|early\s+morning)\b", TimeOfDay.DAWN),
        (r"\b(morning|breakfast)\b", TimeOfDay.MORNING),
        (r"\b(noon|midday|afternoon|day(?:light|time)?|continuous)\b", TimeOfDay.DAY),
        (r"\b(dusk|sunset|twilight|evening)\b", TimeOfDay.DUSK),
        (r"\b(night|midnight|darkness|late)\b", TimeOfDay.NIGHT),
    ]
    for pat, tod in table:
        if re.search(pat, t):
            return tod
    return TimeOfDay.UNKNOWN


def _detect_weather(text: str) -> Weather:
    t = text.lower()
    table = [
        (r"\b(rain|drizzle|downpour|raining)\b", Weather.RAINY),
        (r"\b(storm|thunder|lightning)\b", Weather.STORMY),
        (r"\b(snow|blizzard|flurries)\b", Weather.SNOWY),
        (r"\b(fog|mist|haze)\b", Weather.FOGGY),
        (r"\b(cloudy|overcast|grey\s+skies)\b", Weather.CLOUDY),
        (r"\b(sunny|clear\s+sky|bright)\b", Weather.CLEAR),
    ]
    for pat, w in table:
        if re.search(pat, t):
            return w
    return Weather.UNKNOWN


def _detect_tone(text: str) -> VisualTone:
    t = text.lower()
    table = [
        (r"\b(stark|harsh|dramatic|chiaroscuro)\b", VisualTone.HIGH_CONTRAST),
        (r"\b(soft|gentle|muted|diffused)\b", VisualTone.SOFT),
        (r"\b(dark|shadowy|dim|gloomy)\b", VisualTone.DARK),
        (r"\b(bright|vibrant|luminous|sunlit)\b", VisualTone.BRIGHT),
        (r"\b(warm|golden|amber|orange)\b", VisualTone.WARM),
        (r"\b(cool|blue|steel|cold)\b", VisualTone.COOL),
    ]
    for pat, tone in table:
        if re.search(pat, t):
            return tone
    return VisualTone.NEUTRAL


def _detect_emotion(text: str) -> Optional[Emotion]:
    t = text.lower()
    table = [
        (r"\b(smiles?|laughs?|happy|joyful|grins?)\b", Emotion.HAPPY),
        (r"\b(sad|crying|tears|sobs?|weep)\b", Emotion.SAD),
        (r"\b(angry|furious|rage|scowls?|yells?)\b", Emotion.ANGRY),
        (r"\b(scared|afraid|trembling|nervous|terrified)\b", Emotion.FEARFUL),
        (r"\b(surprised|shocked|startled|stunned)\b", Emotion.SURPRISED),
        (r"\b(tense|anxious|worried|wary)\b", Emotion.TENSE),
        (r"\b(calm|relaxed|peaceful|serene)\b", Emotion.PEACEFUL),
    ]
    for pat, emo in table:
        if re.search(pat, t):
            return emo
    return None


def _split_heading(line: str) -> Optional[Tuple[str, str, str]]:
    """Returns (setting_type, location, time_of_day_text) or None."""
    m = _SCENE_HEADER.match(line)
    if m:
        return m.group(1).rstrip("."), m.group(2).strip(), m.group(3).strip()
    m = _SCENE_HEADER_NO_TIME.match(line)
    if m:
        return m.group(1).rstrip("."), m.group(2).strip(), ""
    return None


def _is_scene_header(line: str) -> bool:
    return _split_heading(line.strip()) is not None


def _clean_content(content: str) -> str:
    # Collapse multi-blank lines, drop page numbers, remove (CONTINUED).
    content = content.replace("\f", "\n")
    content = re.sub(r"^\s*\d+\.\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*\(CONTINUED\)\s*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"^\s*CONTINUED:.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


class ScriptParser:
    """Parses a screenplay text into a list of Scene objects."""

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------ public

    def parse_script(self, content: str) -> List[Scene]:
        cleaned = _clean_content(content)
        lines = cleaned.split("\n")

        scenes: List[Scene] = []
        buf: List[str] = []
        scene_idx = 0

        for line in lines:
            if _is_scene_header(line):
                if buf:
                    s = self._build_scene(buf, scene_idx)
                    if s:
                        scenes.append(s)
                        scene_idx += 1
                    buf = []
                buf.append(line)
            else:
                if line.strip() or buf:
                    buf.append(line)

        if buf:
            s = self._build_scene(buf, scene_idx)
            if s:
                scenes.append(s)

        self.logger.info("parsed %d scenes", len(scenes))
        return scenes

    # ------------------------------------------------------------------ internal

    def _build_scene(self, lines: List[str], idx: int) -> Optional[Scene]:
        if not lines:
            return None
        heading_line = lines[0].strip()
        parts = _split_heading(heading_line)
        if not parts:
            return None
        setting_type, location_name, time_text = parts

        chars_by_name: dict[str, Character] = {}
        dialogue: List[Tuple[str, str]] = []
        action_descriptions: List[str] = []
        transitions: List[str] = []

        current_speaker: Optional[Character] = None
        # Body lines (skip the heading itself).
        i = 1
        while i < len(lines):
            line = lines[i].rstrip()
            stripped = line.strip()
            if not stripped:
                current_speaker = None
                i += 1
                continue

            if _TRANSITION.match(stripped):
                transitions.append(stripped)
                current_speaker = None
                i += 1
                continue

            cue = _CHARACTER_CUE.match(line)
            # Heuristic: a character cue is short, all-caps, and is followed
            # by either dialogue or a parenthetical. Bare action lines that
            # happen to be all-caps (rare but possible) won't have a follower.
            if cue and i + 1 < len(lines) and lines[i + 1].strip():
                name = re.sub(r"\s+", " ", cue.group(1).strip())
                if name not in chars_by_name:
                    chars_by_name[name] = Character(name=name)
                current_speaker = chars_by_name[name]
                i += 1
                continue

            paren = _PARENTHETICAL.match(stripped)
            if paren and current_speaker:
                emo = _detect_emotion(paren.group(1))
                if emo:
                    current_speaker.emotional_state = emo.value
                i += 1
                continue

            if current_speaker:
                # Dialogue line.
                dialogue.append((current_speaker.name, stripped))
                emo = _detect_emotion(stripped)
                if emo:
                    current_speaker.emotional_state = emo.value
                i += 1
                continue

            # Action line.
            action_descriptions.append(stripped)
            i += 1

        # Build location with time/weather sniffed from the heading line.
        location_text = f"{location_name} {time_text}"
        location = Location(
            name=location_name,
            setting_type=setting_type.upper(),
            description=heading_line,
            time_of_day=_detect_time(time_text or location_text),
        )

        # Build visual style from the action lines (the prose carries the mood).
        action_blob = " ".join(action_descriptions)
        style = VisualStyle(
            tone=_detect_tone(action_blob),
            atmosphere_keywords=self._extract_atmosphere(action_blob),
        )

        scene = Scene(
            number=idx + 1,
            heading=heading_line,
            location=location,
            characters=list(chars_by_name.values()),
            action_descriptions=action_descriptions,
            dialogue=dialogue,
            visual_style=style,
            transitions=transitions,
        )
        scene.estimated_duration = scene.estimate_keyframes() * 2.0
        return scene

    @staticmethod
    def _extract_atmosphere(text: str) -> List[str]:
        keywords: List[str] = []
        patterns = [
            r"\b(mysterious|eerie|suspenseful)\b",
            r"\b(romantic|intimate|tender)\b",
            r"\b(chaotic|frenzied|intense|frantic)\b",
            r"\b(peaceful|tranquil|serene|still)\b",
            r"\b(grim|bleak|desolate)\b",
        ]
        for p in patterns:
            keywords.extend(re.findall(p, text, re.IGNORECASE))
        # de-dupe, lowercase
        return sorted({k.lower() for k in keywords})
