from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class TimeOfDay(Enum):
    DAY = "day"
    NIGHT = "night"
    DAWN = "dawn"
    DUSK = "dusk"
    UNKNOWN = "unknown"

class CameraMovement(Enum):
    STATIC = "static"
    PAN = "pan"
    TRACK = "track"
    CRANE = "crane"
    HANDHELD = "handheld"
    AERIAL = "aerial"

class VisualTone(Enum):
    BRIGHT = "bright"
    DARK = "dark"
    NEUTRAL = "neutral"
    HIGH_CONTRAST = "high_contrast"
    SOFT = "soft"

class Weather(Enum):
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    SNOWY = "snowy"
    STORMY = "stormy"
    FOGGY = "foggy"
    UNKNOWN = "unknown"

class Emotion(Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    FEARFUL = "fearful"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"

CharacterState = Emotion  # Add this line to maintain backward compatibility

@dataclass
class Character:
    """Stores character visual information for consistency"""
    name: str
    description: str = ""
    visual_traits: List[str] = field(default_factory=list)
    emotional_state: str = "neutral"
    style_template: Optional[str] = None
    reference_images: List[str] = field(default_factory=list)

@dataclass
class Location:
    """Stores location visual information"""
    name: str
    setting_type: str  # INT/EXT
    description: str = ""
    atmosphere: str = ""
    time_of_day: TimeOfDay = TimeOfDay.UNKNOWN
    style_template: Optional[str] = None
    reference_images: List[str] = field(default_factory=list)

@dataclass
class VisualStyle:
    """Defines the visual style for a scene or sequence"""
    tone: VisualTone = VisualTone.NEUTRAL
    lighting: str = "natural"
    color_palette: List[str] = field(default_factory=list)
    camera_movement: CameraMovement = CameraMovement.STATIC
    atmosphere_keywords: List[str] = field(default_factory=list)
    reference_images: List[str] = field(default_factory=list)
    style_template: Optional[str] = None

@dataclass
class Scene:
    """Enhanced scene class with visual information for AI generation"""
    number: int
    heading: str
    location: Location
    characters: List[Character]
    action_descriptions: List[str] = field(default_factory=list)
    dialogue: List[tuple[str, str]] = field(default_factory=list)  # (character, text)
    visual_style: VisualStyle = field(default_factory=VisualStyle)
    transitions: List[str] = field(default_factory=list)
    
    # AI Generation specific fields
    stable_diffusion_prompts: List[str] = field(default_factory=list)
    key_frames: List[Dict] = field(default_factory=list)
    estimated_duration: float = 0.0  # in seconds
    
    # Add to existing fields
    applied_style_config: Dict = field(default_factory=dict)
    
    def generate_base_prompt(self) -> str:
        """Generate base prompt for Stable Diffusion"""
        prompt_elements = [
            f"Scene {self.number}:",
            f"{self.location.setting_type} {self.location.name}",
            f"Time: {self.location.time_of_day.value}",
            f"Tone: {self.visual_style.tone.value}",
            f"Lighting: {self.visual_style.lighting}",
            f"Camera: {self.visual_style.camera_movement.value}"
        ]
        
        if self.visual_style.atmosphere_keywords:
            prompt_elements.append(f"Atmosphere: {', '.join(self.visual_style.atmosphere_keywords)}")
            
        if self.characters:
            char_descriptions = [f"{char.name}: {char.description}" for char in self.characters]
            prompt_elements.append("Characters: " + "; ".join(char_descriptions))
            
        return ", ".join(prompt_elements)
    
    def estimate_keyframes(self) -> int:
        """Estimate number of keyframes needed based on scene content"""
        base_frames = 1  # At least one frame per scene
        
        # Add frames for significant actions
        base_frames += len(self.action_descriptions)
        
        # Add frames for dialogue exchanges
        base_frames += len(self.dialogue) // 2  # One frame per two dialogue lines
        
        # Add frames for camera movements
        if self.visual_style.camera_movement != CameraMovement.STATIC:
            base_frames += 2  # Start and end positions
            
        return base_frames