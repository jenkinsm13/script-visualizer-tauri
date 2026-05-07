from typing import List, Dict, Optional
import re
from ..core.scene import Scene, TimeOfDay, CameraMovement, VisualTone, Character, Location, VisualStyle

class VisualAnalyzer:
    """Analyzes script content for visual elements and AI prompt generation"""
    
    def __init__(self):
        self._camera_keywords = {
            CameraMovement.PAN: ['pan', 'panning', 'sweeps', 'scanning'],
            CameraMovement.TRACK: ['tracking', 'follows', 'moving with', 'dolly'],
            CameraMovement.CRANE: ['crane', 'rising', 'descending', 'aerial view'],
            CameraMovement.HANDHELD: ['handheld', 'shaky', 'unstable', 'documentary style'],
            CameraMovement.AERIAL: ['drone', 'bird\'s eye', 'overhead', 'aerial']
        }
        
        self._tone_keywords = {
            VisualTone.BRIGHT: ['sunny', 'bright', 'vibrant', 'cheerful', 'warm'],
            VisualTone.DARK: ['dark', 'gloomy', 'shadowy', 'moody', 'noir'],
            VisualTone.HIGH_CONTRAST: ['harsh', 'dramatic', 'stark', 'contrasting'],
            VisualTone.SOFT: ['soft', 'gentle', 'dreamy', 'hazy', 'muted']
        }
        
        self._atmosphere_patterns = {
            'tension': r'\b(tense|nervous|anxiety|suspense)\b',
            'romance': r'\b(romantic|intimate|tender|loving)\b',
            'action': r'\b(explosive|violent|fast|intense|chaos)\b',
            'mystery': r'\b(mysterious|enigmatic|strange|eerie)\b',
            'comedy': r'\b(funny|humorous|silly|comedic)\b'
        }
    
    def analyze_scene(self, scene: Scene) -> Scene:
        """Enhance scene with visual analysis"""
        # Analyze camera movement
        scene.visual_style.camera_movement = self._detect_camera_movement(scene.action_descriptions)
        
        # Analyze visual tone
        scene.visual_style.tone = self._detect_visual_tone(
            scene.action_descriptions + [scene.location.description]
        )
        
        # Analyze atmosphere
        scene.visual_style.atmosphere_keywords = self._detect_atmosphere(
            scene.action_descriptions + [scene.location.description]
        )
        
        # Generate prompts
        scene.stable_diffusion_prompts = self._generate_prompts(scene)
        
        return scene
    
    def _detect_camera_movement(self, descriptions: List[str]) -> CameraMovement:
        """Detect camera movement from scene descriptions"""
        text = ' '.join(descriptions).lower()
        
        for movement, keywords in self._camera_keywords.items():
            if any(keyword in text for keyword in keywords):
                return movement
        
        return CameraMovement.STATIC
    
    def _detect_visual_tone(self, descriptions: List[str]) -> VisualTone:
        """Detect visual tone from scene descriptions"""
        text = ' '.join(descriptions).lower()
        
        tone_scores = {tone: 0 for tone in VisualTone}
        
        for tone, keywords in self._tone_keywords.items():
            tone_scores[tone] = sum(1 for keyword in keywords if keyword in text)
            
        # Get tone with highest score
        max_tone = max(tone_scores.items(), key=lambda x: x[1])[0]
        return max_tone if tone_scores[max_tone] > 0 else VisualTone.NEUTRAL
    
    def _detect_atmosphere(self, descriptions: List[str]) -> List[str]:
        """Detect atmosphere keywords from scene descriptions"""
        text = ' '.join(descriptions).lower()
        atmosphere = []
        
        for mood, pattern in self._atmosphere_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                atmosphere.append(mood)
                
        return atmosphere
    
    def _generate_prompts(self, scene: Scene) -> List[str]:
        """Generate Stable Diffusion prompts for the scene"""
        prompts = []
        base_prompt = scene.generate_base_prompt()
        
        # Generate a prompt for each key frame
        n_frames = scene.estimate_keyframes()
        
        for i in range(n_frames):
            prompt = base_prompt
            
            # Add frame-specific elements
            if i < len(scene.action_descriptions):
                prompt += f", Action: {scene.action_descriptions[i]}"
                
            # Add style modifiers
            prompt += self._get_style_modifiers(scene.visual_style)
            
            # Add quality boosters
            prompt += (", professional photography, high quality, detailed, realistic, "
                      "cinematic lighting, 8k resolution")
            
            prompts.append(prompt)
            
        return prompts
    
    def _get_style_modifiers(self, style: VisualStyle) -> str:
        """Generate style modifier string for prompts"""
        modifiers = []
        
        if style.lighting:
            modifiers.append(f"lighting: {style.lighting}")
            
        if style.color_palette:
            modifiers.append(f"color palette: {', '.join(style.color_palette)}")
            
        if style.atmosphere_keywords:
            modifiers.append(f"atmosphere: {', '.join(style.atmosphere_keywords)}")
            
        return ", " + ", ".join(modifiers) if modifiers else ""