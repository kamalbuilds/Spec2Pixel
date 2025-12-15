"""
Enhanced BRIA FIBO Pipeline with Production Features
Includes error handling, batch processing, JSON diff visualization, and more.
"""

import os
import json
import time
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
from dotenv import load_dotenv
import requests
from PIL import Image
import io
import base64
from functools import wraps
import hashlib

# Load environment variables
load_dotenv()

# Configuration
class Config:
    API_TOKEN = os.getenv("BRIA_API_TOKEN")
    API_URL = os.getenv("BRIA_API_URL", "https://engine.prod.bria-api.com/v2")
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
    POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "5"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "300"))
    ENABLE_HDR = os.getenv("ENABLE_HDR", "false").lower() == "true"
    ENABLE_16BIT = os.getenv("ENABLE_16BIT", "false").lower() == "true"
    ENABLE_BATCH_PROCESSING = os.getenv("ENABLE_BATCH_PROCESSING", "true").lower() == "true"
    MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "5"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "pipeline.log")

# Setup logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Data Classes
@dataclass
class RefinementStep:
    """Represents a single refinement step in the chain"""
    prompt: str
    description: str
    params: Optional[Dict[str, Any]] = None

@dataclass
class PipelineResult:
    """Result of pipeline execution"""
    success: bool
    image_url: Optional[str] = None
    structured_prompt: Optional[Dict] = None
    refinement_history: List[Dict] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict] = None

@dataclass
class ParameterPreset:
    """Predefined parameter sets for common use cases"""
    name: str
    description: str
    parameters: Dict[str, Any]

# Preset Management
class PresetManager:
    """Manages parameter presets for quick configuration"""

    PRESETS = {
        "photorealistic": ParameterPreset(
            "photorealistic",
            "Ultra-realistic photography settings",
            {
                "style_medium": "photograph",
                "lighting": {"conditions": "natural light", "quality": "soft"},
                "camera": {"angle": "eye level", "shot": "medium shot"},
                "quality": "high resolution, 8k, detailed"
            }
        ),
        "cinematic": ParameterPreset(
            "cinematic",
            "Cinematic film-like appearance",
            {
                "style_medium": "cinematic",
                "lighting": {"conditions": "dramatic lighting", "quality": "volumetric"},
                "camera": {"angle": "low angle", "shot": "wide shot"},
                "mood": "epic, dramatic",
                "color_palette": "teal and orange"
            }
        ),
        "artistic": ParameterPreset(
            "artistic",
            "Artistic illustration style",
            {
                "style_medium": "digital illustration",
                "artistic_style": "impressionist",
                "color_palette": "vibrant colors",
                "brushwork": "expressive"
            }
        ),
        "hdr": ParameterPreset(
            "hdr",
            "High Dynamic Range settings",
            {
                "style_medium": "photograph",
                "lighting": {"conditions": "HDR", "quality": "high dynamic range"},
                "technical": {"bit_depth": "16-bit", "color_space": "ProPhoto RGB"},
                "quality": "ultra high resolution, HDR, 16-bit color"
            }
        )
    }

    @classmethod
    def get_preset(cls, name: str) -> Optional[ParameterPreset]:
        return cls.PRESETS.get(name)

    @classmethod
    def list_presets(cls) -> List[str]:
        return list(cls.PRESETS.keys())

    @classmethod
    def apply_preset(cls, structured_prompt: Dict, preset_name: str) -> Dict:
        """Apply a preset to a structured prompt"""
        preset = cls.get_preset(preset_name)
        if not preset:
            raise ValueError(f"Preset '{preset_name}' not found")

        # Deep merge preset parameters into structured prompt
        result = json.loads(json.dumps(structured_prompt))  # Deep copy
        for key, value in preset.parameters.items():
            if isinstance(value, dict) and key in result:
                result[key].update(value)
            else:
                result[key] = value

        return result

# Error Handling Decorators
def retry_with_backoff(max_retries: int = None, delay: int = None):
    """Decorator for retrying functions with exponential backoff"""
    max_retries = max_retries or Config.MAX_RETRIES
    delay = delay or Config.RETRY_DELAY

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"All {max_retries} attempts failed: {e}")
            raise last_exception
        return wrapper
    return decorator

# Enhanced Pipeline Class
class EnhancedBRIAPipeline:
    """Enhanced BRIA FIBO Pipeline with production features"""

    def __init__(self):
        if not Config.API_TOKEN:
            raise ValueError("BRIA_API_TOKEN not found in environment variables")

        self.headers = {
            "api_token": Config.API_TOKEN,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    @retry_with_backoff()
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic"""
        url = f"{Config.API_URL}/{endpoint}"
        response = self.session.request(
            method, url,
            timeout=Config.REQUEST_TIMEOUT,
            **kwargs
        )
        response.raise_for_status()
        return response

    def poll_status_enhanced(self, status_url: str, timeout: int = None) -> Optional[Dict]:
        """Enhanced polling with timeout and better error handling"""
        timeout = timeout or Config.REQUEST_TIMEOUT
        start_time = time.time()

        while True:
            if time.time() - start_time > timeout:
                logger.error(f"Polling timeout after {timeout} seconds")
                return None

            try:
                response = self.session.get(status_url, headers=self.headers)
                if response.status_code == 200:
                    result = response.json()
                    status = result.get('status')

                    if status == 'completed':
                        logger.info("Request completed successfully")
                        return result
                    elif status in ['failed', 'blocked']:
                        logger.error(f"Request {status}: {result}")
                        return None
                    else:
                        logger.debug(f"Status: {status}. Waiting...")

            except Exception as e:
                logger.warning(f"Error polling status: {e}")

            time.sleep(Config.POLLING_INTERVAL)

    def generate_structured_prompt(self, prompt: str,
                                  structured_prompt: Optional[Dict] = None,
                                  preset: Optional[str] = None) -> Optional[Dict]:
        """Generate or refine structured prompt with preset support"""
        logger.info(f"Generating structured prompt: {prompt[:50]}...")

        payload = {"prompt": prompt}
        if structured_prompt:
            payload["structured_prompt"] = structured_prompt

        try:
            response = self._make_request(
                "POST",
                "structured_prompt/generate",
                data=json.dumps(payload)
            )

            if response.status_code == 202:
                status_url = response.json().get('status_url')
                result = self.poll_status_enhanced(status_url)

                if result and result.get('result'):
                    structured = json.loads(result['result']['structured_prompt'])

                    # Apply preset if specified
                    if preset:
                        structured = PresetManager.apply_preset(structured, preset)

                    return structured

        except Exception as e:
            logger.error(f"Failed to generate structured prompt: {e}")

        return None

    def multi_step_refinement(self, initial_prompt: str,
                            refinement_steps: List[RefinementStep]) -> PipelineResult:
        """Execute multiple refinement steps in sequence"""
        logger.info(f"Starting multi-step refinement with {len(refinement_steps)} steps")

        refinement_history = []
        current_prompt = None
        execution_start = time.time()

        try:
            # Initial generation
            current_prompt = self.generate_structured_prompt(initial_prompt)
            if not current_prompt:
                return PipelineResult(
                    success=False,
                    error="Failed to generate initial prompt"
                )

            refinement_history.append({
                "step": 0,
                "type": "initial",
                "prompt": initial_prompt,
                "structured_prompt": current_prompt
            })

            # Apply refinement steps
            for idx, step in enumerate(refinement_steps, 1):
                logger.info(f"Applying refinement step {idx}: {step.description}")

                # Apply preset if specified in params
                if step.params and 'preset' in step.params:
                    current_prompt = PresetManager.apply_preset(
                        current_prompt,
                        step.params['preset']
                    )

                # Refine with VLM
                refined = self.generate_structured_prompt(
                    step.prompt,
                    structured_prompt=current_prompt
                )

                if not refined:
                    logger.warning(f"Refinement step {idx} failed")
                    continue

                # Store diff
                diff = self.generate_json_diff(current_prompt, refined)
                refinement_history.append({
                    "step": idx,
                    "type": "refinement",
                    "prompt": step.prompt,
                    "description": step.description,
                    "diff": diff,
                    "structured_prompt": refined
                })

                current_prompt = refined

            # Generate final image
            image_url = self.generate_image_from_structured(current_prompt)

            execution_time = time.time() - execution_start

            return PipelineResult(
                success=bool(image_url),
                image_url=image_url,
                structured_prompt=current_prompt,
                refinement_history=refinement_history,
                execution_time=execution_time,
                metadata={
                    "total_steps": len(refinement_steps) + 1,
                    "hdr_enabled": Config.ENABLE_HDR,
                    "16bit_enabled": Config.ENABLE_16BIT
                }
            )

        except Exception as e:
            logger.error(f"Multi-step refinement failed: {e}")
            return PipelineResult(
                success=False,
                error=str(e),
                refinement_history=refinement_history
            )

    def generate_image_from_structured(self, structured_prompt: Dict,
                                      aspect_ratio: str = "1:1") -> Optional[str]:
        """Generate image from structured prompt with HDR/16-bit support"""
        logger.info("Generating final image...")

        # Add HDR/16-bit parameters if enabled
        if Config.ENABLE_HDR or Config.ENABLE_16BIT:
            technical = structured_prompt.get("technical", {})
            if Config.ENABLE_HDR:
                technical["hdr"] = True
                technical["tone_mapping"] = "reinhard"
            if Config.ENABLE_16BIT:
                technical["bit_depth"] = "16-bit"
                technical["color_space"] = "ProPhoto RGB"
            structured_prompt["technical"] = technical

        payload = {
            "structured_prompt": json.dumps(structured_prompt),
            "aspect_ratio": aspect_ratio
        }

        try:
            response = self._make_request(
                "POST",
                "image/generate",
                data=json.dumps(payload)
            )

            if response.status_code == 202:
                status_url = response.json().get('status_url')
                result = self.poll_status_enhanced(status_url)

                if result and result.get('result'):
                    return result['result'].get('image_url')

        except Exception as e:
            logger.error(f"Failed to generate image: {e}")

        return None

    def batch_process(self, prompts: List[Dict[str, Any]]) -> List[PipelineResult]:
        """Process multiple prompts concurrently"""
        if not Config.ENABLE_BATCH_PROCESSING:
            logger.warning("Batch processing disabled. Processing sequentially.")
            return [self.process_single(p) for p in prompts]

        logger.info(f"Batch processing {len(prompts)} prompts...")
        results = []

        # Process in batches
        for i in range(0, len(prompts), Config.MAX_BATCH_SIZE):
            batch = prompts[i:i + Config.MAX_BATCH_SIZE]

            with ThreadPoolExecutor(max_workers=Config.MAX_BATCH_SIZE) as executor:
                futures = {
                    executor.submit(self.process_single, prompt): idx
                    for idx, prompt in enumerate(batch, start=i)
                }

                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        logger.info(f"Completed prompt {idx + 1}/{len(prompts)}")
                    except Exception as e:
                        logger.error(f"Failed to process prompt {idx}: {e}")
                        results.append(PipelineResult(
                            success=False,
                            error=str(e)
                        ))

        return results

    def process_single(self, prompt_config: Dict[str, Any]) -> PipelineResult:
        """Process a single prompt configuration"""
        initial_prompt = prompt_config.get("prompt")
        refinements = prompt_config.get("refinements", [])
        preset = prompt_config.get("preset")

        if refinements:
            steps = [RefinementStep(**r) if isinstance(r, dict) else r
                    for r in refinements]
            return self.multi_step_refinement(initial_prompt, steps)
        else:
            # Simple generation
            structured = self.generate_structured_prompt(initial_prompt, preset=preset)
            if structured:
                image_url = self.generate_image_from_structured(structured)
                return PipelineResult(
                    success=bool(image_url),
                    image_url=image_url,
                    structured_prompt=structured
                )
            return PipelineResult(success=False, error="Failed to generate structured prompt")

    @staticmethod
    def generate_json_diff(original: Dict, modified: Dict) -> Dict:
        """Generate a visual diff between two JSON structures"""
        original_str = json.dumps(original, indent=2, sort_keys=True)
        modified_str = json.dumps(modified, indent=2, sort_keys=True)

        differ = difflib.unified_diff(
            original_str.splitlines(keepends=True),
            modified_str.splitlines(keepends=True),
            fromfile='original',
            tofile='modified'
        )

        changes = []
        for line in differ:
            if line.startswith('+') and not line.startswith('+++'):
                changes.append({"type": "added", "content": line[1:].strip()})
            elif line.startswith('-') and not line.startswith('---'):
                changes.append({"type": "removed", "content": line[1:].strip()})

        return {
            "summary": f"{len(changes)} changes",
            "changes": changes[:10]  # Limit to first 10 changes
        }

    def save_results(self, result: PipelineResult, output_dir: str = "output"):
        """Save pipeline results to disk"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save structured prompt
        if result.structured_prompt:
            prompt_file = output_path / f"prompt_{timestamp}.json"
            with open(prompt_file, 'w') as f:
                json.dump(result.structured_prompt, f, indent=2)
            logger.info(f"Saved structured prompt to {prompt_file}")

        # Save refinement history
        if result.refinement_history:
            history_file = output_path / f"history_{timestamp}.json"
            with open(history_file, 'w') as f:
                json.dump(result.refinement_history, f, indent=2)
            logger.info(f"Saved refinement history to {history_file}")

        # Download and save image
        if result.image_url:
            try:
                response = requests.get(result.image_url)
                if response.status_code == 200:
                    image_file = output_path / f"image_{timestamp}.png"
                    with open(image_file, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"Saved image to {image_file}")
            except Exception as e:
                logger.error(f"Failed to download image: {e}")

    def visualize_refinement_history(self, history: List[Dict]) -> str:
        """Create a text visualization of refinement history"""
        output = []
        output.append("=" * 60)
        output.append("REFINEMENT HISTORY VISUALIZATION")
        output.append("=" * 60)

        for entry in history:
            output.append(f"\nStep {entry['step']}: {entry['type'].upper()}")
            output.append("-" * 40)

            if 'prompt' in entry:
                output.append(f"Prompt: {entry['prompt'][:100]}...")

            if 'description' in entry:
                output.append(f"Description: {entry['description']}")

            if 'diff' in entry and entry['diff']:
                output.append(f"Changes: {entry['diff']['summary']}")
                for change in entry['diff']['changes'][:3]:
                    symbol = "+" if change['type'] == 'added' else "-"
                    output.append(f"  {symbol} {change['content'][:60]}...")

        return "\n".join(output)

# Demo and Testing Functions
def demo_simple_generation():
    """Demo: Simple image generation"""
    pipeline = EnhancedBRIAPipeline()

    result = pipeline.process_single({
        "prompt": "A majestic eagle soaring through clouds at sunset",
        "preset": "cinematic"
    })

    if result.success:
        logger.info(f"✅ Image generated: {result.image_url}")
        pipeline.save_results(result)
    else:
        logger.error(f"❌ Generation failed: {result.error}")

    return result

def demo_multi_step_refinement():
    """Demo: Multi-step refinement chain"""
    pipeline = EnhancedBRIAPipeline()

    initial_prompt = "A cozy coffee shop interior"
    refinement_steps = [
        RefinementStep(
            "Add warm morning sunlight streaming through windows",
            "Adding lighting"
        ),
        RefinementStep(
            "Place vintage decorations and plants",
            "Adding decorative elements"
        ),
        RefinementStep(
            "Make it more photorealistic with high detail",
            "Enhancing realism",
            {"preset": "photorealistic"}
        )
    ]

    result = pipeline.multi_step_refinement(initial_prompt, refinement_steps)

    if result.success:
        logger.info(f"✅ Multi-step refinement complete: {result.image_url}")
        logger.info(f"⏱️ Execution time: {result.execution_time:.2f}s")

        # Visualize history
        visualization = pipeline.visualize_refinement_history(result.refinement_history)
        print(visualization)

        pipeline.save_results(result)
    else:
        logger.error(f"❌ Refinement failed: {result.error}")

    return result

def demo_batch_processing():
    """Demo: Batch processing multiple prompts"""
    pipeline = EnhancedBRIAPipeline()

    prompts = [
        {
            "prompt": "A futuristic city skyline at night",
            "preset": "cinematic"
        },
        {
            "prompt": "A serene mountain landscape",
            "preset": "photorealistic"
        },
        {
            "prompt": "Abstract colorful patterns",
            "preset": "artistic"
        }
    ]

    results = pipeline.batch_process(prompts)

    success_count = sum(1 for r in results if r.success)
    logger.info(f"Batch processing complete: {success_count}/{len(results)} successful")

    for i, result in enumerate(results):
        if result.success:
            logger.info(f"  ✅ Prompt {i+1}: {result.image_url}")
            pipeline.save_results(result, f"output/batch_{i+1}")
        else:
            logger.error(f"  ❌ Prompt {i+1}: {result.error}")

    return results

def demo_hdr_generation():
    """Demo: HDR/16-bit image generation"""
    # Enable HDR and 16-bit in config
    original_hdr = Config.ENABLE_HDR
    original_16bit = Config.ENABLE_16BIT

    Config.ENABLE_HDR = True
    Config.ENABLE_16BIT = True

    pipeline = EnhancedBRIAPipeline()

    result = pipeline.process_single({
        "prompt": "A dramatic sunset with rich colors and extreme dynamic range",
        "preset": "hdr"
    })

    if result.success:
        logger.info(f"✅ HDR image generated: {result.image_url}")
        logger.info(f"📊 Metadata: {result.metadata}")
        pipeline.save_results(result, "output/hdr")
    else:
        logger.error(f"❌ HDR generation failed: {result.error}")

    # Restore original config
    Config.ENABLE_HDR = original_hdr
    Config.ENABLE_16BIT = original_16bit

    return result

def main():
    """Main execution function"""
    logger.info("=" * 60)
    logger.info("ENHANCED BRIA FIBO PIPELINE - DEMO")
    logger.info("=" * 60)

    print("\n🚀 Starting Enhanced Pipeline Demo...\n")

    # Run demos
    print("1️⃣ Demo: Simple Generation with Preset")
    demo_simple_generation()

    print("\n2️⃣ Demo: Multi-Step Refinement Chain")
    demo_multi_step_refinement()

    print("\n3️⃣ Demo: Batch Processing")
    demo_batch_processing()

    print("\n4️⃣ Demo: HDR/16-bit Generation")
    demo_hdr_generation()

    print("\n✅ All demos complete! Check the output/ directory for results.")
    print("📝 Logs saved to:", Config.LOG_FILE)

if __name__ == "__main__":
    main()