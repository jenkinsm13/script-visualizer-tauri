from typing import Dict, List, Optional
import json
import os
from dataclasses import dataclass, asdict
from ..core.scene import VisualStyle, VisualTone, CameraMovement
from pathlib import Path
import logging

@dataclass
class StyleTemplate:
    """Template for consistent visual styling"""
    name: str
    description: str
    base_prompt: str
    negative_prompt: str = ""
    tone: VisualTone = VisualTone.NEUTRAL
    lighting_presets: List[str] = None
    color_palettes: List[List[str]] = None
    camera_movements: List[CameraMovement] = None
    atmosphere_keywords: List[str] = None
    
    def __post_init__(self):
        # Ensure lists are initialized properly
        self.lighting_presets = self.lighting_presets or []
        self.color_palettes = self.color_palettes or [[]]  # At least one empty palette
        self.camera_movements = self.camera_movements or []
        self.atmosphere_keywords = self.atmosphere_keywords or []
        
    @classmethod
    def from_json(cls, data: dict) -> 'StyleTemplate':
        """Safely create template from JSON data"""
        try:
            # Convert string to enum for tone
            if isinstance(data.get('tone'), str):
                data['tone'] = VisualTone[data['tone'].upper()]
            
            # Convert strings to enums for camera movements
            if 'camera_movements' in data:
                data['camera_movements'] = [
                    CameraMovement[mv.upper()] if isinstance(mv, str) else mv 
                    for mv in data['camera_movements']
                ]
                
            return cls(**data)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Invalid template data: {str(e)}")

class StyleManager:
    """Manages visual style templates and consistency"""
    
    def __init__(self, templates_dir: str = "styles"):
        self.templates_dir = templates_dir
        self.templates: Dict[str, StyleTemplate] = {}
        self.active_template: Optional[StyleTemplate] = None
        
        # Create default style templates
        self._create_default_templates()
        
        # Load any custom templates
        self.load_templates()
        
    def _create_default_templates(self):
        """Create default style templates"""
        noir_template = StyleTemplate(
            name="Film Noir",
            description="High contrast, dramatic shadows, moody atmosphere",
            base_prompt="film noir style, dramatic lighting, deep shadows, high contrast",
            negative_prompt="bright, colorful, flat lighting, cheerful",
            tone=VisualTone.DARK,
            lighting_presets=["low-key", "chiaroscuro", "venetian blinds", "rim lighting"],
            color_palettes=[["#000000", "#FFFFFF", "#404040"]],
            atmosphere_keywords=["mysterious", "moody", "dramatic", "shadowy"]
        )
        
        natural_template = StyleTemplate(
            name="Natural Realism",
            description="Realistic lighting and colors, documentary style",
            base_prompt="realistic, natural lighting, photorealistic, detailed",
            negative_prompt="artistic, stylized, unrealistic, cartoon",
            tone=VisualTone.NEUTRAL,
            lighting_presets=["natural", "soft", "available light", "practical"],
            color_palettes=[["#F5F5F5", "#E0E0E0", "#BDBDBD", "#757575"]],
            atmosphere_keywords=["realistic", "natural", "authentic", "candid"]
        )
        
        cyberpunk_template = StyleTemplate(
            name="Neo-Cyberpunk",
            description="High-tech, neon-lit, futuristic aesthetic",
            base_prompt="cyberpunk style, neon lights, futuristic, technological",
            negative_prompt="vintage, natural, rustic, organic",
            tone=VisualTone.HIGH_CONTRAST,
            lighting_presets=["neon", "LED", "holographic", "backlit"],
            color_palettes=[["#FF00FF", "#00FFFF", "#FF0000", "#0000FF"]],
            atmosphere_keywords=["futuristic", "high-tech", "urban", "dystopian"]
        )
        
        self.templates = {
            "film_noir": noir_template,
            "natural_realism": natural_template,
            "neo_cyberpunk": cyberpunk_template
        }
        
    def load_templates(self) -> Dict[str, StyleTemplate]:
        """Load style templates from JSON files"""
        templates = {}
        template_dir = Path(__file__).parent / "templates"
        
        if not template_dir.exists():
            return templates
            
        for file_path in template_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    template = StyleTemplate.from_json(data)
                    templates[template.name] = template
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse template {file_path}: {str(e)}")
            except Exception as e:
                logging.error(f"Failed to load template {file_path}: {str(e)}")
                
        return templates
        
    def save_template(self, template: StyleTemplate):
        """Save a custom template"""
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)
            
        filename = f"{template.name.lower().replace(' ', '_')}.json"
        path = os.path.join(self.templates_dir, filename)
        
        with open(path, 'w') as f:
            json.dump(asdict(template), f, indent=4)
            
        self.templates[template.name] = template
        
    def get_template(self, name: str) -> Optional[StyleTemplate]:
        """Get a template by name"""
        return self.templates.get(name)
        
    def set_active_template(self, name: str):
        """Set the active template for style consistency"""
        if name in self.templates:
            self.active_template = self.templates[name]
        
    def apply_template_to_style(self, style: VisualStyle, template_name: str) -> VisualStyle:
        """Apply a template to a VisualStyle object"""
        template = self.get_template(template_name)
        if not template:
            return style
            
        style.tone = template.tone
        style.style_template = template_name
        
        if template.lighting_presets:
            style.lighting = template.lighting_presets[0]  # Use first preset as default
            
        if template.color_palettes:
            style.color_palette = template.color_palettes[0]  # Use first palette as default
            
        if template.atmosphere_keywords:
            style.atmosphere_keywords = template.atmosphere_keywords.copy()
            
        return style
        
    def generate_prompt_modifiers(self, template_name: str) -> Dict[str, str]:
        """Generate prompt modifiers based on template"""
        template = self.get_template(template_name)
        if not template:
            return {}
            
        return {
            "base_prompt": template.base_prompt,
            "negative_prompt": template.negative_prompt
        }