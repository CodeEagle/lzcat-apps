# TTS-Story Upstream Deployment Checklist

## Upstream Basics

- Project name: `TTS-Story`
- Project slug: `tts-story`
- Upstream repo: `Xerophayze/TTS-Story`
- Upstream URL: `https://github.com/Xerophayze/TTS-Story`
- License: Apache-2.0
- Author: Xerophayze
- Release status: no GitHub release/tag found; current migration baseline uses commit `1f7ce734cb6135b4524015ec34ba67373faf8d1d` from `2026-03-07`

## Runtime Topology

- Topology: single-container Flask web application
- Entry file: `app.py`
- Startup path upstream:
  - `run.sh` activates `venv`
  - `run.sh` finally executes `python app.py`
  - `app.py` runs `app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)`
- Health endpoint: `GET /api/health`
- Container listen port: `5000`
- External dependencies:
  - None required for basic startup
  - Optional cloud APIs: Gemini, Replicate
  - Optional local model downloads: Hugging Face models for several engines

## Environment Variables and Config Inputs

- Primary config file: `config.json`
- Upstream stores nearly all runtime settings in `config.json`, not process env
- LazyCat seeding strategy:
  - persist `config.json`
  - on first boot force CPU-friendly defaults
  - optionally import these env values into blank config fields:
    - `GEMINI_API_KEY`
    - `REPLICATE_API_KEY`
    - `CHATTERBOX_TURBO_REPLICATE_API_TOKEN`
- Useful runtime env for LazyCat:
  - `PORT=5000`
  - `HF_HOME=/data/.cache/huggingface`
  - `TRANSFORMERS_CACHE=/data/.cache/huggingface/hub`
  - `XDG_CACHE_HOME=/data/.cache`
  - `TORCH_HOME=/data/.cache/torch`

## Real Read/Write Paths

- `config.json`
  - purpose: app settings, API keys, engine defaults
  - write behavior: app UI saves settings here
  - LazyCat handling: persist at `/data/config.json`, symlink back to app root
- `data/jobs/jobs.db`
  - purpose: SQLite job queue database
  - write behavior: created and updated at startup and during generation
- `data/jobs/`
  - purpose: per-job metadata and archived job records
- `data/voice_prompts/`
  - purpose: uploaded reference voice samples
- `data/prep/`
  - purpose: text-prep progress/state files
- `data/custom_voices.json`
  - purpose: blended/custom voice definitions
- `data/chatterbox_voices.json`
  - purpose: registered chatterbox voice prompt metadata
- `data/external_voice_archives.json`
  - purpose: cached external voice library metadata
- `static/audio/`
  - purpose: generated outputs served by Flask
- `models/qwen3/`
  - purpose: local Qwen3 model cache when that engine is enabled
- Hugging Face / Torch cache:
  - `/data/.cache/huggingface`
  - `/data/.cache/torch`
  - `/data/.cache/matplotlib`

## Directory Creation and Ownership

- Upstream local install assumes the interactive user owns the repo directory
- LazyCat migration runs the service as the container default user (root in this image)
- Directories to pre-create before app boot:
  - `/data`
  - `/data/data`
  - `/data/audio`
  - `/data/models/qwen3`
  - `/data/.cache/huggingface`
  - `/data/.cache/torch`
  - `/data/.cache/matplotlib`
- Creation method: entrypoint pre-creates them before launching Flask
- Ownership/mode: default container owner/group, no extra `chown` required for current image

## Initialization and Health

- First boot work:
  - seed persistent `data/` tree from upstream repo contents
  - seed persistent `config.json`
  - force first-run defaults to CPU-friendly engine `kitten_tts`
  - register any voice prompt files
  - initialize SQLite jobs database
- No database migrations or admin-bootstrap commands required
- Health check:
  - `curl -fsS http://127.0.0.1:5000/api/health`

## CPU/Docker Suitability Assessment

- Project is not blocked by CPU-only deployment
- Reason:
  - upstream ships CPU-capable engines (`pocket_tts`, `kitten_tts`)
  - GPU-heavy engines remain optional and can stay unavailable until users install or enable them
- Expected limitation:
  - local GPU/large-model engines will be slow or unavailable on CPU-only LazyCat devices
  - first use of some engines may download large model assets into persistent cache

## Minimum Runnable Path

1. Build LazyCat image from custom Dockerfile
2. Install system audio tools and CPU PyTorch
3. Install upstream Python dependencies and optional runtime packages
4. Start entrypoint
5. Seed `/data`, symlink runtime paths, initialize DB
6. Launch Flask on port `5000`
7. Access `/` and confirm `/api/health` returns success JSON
