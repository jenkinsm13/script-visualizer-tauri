from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum

class MotionType(Enum):
    """Types of motion in a scene"""
    STATIC = "static"
    CAMERA_MOVE = "camera_move"
    SUBJECT_MOVE = "subject_move"
    BOTH = "both"

class CameraMotion(Enum):
    """Specific camera movements"""
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    DOLLY_IN = "dolly_in"
    DOLLY_OUT = "dolly_out"
    TRACKING = "tracking"
    CRANE_UP = "crane_up"
    CRANE_DOWN = "crane_down"
    AERIAL = "aerial"
    STATIC = "static"

@dataclass
class SubjectMotion:
    """Describes movement of subjects in scene"""
    who: str  # Which character/object is moving
    action: str  # What they're doing
    direction: Optional[str] = None  # Direction of movement if applicable
    speed: str = "normal"  # Speed of movement
    intensity: str = "normal"  # Intensity/energy of movement

@dataclass
class PromptElements:
    """Structured elements for prompt construction"""
    who: List[str] = field(default_factory=list)  # Characters, key objects
    what: List[str] = field(default_factory=list)  # Actions, events, states
    where: List[str] = field(default_factory=list)  # Location details
    when: List[str] = field(default_factory=list)  # Time, period, conditions
    why: List[str] = field(default_factory=list)  # Context, motivations
    how: List[str] = field(default_factory=list)  # Style, mood, atmosphere

@dataclass
class MotionPrompt:
    """Motion-specific prompt elements"""
    motion_type: MotionType = MotionType.STATIC
    camera_motion: CameraMotion = CameraMotion.STATIC
    subject_motions: List[SubjectMotion] = field(default_factory=list)
    transition_in: Optional[str] = None
    transition_out: Optional[str] = None
    duration_seconds: float = 2.0
    keyframe_count: int = 1

class PromptBuilder:
    """Builds structured prompts for image and motion generation"""
    
    def __init__(self):
        self.default_quality_terms = [
            "high quality",
            "detailed",
            "professional photography",
            "cinematic lighting",
            "8k resolution"
        ]
    
    def build_image_prompt(
        self,
        elements: PromptElements,
        style_template: Optional[Dict] = None
    ) -> str:
        """Build prompt for still image generation"""
        prompt_parts = []
        
        # Add who
        if elements.who:
            prompt_parts.append(f"Focus on {', '.join(elements.who)}")
        
        # Add what
        if elements.what:
            prompt_parts.append(f"Showing {', '.join(elements.what)}")
        
        # Add where
        if elements.where:
            prompt_parts.append(f"In {', '.join(elements.where)}")
        
        # Add when
        if elements.when:
            prompt_parts.append(f"During {', '.join(elements.when)}")
        
        # Add how (style/mood)
        if elements.how:
            prompt_parts.append(f"With {', '.join(elements.how)}")
        
        # Add why (if it affects visual elements)
        if elements.why:
            prompt_parts.append(f"Conveying {', '.join(elements.why)}")
        
        # Add style template elements if provided
        if style_template:
            if 'base_prompt' in style_template:
                prompt_parts.append(style_template['base_prompt'])
        
        # Add quality terms
        prompt_parts.extend(self.default_quality_terms)
        
        return ", ".join(prompt_parts)
    
    def build_motion_prompt(
        self,
        elements: PromptElements,
        motion: MotionPrompt,
        style_template: Optional[Dict] = None
    ) -> Dict[str, any]:
        """Build structured prompt for motion generation"""
        # Build base image prompt
        base_prompt = self.build_image_prompt(elements, style_template)
        
        # Create motion structure
        motion_data = {
            "base_prompt": base_prompt,
            "motion_type": motion.motion_type.value,
            "camera_motion": {
                "type": motion.camera_motion.value,
                "duration": motion.duration_seconds,
                "keyframes": motion.keyframe_count
            },
            "subject_motions": [
                {
                    "who": m.who,
                    "action": m.action,
                    "direction": m.direction,
                    "speed": m.speed,
                    "intensity": m.intensity
                }
                for m in motion.subject_motions
            ],
            "transitions": {
                "in": motion.transition_in,
                "out": motion.transition_out
            }
        }
        
        # Add style elements
        if style_template:
            motion_data["style"] = style_template
            
        return motion_data
    
    @staticmethod
    def extract_elements_from_scene(scene) -> PromptElements:
        """Extract prompt elements from a scene object"""
        elements = PromptElements()
        
        # Extract who (characters and key objects)
        elements.who = [char.name for char in scene.characters]
        
        # Extract what (actions)
        for action in scene.action_descriptions:
            elements.what.append(action)
        
        # Extract where (location details)
        elements.where = [
            scene.location.name,
            scene.location.setting_type,
            scene.location.description
        ]
        
        # Extract when (time and conditions)
        elements.when = [
            scene.location.time_of_day.value,
            # Add any weather or temporal descriptions
        ]
        
        # Extract how (style and mood)
        elements.how = [
            scene.visual_style.tone.value,
            scene.visual_style.lighting,
            *scene.visual_style.atmosphere_keywords
        ]
        
        return elements
    
    @staticmethod
    def extract_motion_from_scene(scene) -> MotionPrompt:
        """Extract motion information from a scene object"""
        motion = MotionPrompt()
        
        # Analyze action descriptions for motion
        has_camera_motion = False
        has_subject_motion = False
        
        # Extract camera movements
        for action in scene.action_descriptions:
            for cam_motion in CameraMotion:
                if cam_motion.value in action.lower():
                    motion.camera_motion = cam_motion
                    has_camera_motion = True
                    break
        
        # Extract subject movements
        for action in scene.action_descriptions:
            for character in scene.characters:
                if character.name in action:
                    subject_motion = SubjectMotion(
                        who=character.name,
                        action=action
                    )
                    motion.subject_motions.append(subject_motion)
                    has_subject_motion = True
        
        # Set motion type based on findings
        if has_camera_motion and has_subject_motion:
            motion.motion_type = MotionType.BOTH
        elif has_camera_motion:
            motion.motion_type = MotionType.CAMERA_MOVE
        elif has_subject_motion:
            motion.motion_type = MotionType.SUBJECT_MOVE
        
        # Set transitions
        if scene.transitions:
            motion.transition_out = scene.transitions[-1]
        
        return motion