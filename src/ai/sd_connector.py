from typing import Dict, List, Optional, Union
import base64
from dataclasses import dataclass
import json
import aiohttp
import asyncio
from PIL import Image
import io

@dataclass
class SDGenerationParams:
    """Parameters for Stable Diffusion generation"""
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 576  # 16:9 aspect ratio
    num_inference_steps: int = 50
    guidance_scale: float = 7.5
    seed: Optional[int] = None

@dataclass
class SDResponse:
    """Response from Stable Diffusion API"""
    images: List[Image.Image]
    parameters: Dict
    info: Dict

class StableDiffusionConnector:
    """Handles communication with Stable Diffusion API"""
    
    def __init__(self, api_url: str, api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Set up async context"""
        self.session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up async context"""
        if self.session:
            await self.session.close()
            
    async def generate_image(self, params: SDGenerationParams) -> SDResponse:
        """Generate image using Stable Diffusion"""
        if not self.session:
            raise RuntimeError("Connector must be used as async context manager")
            
        payload = {
            "prompt": params.prompt,
            "negative_prompt": params.negative_prompt,
            "width": params.width,
            "height": params.height,
            "num_inference_steps": params.num_inference_steps,
            "guidance_scale": params.guidance_scale,
            "seed": params.seed
        }
        
        try:
            async with self.session.post(f"{self.api_url}/txt2img", json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(f"API request failed: {await response.text()}")
                    
                result = await response.json()
                
                # Convert base64 images to PIL Images
                images = []
                for img_data in result["images"]:
                    image_bytes = base64.b64decode(img_data)
                    img = Image.open(io.BytesIO(image_bytes))
                    images.append(img)
                    
                return SDResponse(
                    images=images,
                    parameters=result.get("parameters", {}),
                    info=result.get("info", {})
                )
                
        except Exception as e:
            raise RuntimeError(f"Failed to generate image: {str(e)}")
            
    async def generate_sequence(
        self,
        prompts: List[str],
        base_params: SDGenerationParams,
        maintain_consistency: bool = True
    ) -> List[SDResponse]:
        """Generate a sequence of images with optional consistency"""
        responses = []
        last_seed = base_params.seed
        
        for prompt in prompts:
            # Update params for this generation
            params = SDGenerationParams(
                prompt=prompt,
                negative_prompt=base_params.negative_prompt,
                width=base_params.width,
                height=base_params.height,
                num_inference_steps=base_params.num_inference_steps,
                guidance_scale=base_params.guidance_scale,
                seed=last_seed if maintain_consistency else None
            )
            
            response = await self.generate_image(params)
            responses.append(response)
            
            # Update seed for consistency if needed
            if maintain_consistency and len(response.images) > 0:
                last_seed = int(response.info.get("seed", last_seed))
                
        return responses
        
    async def interpolate_frames(
        self,
        keyframe1: Image.Image,
        keyframe2: Image.Image,
        num_frames: int
    ) -> List[Image.Image]:
        """Generate interpolated frames between two keyframes"""
        if not self.session:
            raise RuntimeError("Connector must be used as async context manager")
            
        # Convert images to base64
        buffer1 = io.BytesIO()
        buffer2 = io.BytesIO()
        keyframe1.save(buffer1, format='PNG')
        keyframe2.save(buffer2, format='PNG')
        
        payload = {
            "image1": base64.b64encode(buffer1.getvalue()).decode('utf-8'),
            "image2": base64.b64encode(buffer2.getvalue()).decode('utf-8'),
            "num_frames": num_frames
        }
        
        try:
            async with self.session.post(f"{self.api_url}/interpolate", json=payload) as response:
                if response.status != 200:
                    raise RuntimeError(f"Frame interpolation failed: {await response.text()}")
                    
                result = await response.json()
                
                # Convert base64 frames to PIL Images
                frames = []
                for frame_data in result["frames"]:
                    frame_bytes = base64.b64decode(frame_data)
                    frame = Image.open(io.BytesIO(frame_bytes))
                    frames.append(frame)
                    
                return frames
                
        except Exception as e:
            raise RuntimeError(f"Failed to interpolate frames: {str(e)}")
            
    def save_response(self, response: SDResponse, output_dir: str, prefix: str = "frame"):
        """Save generated images to disk"""
        os.makedirs(output_dir, exist_ok=True)
        
        for i, image in enumerate(response.images):
            filename = f"{prefix}_{i:04d}.png"
            path = os.path.join(output_dir, filename)
            image.save(path, "PNG")
            
            # Save metadata
            meta_filename = f"{prefix}_{i:04d}_meta.json"
            meta_path = os.path.join(output_dir, meta_filename)
            metadata = {
                "parameters": response.parameters,
                "info": response.info
            }
            with open(meta_path, 'w') as f:
                json.dump(metadata, f, indent=4)