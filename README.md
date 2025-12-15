# 🚀 Spec2Pixel : Enhanced BRIA FIBO Pipeline

<img width="893" height="487" alt="Screenshot 2025-12-16 at 4 49 45 AM" src="https://github.com/user-attachments/assets/c4cf1676-9384-416d-80c8-a3618540352b" />

## Automated JSON Refinement Pipeline for FIBO Hackathon

This project demonstrates the power of BRIA's FIBO model through an **automated, auditable, multi-step image refinement pipeline** that leverages structured JSON prompts for deterministic, scalable workflows.

## ✨ Key Features

### Core Capabilities
-  **Environment-based configuration** - Secure API token management
-  **Robust error handling** - Retry logic with exponential backoff
-  **Multi-step refinement chains** - Sequential prompt refinements
-  **Batch processing** - Concurrent processing of multiple prompts
-  **JSON diff visualization** - Track changes between refinements
-  **Parameter presets** - Quick configuration for common styles
-  **HDR/16-bit support** - Professional-grade color depth
-  **Comprehensive testing** - Unit tests with high coverage

### Production Features
- Asynchronous request handling
- Automatic status polling
- Result persistence and archiving
- Refinement history tracking
- Execution metrics and logging
- Thread-safe batch operations

### Categories
- **Best JSON-Native or Agentic Workflow** (Primary)
- **Best Controllability**
- **Best Professional Tool**


## 🎯 What Makes This Special?

Unlike traditional text-to-image systems that rely on prompt engineering, this pipeline provides:

1. **Deterministic Control**: Every parameter (camera angle, lighting, color) is explicitly controlled through JSON
2. **Auditable Workflow**: Track every refinement step with full diff visualization
3. **Scalable Architecture**: API-based design ready for enterprise deployment
4. **Professional Integration**: ComfyUI nodes for seamless workflow integration

## 📁 Project Structure

```
pipeline/
├── enhanced_pipeline.py    # Main enhanced pipeline implementation
├── main.py                 # Original basic pipeline
├── test_pipeline.py        # Comprehensive unit tests
├── requirements.txt        # Python dependencies
├── .env                   # Environment configuration
├── .env.example          # Example environment file
├── README.md             # This file
└── output/               # Generated images and results
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone
cd fibo/pipeline

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your BRIA API token
# Get your token at: https://bria.ai/api/
```

### 3. Run the Pipeline

```bash
# Run the enhanced pipeline with all demos
python enhanced_pipeline.py

# Run specific demos
python -c "from enhanced_pipeline import demo_simple_generation; demo_simple_generation()"
python -c "from enhanced_pipeline import demo_multi_step_refinement; demo_multi_step_refinement()"
python -c "from enhanced_pipeline import demo_batch_processing; demo_batch_processing()"
python -c "from enhanced_pipeline import demo_hdr_generation; demo_hdr_generation()"
```

### 4. Run Tests

```bash
# Run all unit tests
python test_pipeline.py

# Run with coverage
pytest test_pipeline.py --cov=enhanced_pipeline --cov-report=html
```

## 💡 Usage Examples

### Simple Generation with Preset

```python
from enhanced_pipeline import EnhancedBRIAPipeline

pipeline = EnhancedBRIAPipeline()

result = pipeline.process_single({
    "prompt": "A majestic eagle soaring through clouds",
    "preset": "cinematic"  # Use cinematic preset
})

if result.success:
    print(f"Image URL: {result.image_url}")
    pipeline.save_results(result)
```

### Multi-Step Refinement Chain

```python
from enhanced_pipeline import EnhancedBRIAPipeline, RefinementStep

pipeline = EnhancedBRIAPipeline()

# Define refinement steps
steps = [
    RefinementStep(
        "Add warm morning sunlight",
        "Adding lighting"
    ),
    RefinementStep(
        "Add vintage decorations",
        "Adding decorative elements"
    ),
    RefinementStep(
        "Make it photorealistic",
        "Enhancing realism",
        {"preset": "photorealistic"}
    )
]

# Execute refinement chain
result = pipeline.multi_step_refinement(
    "A cozy coffee shop interior",
    steps
)

# Visualize changes
print(pipeline.visualize_refinement_history(result.refinement_history))
```

### Batch Processing

```python
prompts = [
    {"prompt": "Futuristic city", "preset": "cinematic"},
    {"prompt": "Mountain landscape", "preset": "photorealistic"},
    {"prompt": "Abstract patterns", "preset": "artistic"}
]

results = pipeline.batch_process(prompts)

for i, result in enumerate(results):
    if result.success:
        print(f" Prompt {i+1}: {result.image_url}")
```

### HDR/16-bit Generation

```python
# Enable in .env file:
# ENABLE_HDR=true
# ENABLE_16BIT=true

result = pipeline.process_single({
    "prompt": "Dramatic sunset with extreme dynamic range",
    "preset": "hdr"
})
```

## 🎨 Available Presets

| Preset | Description | Key Parameters |
|--------|-------------|----------------|
| `photorealistic` | Ultra-realistic photography | Natural lighting, high detail |
| `cinematic` | Film-like appearance | Dramatic lighting, wide shots |
| `artistic` | Digital illustration | Vibrant colors, expressive style |
| `hdr` | High Dynamic Range | 16-bit color, ProPhoto RGB |

## 📊 JSON Diff Visualization

The pipeline tracks all changes between refinement steps:

```
Step 1: REFINEMENT
----------------------------------------
Prompt: Add warm morning sunlight...
Changes: 3 changes
  + "lighting": {"conditions": "morning sunlight"}
  - "lighting": {"conditions": "ambient"}
  + "color_temperature": "warm"
```

## 🔧 Configuration Options

Edit `.env` file to customize behavior:

```env
# API Configuration
BRIA_API_TOKEN=your_token_here
BRIA_API_URL=https://engine.prod.bria-api.com/v2

# Performance
MAX_RETRIES=3
RETRY_DELAY=5
POLLING_INTERVAL=5
MAX_BATCH_SIZE=5

# Features
ENABLE_HDR=true
ENABLE_16BIT=true
ENABLE_BATCH_PROCESSING=true

# Logging
LOG_LEVEL=INFO
LOG_FILE=pipeline.log
```

## 🧪 Testing

The project includes comprehensive unit tests:

```bash
# Run tests
python test_pipeline.py

# Expected output:
#  25 tests passed
#  Coverage: 85%+
```

Test coverage includes:
- Preset management
- Retry logic
- Pipeline operations
- Batch processing
- Error handling
- Data structures

## 📈 Performance Metrics

- **Single generation**: ~15-30 seconds
- **Multi-step refinement** (3 steps): ~45-60 seconds
- **Batch processing**: Up to 5 concurrent requests
- **Retry mechanism**: Exponential backoff with 3 attempts
- **Memory usage**: < 100MB per request

## 🤝 ComfyUI Integration

The project includes ComfyUI nodes for visual workflow integration:

1. Navigate to `ComfyUI-BRIA-API/`
2. Install nodes in your ComfyUI instance
3. Load workflow examples from `workflows/`
4. Use V2 nodes for FIBO structured prompts

## 🛠️ API Endpoints Used

- `/v2/structured_prompt/generate` - Generate/refine structured prompts
- `/v2/image/generate` - Generate images from structured prompts
- Status polling for asynchronous operations

## 🚨 Error Handling

The pipeline includes robust error handling:

- Automatic retry with exponential backoff
- Timeout protection for long-running requests
- Graceful degradation for batch failures
- Detailed error logging and reporting

## 📝 Logging

Logs are saved to `pipeline.log` with configurable levels:

```
2024-12-15 10:30:45 - INFO - Starting multi-step refinement...
2024-12-15 10:30:50 - INFO - Step 1: Adding lighting
2024-12-15 10:31:05 - INFO - Step 2: Adding decorative elements
2024-12-15 10:31:20 - SUCCESS - Image generated: https://...
```

## 🎯 Future Enhancements

- [ ] Web UI for interactive refinement
- [ ] Real-time preview during refinement
- [ ] Custom preset creation UI
- [ ] Integration with more professional tools
- [ ] Advanced HDR tone mapping options
- [ ] Distributed processing support

## 📄 License

This project is created for the BRIA FIBO Hackathon.

## 🙏 Acknowledgments

- BRIA.ai for the FIBO model and API
- Hackathon organizers for the opportunity
- Open-source community for tools and libraries

---

**Built with ❤️ for the FIBO Hackathon**