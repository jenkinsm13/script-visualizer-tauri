import re
from typing import List, Optional, Dict, Tuple
from pathlib import Path
import logging
from .scene import (Scene, Character, Location, VisualStyle, TimeOfDay, Weather,
                   VisualTone, Emotion, CharacterState, CameraSetup, ActionBeat)
from .prompt_structure import PromptElements, MotionPrompt

class ScriptParser:
    """Enhanced parser for screenplay formats with detailed visual and motion analysis"""
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        
        # Core screenplay patterns
        self.patterns = {
            'scene_header': r'^(?:(?:\d+\s+)?)(INT\.|EXT\.|INT\/EXT\.)\s+(.*?)(?:\s*-\s*|\s+)(\w+(?:\s+\w+)*?)(?:\s*$|\s*-)',
            'character': r'^\s*([A-Z][A-Z\s\-\']+)(?:\s*\(.*\))?\s*$',
            'parenthetical': r'^\s*\((.*?)\)\s*$',
            'dialogue': r'^\s*(?!>)((?!EXT\.|INT\.).+)$',
            'transition': r'^\s*(CUT TO:|FADE OUT|FADE IN|DISSOLVE TO:)',
            'action': r'^(?!\s*>)(.+)$'
        }
        
        # Visual analysis patterns
        self.visual_patterns = {
            'time': {
                TimeOfDay.DAWN: r'\b(dawn|sunrise|early\s+morning)\b',
                TimeOfDay.MORNING: r'\b(morning|breakfast\s+time)\b',
                TimeOfDay.DAY: r'\b(day|daylight|noon|afternoon)\b',
                TimeOfDay.DUSK: r'\b(dusk|sunset|twilight|evening)\b',
                TimeOfDay.NIGHT: r'\b(night|midnight|darkness)\b'
            },
            'weather': {
                Weather.CLEAR: r'\b(clear|sunny|bright)\b',
                Weather.CLOUDY: r'\b(cloudy|overcast|grey\s+skies)\b',
                Weather.RAINY: r'\b(rain|drizzle|downpour)\b',
                Weather.STORMY: r'\b(storm|thunder|lightning)\b',
                Weather.SNOWY: r'\b(snow|blizzard|flurries)\b',
                Weather.FOGGY: r'\b(fog|mist|haze)\b'
            },
            'tone': {
                VisualTone.BRIGHT: r'\b(bright|vibrant|luminous)\b',
                VisualTone.DARK: r'\b(dark|shadowy|dim)\b',
                VisualTone.HIGH_CONTRAST: r'\b(stark|harsh|dramatic)\b',
                VisualTone.SOFT: r'\b(soft|gentle|muted)\b',
                VisualTone.WARM: r'\b(warm|golden|amber)\b',
                VisualTone.COOL: r'\b(cool|blue|steel)\b'
            }
        }
        
        # Motion and action patterns
        self.motion_patterns = {
            'camera_moves': {
                'dolly': r'\b(dolly|move|push)\s+(in|out)\b',
                'pan': r'\b(pan|sweep)\s+(left|right)\b',
                'tilt': r'\b(tilt|look)\s+(up|down)\b',
                'crane': r'\b(crane|boom)\s+(up|down)\b',
                'track': r'\btrack(ing)?\b',
                'steadicam': r'\b(steadicam|handheld)\b'
            },
            'shot_sizes': {
                'close': r'\b(close|cu|ecu|tight)\b',
                'medium': r'\b(medium|ms|bust)\b',
                'wide': r'\b(wide|ws|long|master)\b'
            },
            'angles': {
                'high': r'\b(high|above|overhead)\b',
                'low': r'\b(low|below|upward)\b',
                'dutch': r'\b(dutch|tilted|canted)\b'
            },
            'movement_speed': {
                'slow': r'\b(slow|gentle|gradual)\b',
                'fast': r'\b(fast|quick|rapid)\b',
                'normal': r'\b(steady|smooth)\b'
            }
        }
        
        # Character action and emotion patterns
        self.character_patterns = {
            'emotions': {
                Emotion.HAPPY: r'\b(smiles?|laughs?|happy|joyful)\b',
                Emotion.SAD: r'\b(sad|crying|tears|depressed)\b',
                Emotion.ANGRY: r'\b(angry|furious|rage|scowls?)\b',
                Emotion.FEARFUL: r'\b(scared|afraid|trembling|nervous)\b',
                Emotion.SURPRISED: r'\b(surprised|shocked|startled)\b',
                Emotion.TENSE: r'\b(tense|anxious|worried)\b',
                Emotion.PEACEFUL: r'\b(calm|relaxed|peaceful)\b'
            },
            'movement': r'\b(walks?|runs?|sits?|stands?|turns?|moves?)\b',
            'intensity': {
                'subtle': r'\b(slightly|barely|gently)\b',
                'intense': r'\b(violently|forcefully|intensely)\b'
            },
            'direction': r'\b(towards?|away|left|right|up|down)\b'
        }
    
    def parse_script(self, content: str) -> List[Scene]:
        """Parse entire script content into scenes"""
        scenes = []
        current_scene_lines = []
        scene_count = 0
        
        # Clean and split content
        lines = self._clean_content(content).split('\n')
        
        for line in lines:
            # Check for scene header
            if self._is_scene_header(line):
                # Process previous scene if it exists
                if current_scene_lines:
                    scene = self._parse_scene(current_scene_lines, scene_count)
                    if scene:
                        scenes.append(scene)
                        scene_count += 1
                    current_scene_lines = []
                
                current_scene_lines.append(line)
            else:
                # Add line to current scene
                if line.strip():
                    current_scene_lines.append(line)
        
        # Process the last scene
        if current_scene_lines:
            scene = self._parse_scene(current_scene_lines, scene_count)
            if scene:
                scenes.append(scene)
        
        self.logger.info(f"Parsed {len(scenes)} scenes from script")
        return scenes
        
    def _clean_content(self, content: str) -> str:
        """Clean script content for parsing"""
        # Remove multiple empty lines
        content = re.sub(r'\n\s*\n', '\n\n', content)
        
        # Remove page breaks and numbers
        content = re.sub(r'\f', '', content)
        content = re.sub(r'^\s*\d+\.\s*$', '', content, flags=re.MULTILINE)
        
        # Remove header/footer text
        content = re.sub(r'^\s*CONTINUED:', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*\(CONTINUED\)\s*$', '', content, flags=re.MULTILINE)
        
        return content.strip()
        
    def _parse_scene(self, lines: List[str], scene_number: int) -> Optional[Scene]:
        """Parse scene lines into a Scene object with enhanced visual analysis"""
        try:
            # Parse scene header
            header_match = re.match(self.patterns['scene_header'], lines[0].strip())
            if not header_match:
                return None
                
            setting_type, location_desc, time_desc = header_match.groups()
            
            # Initialize scene elements
            location = self._parse_location(setting_type.strip('.'), location_desc, time_desc)
            characters = []
            dialogue = []
            beats = []
            transitions = []
            
            # Track current state
            current_character = None
            current_beat = None
            current_camera = CameraSetup()
            
            # Process lines
            for line in lines[1:]:
                line = line.strip()
                
                # Check for character cue
                char_match = re.match(self.patterns['character'], line)
                if char_match:
                    char_name = char_match.group(1).strip()
                    current_character = self._get_or_create_character(char_name, characters)
                    continue
                
                # Check for dialogue
                if current_character and not re.match(self.patterns['parenthetical'], line):
                    if re.match(self.patterns['dialogue'], line):
                        dialogue.append((current_character.name, line))
                        # Update character emotion from dialogue
                        self._analyze_character_emotion(current_character, line)
                        continue
                
                # Check for parenthetical
                paren_match = re.match(self.patterns['parenthetical'], line)
                if paren_match and current_character:
                    self._analyze_character_action(current_character, paren_match.group(1))
                    continue
                
                # Check for transition
                if re.match(self.patterns['transition'], line):
                    transitions.append(line)
                    if current_beat:
                        current_beat.transitions.append(line)
                    continue
                
                # Action line - create new beat
                if line and not re.match(self.patterns['parenthetical'], line):
                    camera_setup = self._analyze_camera_setup(line)
                    if camera_setup:
                        current_camera = camera_setup
                    
                    current_beat = ActionBeat(
                        description=line,
                        characters=characters.copy(),
                        camera=current_camera,
                        duration=self._estimate_beat_duration(line)
                    )
                    
                    # Analyze character actions in the beat
                    for char in characters:
                        if char.name in line:
                            self._analyze_character_action(char, line)
                    
                    beats.append(current_beat)
                    current_character = None
            
            # Create visual style from accumulated information
            visual_style = self._analyze_visual_style(beats, location)
            
            # Create scene object
            scene = Scene(
                number=scene_number + 1,
                heading=lines[0].strip(),
                location=location,
                characters=characters,
                beats=beats,
                visual_style=visual_style,
                dialogue=dialogue,
                transitions=transitions
            )
            
            # Generate prompt elements
            scene.prompt_elements = scene.get_prompt_elements()
            scene.motion_prompts = scene.get_motion_prompts()
            
            return scene
            
        except Exception as e:
            self.logger.error(f"Error parsing scene {scene_number}: {str(e)}")
            return None
            
    def _parse_location(self, setting_type: str, location: str, time: str) -> Location:
        """Parse enhanced location information"""
        # Detect time of day
        time_of_day = TimeOfDay.UNKNOWN
        for tod, pattern in self.visual_patterns['time'].items():
            if re.search(pattern, time, re.IGNORECASE):
                time_of_day = tod
                break
        
        # Detect weather
        weather = Weather.UNKNOWN
        for w, pattern in self.visual_patterns['weather'].items():
            if re.search(pattern, location + " " + time, re.IGNORECASE):
                weather = w
                break
        
        return Location(
            name=location,
            setting_type=setting_type,
            description=f"{setting_type} {location} - {time}",
            time_of_day=time_of_day,
            weather=weather
        )
        
    def _analyze_camera_setup(self, line: str) -> Optional[CameraSetup]:
        """Analyze line for camera setup information"""
        setup = CameraSetup()
        
        # Check for camera movements
        for move_type, pattern in self.motion_patterns['camera_moves'].items():
            if re.search(pattern, line, re.IGNORECASE):
                setup.movement = move_type
                # Extract direction
                direction_match = re.search(r'\b(in|out|left|right|up|down)\b', line)
                if direction_match:
                    setup.movement_direction = direction_match.group(1)
        
        # Check for shot sizes
        for size, pattern in self.motion_patterns['shot_sizes'].items():
            if re.search(pattern, line, re.IGNORECASE):
                setup.shot_size = size
                
        # Check for angles
        for angle, pattern in self.motion_patterns['angles'].items():
            if re.search(pattern, line, re.IGNORECASE):
                setup.angle = angle
                
        # Check for movement speed
        for speed, pattern in self.motion_patterns['movement_speed'].items():
            if re.search(pattern, line, re.IGNORECASE):
                setup.movement_speed = speed
        
        return setup if setup.movement != "static" or setup.angle != "eye level" else None
        
    def _analyze_character_action(self, character: Character, text: str):
        """Analyze character action and update state"""
        state = CharacterState()
        
        # Check for movement
        movement_match = re.search(self.character_patterns['movement'], text, re.IGNORECASE)
        if movement_match:
            state.motion = movement_match.group(0)
            
            # Check direction
            direction_match = re.search(self.character_patterns['direction'], text, re.IGNORECASE)
            if direction_match:
                state.direction = direction_match.group(0)
            
            # Check intensity
            for intensity, pattern in self.character_patterns['intensity'].items():
                if re.search(pattern, text, re.IGNORECASE):
                    state.intensity = intensity
                    break
        
        # Update character state
        character.state = state
        
    def _analyze_character_emotion(self, character: Character, text: str):
        """Analyze character emotion from dialogue or action"""
        for emotion, pattern in self.character_patterns['emotions'].items():
            if re.search(pattern, text, re.IGNORECASE):
                character.state.emotion = emotion
                break
                
    def _estimate_beat_duration(self, text: str) -> float:
        """Estimate duration of an action beat in seconds"""
        # Basic estimation based on text length and content
        base_duration = 2.0  # Default duration
        
        # Adjust for action complexity
        word_count = len(text.split())
        if word_count > 30:
            base_duration += 1.0
        
        # Adjust for camera movement
        if any(re.search(pattern, text, re.IGNORECASE) 
              for patterns in self.motion_patterns['camera_moves'].values() 
              for pattern in [patterns]):
            base_duration += 1.5
            
        return base_duration
        
    def _analyze_visual_style(self, beats: List[ActionBeat], location: Location) -> VisualStyle:
        """Analyze beats to determine overall visual style"""
        style = VisualStyle()
        
        # Combine all text for analysis
        text = ' '.join([beat.description for beat in beats])
        
        # Detect tone
        tone_scores = {tone: 0 for tone in VisualTone}
        for tone, pattern in self.visual_patterns['tone'].items():
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            tone_scores[tone] = matches
            
        style.tone = max(tone_scores.items(), key=lambda x: x[1])[0]
        
        # Set additional style elements
        style.lighting_style = self._detect_lighting_style(text)
        style.atmosphere_keywords = self._extract_atmosphere_keywords(text)
        
        return style
        
    def _detect_lighting_style(self, text: str) -> str:
        """Detect lighting style from text"""
        lighting_patterns = {
            'natural': r'\b(natural|sunlight|daylight)\b',
            'artificial': r'\b(fluorescent|lamp|overhead)\b',
            'dramatic': r'\b(dramatic|moody|shadowy)\b',
            'soft': r'\b(soft|diffused|gentle)\b'
        }
        
        for style, pattern in lighting_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                return style
                
        return 'natural'  # default
        
    def _extract_atmosphere_keywords(self, text: str) -> List[str]:
        """Extract keywords that contribute to atmosphere"""
        atmosphere_patterns = [
            r'\b(mysterious|eerie|suspenseful)\b',
            r'\b(romantic|intimate|tender)\b',
            r'\b(chaotic|frenzied|intense)\b',
            r'\b(peaceful|tranquil|serene)\b'
        ]
        
        keywords = []
        for pattern in atmosphere_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            keywords.extend(matches)
            
        return list(set(keywords))  # Remove duplicates