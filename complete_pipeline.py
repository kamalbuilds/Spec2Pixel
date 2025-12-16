"""
Complete BRIA FIBO Pipeline - Production Ready
Integrates all enhanced features with working sync mode for the hackathon.
"""

import os
import json
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
from dotenv import load_dotenv
import requests
from functools import wraps
import hashlib
from enum import Enum

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration management"""
    API_TOKEN = os.getenv("BRIA_API_TOKEN")
    API_URL = os.getenv("BRIA_API_URL", "https://engine.prod.bria-api.com/v2")
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
    RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "180"))
    ENABLE_HDR = os.getenv("ENABLE_HDR", "false").lower() == "true"
    ENABLE_16BIT = os.getenv("ENABLE_16BIT", "false").lower() == "true"
    ENABLE_BATCH_PROCESSING = os.getenv("ENABLE_BATCH_PROCESSING", "true").lower() == "true"
    MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "5"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "pipeline.log")
    USE_SYNC_MODE = os.getenv("USE_SYNC_MODE", "true").lower() == "true"

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

# ============================================================================
# DATA CLASSES
# ============================================================================

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
    refinement_history: Optional[List[Dict]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict] = None

@dataclass
class BatchResult:
    """Result of batch processing"""
    total: int
    successful: int
    failed: int
    results: List[PipelineResult]
    execution_time: float

    @property
    def success_rate(self) -> float:
        return (self.successful / self.total * 100) if self.total > 0 else 0

@dataclass
class ParameterPreset:
    """Predefined parameter sets for common use cases"""
    name: str
    description: str
    parameters: Dict[str, Any]

# ============================================================================
# PRESET MANAGEMENT
# ============================================================================

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
                "quality": "high resolution, 8k, detailed",
                "photographic_characteristics": {
                    "depth_of_field": "shallow",
                    "focus": "sharp focus on subject",
                    "camera_angle": "eye-level",
                    "lens_focal_length": "85mm portrait lens"
                }
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
                "color_palette": "teal and orange",
                "aesthetics": {
                    "composition": "rule of thirds",
                    "color_scheme": "cinematic color grading",
                    "mood_atmosphere": "dramatic, intense"
                }
            }
        ),
        "artistic": ParameterPreset(
            "artistic",
            "Artistic illustration style",
            {
                "style_medium": "digital illustration",
                "artistic_style": "impressionist",
                "color_palette": "vibrant colors",
                "brushwork": "expressive",
                "aesthetics": {
                    "composition": "dynamic",
                    "color_scheme": "bold and vibrant",
                    "mood_atmosphere": "creative, imaginative"
                }
            }
        ),
        "hdr": ParameterPreset(
            "hdr",
            "High Dynamic Range settings",
            {
                "style_medium": "photograph",
                "lighting": {"conditions": "HDR", "quality": "high dynamic range"},
                "technical": {"bit_depth": "16-bit", "color_space": "ProPhoto RGB"},
                "quality": "ultra high resolution, HDR, 16-bit color",
                "photographic_characteristics": {
                    "depth_of_field": "deep",
                    "focus": "tack sharp throughout",
                    "dynamic_range": "extended"
                }
            }
        ),
        "minimalist": ParameterPreset(
            "minimalist",
            "Clean, minimalist aesthetic",
            {
                "style_medium": "photograph",
                "composition": "minimal, clean lines",
                "color_palette": "monochrome or limited palette",
                "background_setting": "simple, uncluttered",
                "aesthetics": {
                    "composition": "negative space, simplicity",
                    "mood_atmosphere": "calm, serene"
                }
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

        def deep_merge(target: Dict, source: Dict) -> Dict:
            for key, value in source.items():
                if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                    deep_merge(target[key], value)
                else:
                    target[key] = value
            return target

        return deep_merge(result, preset.parameters)

# ============================================================================
# ERROR HANDLING
# ============================================================================

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

# ============================================================================
# MAIN PIPELINE CLASS
# ============================================================================

class CompleteBRIAPipeline:
    """Complete BRIA FIBO Pipeline with all production features"""

    def __init__(self):
        if not Config.API_TOKEN:
            raise ValueError("BRIA_API_TOKEN not found in environment variables")

        self.headers = {
            "api_token": Config.API_TOKEN,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        logger.info(f"Pipeline initialized with API Token: {Config.API_TOKEN[:10]}...")
        logger.info(f"Sync mode: {Config.USE_SYNC_MODE}")

    @retry_with_backoff()
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with retry logic"""
        url = f"{Config.API_URL}/{endpoint}"

        # Set timeout if not specified
        if 'timeout' not in kwargs:
            kwargs['timeout'] = Config.REQUEST_TIMEOUT

        logger.debug(f"Making {method} request to {url}")

        response = self.session.request(
            method,
            url,
            **kwargs
        )

        return response

    def generate_structured_prompt(self,
                                  prompt: str,
                                  structured_prompt: Optional[Dict] = None,
                                  preset: Optional[str] = None) -> Optional[Dict]:
        """Generate or refine structured prompt with preset support"""
        logger.info(f"Generating structured prompt: {prompt[:50]}...")

        payload = {
            "prompt": prompt,
            "sync": Config.USE_SYNC_MODE  # Use sync mode for immediate response
        }

        # Add existing structured prompt for refinement
        if structured_prompt:
            if isinstance(structured_prompt, dict):
                payload["structured_prompt"] = json.dumps(structured_prompt)
            else:
                payload["structured_prompt"] = structured_prompt

        try:
            response = self._make_request(
                "POST",
                "structured_prompt/generate",
                data=json.dumps(payload)
            )

            if response.status_code == 200:
                result = response.json()
                if 'result' in result and 'structured_prompt' in result['result']:
                    structured = json.loads(result['result']['structured_prompt'])

                    # Apply preset if specified
                    if preset:
                        structured = PresetManager.apply_preset(structured, preset)

                    logger.info(" Structured prompt generated successfully")
                    return structured
                else:
                    logger.error("No structured_prompt in result")
            else:
                logger.error(f"API Error: {response.status_code}")
                logger.error(f"Response: {response.text}")

        except Exception as e:
            logger.error(f"Failed to generate structured prompt: {e}")
            raise

        return None

    def generate_image(self,
                      structured_prompt: Optional[Dict] = None,
                      prompt: Optional[str] = None,
                      aspect_ratio: str = "1:1",
                      enable_hdr: Optional[bool] = None,
                      enable_16bit: Optional[bool] = None) -> Optional[str]:
        """Generate image with HDR/16-bit support"""
        logger.info("Generating image...")

        # Apply HDR/16-bit if enabled globally or specified
        use_hdr = enable_hdr if enable_hdr is not None else Config.ENABLE_HDR
        use_16bit = enable_16bit if enable_16bit is not None else Config.ENABLE_16BIT

        payload = {
            "sync": Config.USE_SYNC_MODE,
            "aspect_ratio": aspect_ratio
        }

        # Handle structured prompt
        if structured_prompt:
            # Add HDR/16-bit parameters if enabled
            if use_hdr or use_16bit:
                technical = structured_prompt.get("technical", {})
                if use_hdr:
                    technical["hdr"] = True
                    technical["tone_mapping"] = "reinhard"
                if use_16bit:
                    technical["bit_depth"] = "16-bit"
                    technical["color_space"] = "ProPhoto RGB"
                structured_prompt["technical"] = technical

            if isinstance(structured_prompt, dict):
                payload["structured_prompt"] = json.dumps(structured_prompt)
            else:
                payload["structured_prompt"] = structured_prompt
        elif prompt:
            payload["prompt"] = prompt
        else:
            logger.error("No prompt or structured_prompt provided")
            return None

        try:
            response = self._make_request(
                "POST",
                "image/generate",
                data=json.dumps(payload)
            )

            if response.status_code == 200:
                result = response.json()
                if 'result' in result and 'image_url' in result['result']:
                    image_url = result['result']['image_url']
                    logger.info(f" Image generated: {image_url}")
                    return image_url
                else:
                    logger.error("No image_url in result")
            else:
                logger.error(f"API Error: {response.status_code}")
                logger.error(f"Response: {response.text}")

        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            raise

        return None

    def multi_step_refinement(self,
                            initial_prompt: str,
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
                logger.info(f"Step {idx}: {step.description}")

                # Apply preset if specified
                if step.params and 'preset' in step.params:
                    current_prompt = PresetManager.apply_preset(
                        current_prompt,
                        step.params['preset']
                    )
                    logger.info(f"Applied preset: {step.params['preset']}")

                # Refine with VLM
                refined = self.generate_structured_prompt(
                    step.prompt,
                    structured_prompt=current_prompt,
                    preset=step.params.get('preset') if step.params else None
                )

                if refined:
                    # Calculate diff
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
                else:
                    logger.warning(f"Refinement step {idx} failed, skipping")

            # Generate final image
            image_url = self.generate_image(
                structured_prompt=current_prompt,
                enable_hdr=Config.ENABLE_HDR,
                enable_16bit=Config.ENABLE_16BIT
            )

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
                refinement_history=refinement_history,
                execution_time=time.time() - execution_start
            )

    def batch_process(self, prompts: List[Dict[str, Any]]) -> BatchResult:
        """Process multiple prompts with concurrency control"""
        if not Config.ENABLE_BATCH_PROCESSING:
            logger.warning("Batch processing disabled. Processing sequentially.")
            results = [self.process_single(p) for p in prompts]
            return BatchResult(
                total=len(prompts),
                successful=sum(1 for r in results if r.success),
                failed=sum(1 for r in results if not r.success),
                results=results,
                execution_time=sum(r.execution_time for r in results)
            )

        logger.info(f"Batch processing {len(prompts)} prompts...")
        results = []
        execution_start = time.time()

        # Process in batches
        for i in range(0, len(prompts), Config.MAX_BATCH_SIZE):
            batch = prompts[i:i + Config.MAX_BATCH_SIZE]
            logger.info(f"Processing batch {i//Config.MAX_BATCH_SIZE + 1}")

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
                        logger.info(f"Completed prompt {idx + 1}/{len(prompts)}: {'' if result.success else '❌'}")
                    except Exception as e:
                        logger.error(f"Failed to process prompt {idx}: {e}")
                        results.append(PipelineResult(
                            success=False,
                            error=str(e)
                        ))

        execution_time = time.time() - execution_start

        return BatchResult(
            total=len(prompts),
            successful=sum(1 for r in results if r.success),
            failed=sum(1 for r in results if not r.success),
            results=results,
            execution_time=execution_time
        )

    def process_single(self, prompt_config: Dict[str, Any]) -> PipelineResult:
        """Process a single prompt configuration"""
        initial_prompt = prompt_config.get("prompt")
        refinements = prompt_config.get("refinements", [])
        preset = prompt_config.get("preset")
        aspect_ratio = prompt_config.get("aspect_ratio", "1:1")

        if refinements:
            steps = [RefinementStep(**r) if isinstance(r, dict) else r for r in refinements]
            return self.multi_step_refinement(initial_prompt, steps)
        else:
            # Simple generation
            execution_start = time.time()

            # Generate structured prompt with preset
            structured = self.generate_structured_prompt(initial_prompt, preset=preset)
            if structured:
                # Generate image
                image_url = self.generate_image(
                    structured_prompt=structured,
                    aspect_ratio=aspect_ratio
                )

                return PipelineResult(
                    success=bool(image_url),
                    image_url=image_url,
                    structured_prompt=structured,
                    execution_time=time.time() - execution_start
                )

            return PipelineResult(
                success=False,
                error="Failed to generate structured prompt",
                execution_time=time.time() - execution_start
            )

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
                response = requests.get(result.image_url, timeout=30)
                if response.status_code == 200:
                    image_file = output_path / f"image_{timestamp}.png"
                    with open(image_file, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"Saved image to {image_file}")
                    return str(image_file)
            except Exception as e:
                logger.error(f"Failed to download image: {e}")

        return None

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

    def generate_report(self, results: List[PipelineResult]) -> str:
        """Generate a comprehensive report of pipeline results"""
        report = []
        report.append("=" * 60)
        report.append("PIPELINE EXECUTION REPORT")
        report.append("=" * 60)
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Summary statistics
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_time = sum(r.execution_time for r in results)

        report.append(f"\n📊 SUMMARY:")
        report.append(f"  Total Runs: {len(results)}")
        report.append(f"  Successful: {successful} ({successful/len(results)*100:.1f}%)")
        report.append(f"  Failed: {failed}")
        report.append(f"  Total Time: {total_time:.2f}s")
        report.append(f"  Average Time: {total_time/len(results):.2f}s")

        # Detailed results
        report.append(f"\n📝 DETAILED RESULTS:")
        for i, result in enumerate(results, 1):
            status = "" if result.success else "❌"
            report.append(f"\n  {i}. {status} Run #{i}")
            if result.success:
                report.append(f"     Image URL: {result.image_url[:50]}...")
                report.append(f"     Execution Time: {result.execution_time:.2f}s")
                if result.metadata:
                    report.append(f"     Metadata: {result.metadata}")
            else:
                report.append(f"     Error: {result.error}")

        report.append("\n" + "=" * 60)
        return "\n".join(report)

# ============================================================================
# DEMO FUNCTIONS
# ============================================================================

def demo_simple_generation():
    """Demo: Simple image generation with preset"""
    print("\n" + "=" * 60)
    print("DEMO: Simple Generation with Preset")
    print("=" * 60)

    pipeline = CompleteBRIAPipeline()

    result = pipeline.process_single({
        "prompt": "A majestic eagle soaring through clouds at sunset",
        "preset": "cinematic"
    })

    if result.success:
        print(f" Image generated: {result.image_url}")
        print(f"⏱️ Time: {result.execution_time:.2f}s")
        pipeline.save_results(result)
    else:
        print(f"❌ Failed: {result.error}")

    return result

def demo_multi_step_refinement():
    """Demo: Multi-step refinement with presets"""
    print("\n" + "=" * 60)
    print("DEMO: Multi-Step Refinement Chain")
    print("=" * 60)

    pipeline = CompleteBRIAPipeline()

    initial_prompt = "A serene mountain landscape"
    refinement_steps = [
        RefinementStep(
            "Add a dramatic sunset with golden hour lighting",
            "Step 1: Adding sunset lighting"
        ),
        RefinementStep(
            "Add a small cabin with smoke coming from chimney",
            "Step 2: Adding cabin element"
        ),
        RefinementStep(
            "Make it more photorealistic with high detail",
            "Step 3: Enhancing realism",
            {"preset": "photorealistic"}
        )
    ]

    result = pipeline.multi_step_refinement(initial_prompt, refinement_steps)

    if result.success:
        print(f" Multi-step refinement complete!")
        print(f"🖼️ Image: {result.image_url}")
        print(f"⏱️ Total time: {result.execution_time:.2f}s")

        # Show refinement history
        visualization = pipeline.visualize_refinement_history(result.refinement_history)
        print("\n" + visualization)

        pipeline.save_results(result)
    else:
        print(f"❌ Failed: {result.error}")

    return result

def demo_batch_processing():
    """Demo: Batch processing with different presets"""
    print("\n" + "=" * 60)
    print("DEMO: Batch Processing")
    print("=" * 60)

    pipeline = CompleteBRIAPipeline()

    prompts = [
        {
            "prompt": "A futuristic city skyline at night",
            "preset": "cinematic",
            "aspect_ratio": "16:9"
        },
        {
            "prompt": "A serene zen garden with cherry blossoms",
            "preset": "minimalist",
            "aspect_ratio": "1:1"
        },
        {
            "prompt": "Portrait of a wise elderly person",
            "preset": "photorealistic",
            "aspect_ratio": "3:4"
        },
        {
            "prompt": "Abstract colorful geometric patterns",
            "preset": "artistic",
            "aspect_ratio": "1:1"
        }
    ]

    batch_result = pipeline.batch_process(prompts)

    print(f"\n📊 Batch Processing Results:")
    print(f"  Total: {batch_result.total}")
    print(f"  Successful: {batch_result.successful}")
    print(f"  Failed: {batch_result.failed}")
    print(f"  Success Rate: {batch_result.success_rate:.1f}%")
    print(f"  Total Time: {batch_result.execution_time:.2f}s")

    # Save successful results
    for i, result in enumerate(batch_result.results):
        if result.success:
            pipeline.save_results(result, f"output/batch_{i+1}")

    return batch_result

def demo_hdr_generation():
    """Demo: HDR/16-bit image generation"""
    print("\n" + "=" * 60)
    print("DEMO: HDR/16-bit Generation")
    print("=" * 60)

    pipeline = CompleteBRIAPipeline()

    # Temporarily enable HDR and 16-bit
    original_hdr = Config.ENABLE_HDR
    original_16bit = Config.ENABLE_16BIT

    Config.ENABLE_HDR = True
    Config.ENABLE_16BIT = True

    result = pipeline.process_single({
        "prompt": "A dramatic landscape with extreme dynamic range, bright sun and deep shadows",
        "preset": "hdr",
        "aspect_ratio": "16:9"
    })

    if result.success:
        print(f" HDR image generated: {result.image_url}")
        print(f"📊 HDR Enabled: {result.metadata.get('hdr_enabled', False)}")
        print(f"📊 16-bit Enabled: {result.metadata.get('16bit_enabled', False)}")
        print(f"⏱️ Time: {result.execution_time:.2f}s")
        pipeline.save_results(result, "output/hdr")
    else:
        print(f"❌ Failed: {result.error}")

    # Restore original settings
    Config.ENABLE_HDR = original_hdr
    Config.ENABLE_16BIT = original_16bit

    return result

def demo_all_presets():
    """Demo: Generate images with all available presets"""
    print("\n" + "=" * 60)
    print("DEMO: All Presets Showcase")
    print("=" * 60)

    pipeline = CompleteBRIAPipeline()
    base_prompt = "A beautiful tree in a field"

    print(f"\nGenerating with base prompt: '{base_prompt}'")
    print(f"Available presets: {PresetManager.list_presets()}\n")

    results = []
    for preset_name in PresetManager.list_presets():
        print(f"🎨 Applying preset: {preset_name}")
        preset = PresetManager.get_preset(preset_name)
        print(f"   Description: {preset.description}")

        result = pipeline.process_single({
            "prompt": base_prompt,
            "preset": preset_name
        })

        if result.success:
            print(f"    Success! Image: {result.image_url[:50]}...")
            pipeline.save_results(result, f"output/preset_{preset_name}")
        else:
            print(f"   ❌ Failed: {result.error}")

        results.append(result)

    # Generate report
    report = pipeline.generate_report(results)
    print("\n" + report)

    return results

def run_complete_demo():
    """Run all demos to showcase complete pipeline functionality"""
    print("\n" + "🚀" * 30)
    print("COMPLETE BRIA FIBO PIPELINE DEMONSTRATION")
    print("🚀" * 30)

    results = {}

    # 1. Simple generation
    print("\n1️⃣ Testing Simple Generation...")
    results['simple'] = demo_simple_generation()

    # 2. Multi-step refinement
    print("\n2️⃣ Testing Multi-Step Refinement...")
    results['refinement'] = demo_multi_step_refinement()

    # 3. Batch processing
    print("\n3️⃣ Testing Batch Processing...")
    results['batch'] = demo_batch_processing()

    # 4. HDR generation
    print("\n4️⃣ Testing HDR/16-bit Generation...")
    results['hdr'] = demo_hdr_generation()

    # 5. All presets
    print("\n5️⃣ Testing All Presets...")
    results['presets'] = demo_all_presets()

    # Final summary
    print("\n" + "=" * 60)
    print("🏁 COMPLETE DEMO SUMMARY")
    print("=" * 60)

    total_success = 0
    total_runs = 0

    for demo_name, result in results.items():
        if demo_name == 'batch':
            success = result.successful
            total = result.total
            print(f"  {demo_name.upper()}: {success}/{total} successful ({result.success_rate:.1f}%)")
            total_success += success
            total_runs += total
        elif demo_name == 'presets':
            success = sum(1 for r in result if r.success)
            total = len(result)
            print(f"  {demo_name.upper()}: {success}/{total} successful")
            total_success += success
            total_runs += total
        else:
            status = "" if result.success else "❌"
            print(f"  {demo_name.upper()}: {status}")
            if result.success:
                total_success += 1
            total_runs += 1

    overall_rate = (total_success / total_runs * 100) if total_runs > 0 else 0
    print(f"\n📊 Overall Success Rate: {total_success}/{total_runs} ({overall_rate:.1f}%)")
    print(f"✨ Demo Complete! Check the output/ directory for all generated content.")

    return results

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Complete BRIA FIBO Pipeline")
    parser.add_argument('--demo', type=str, help='Run specific demo',
                       choices=['simple', 'refinement', 'batch', 'hdr', 'presets', 'all'])
    parser.add_argument('--prompt', type=str, help='Generate image from prompt')
    parser.add_argument('--preset', type=str, help='Apply preset',
                       choices=PresetManager.list_presets())
    parser.add_argument('--aspect-ratio', type=str, default='1:1',
                       help='Aspect ratio (e.g., 1:1, 16:9, 3:4)')

    args = parser.parse_args()

    if args.demo:
        if args.demo == 'simple':
            demo_simple_generation()
        elif args.demo == 'refinement':
            demo_multi_step_refinement()
        elif args.demo == 'batch':
            demo_batch_processing()
        elif args.demo == 'hdr':
            demo_hdr_generation()
        elif args.demo == 'presets':
            demo_all_presets()
        elif args.demo == 'all':
            run_complete_demo()
    elif args.prompt:
        # Direct generation from command line
        pipeline = CompleteBRIAPipeline()
        result = pipeline.process_single({
            "prompt": args.prompt,
            "preset": args.preset,
            "aspect_ratio": args.aspect_ratio
        })

        if result.success:
            print(f" Image generated: {result.image_url}")
            pipeline.save_results(result)
        else:
            print(f"❌ Failed: {result.error}")
    else:
        # Run complete demo by default
        run_complete_demo()

if __name__ == "__main__":
    main()