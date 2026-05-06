ARG SOURCE_VERSION=main
ARG BUILD_VERSION=0.1.0
ARG UPSTREAM_REPO=Xerophayze/TTS-Story

FROM python:3.11-slim-bookworm

ARG SOURCE_VERSION
ARG BUILD_VERSION
ARG UPSTREAM_REPO

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000 \
    HF_HOME=/data/.cache/huggingface \
    TRANSFORMERS_CACHE=/data/.cache/huggingface/hub \
    XDG_CACHE_HOME=/data/.cache \
    TORCH_HOME=/data/.cache/torch \
    MPLCONFIGDIR=/data/.cache/matplotlib \
    TTS_STORY_DATA_ROOT=/data \
    TTS_STORY_DEFAULT_ENGINE=pocket_tts_preset \
    TTS_STORY_DEFAULT_VOICE=alba \
    KITTEN_TTS_CACHE_DIR=/opt/tts-story/.cache/kittentts \
    TTS_STORY_PARALLEL_CHUNKS=1 \
    TTS_STORY_GROUP_CHUNKS_BY_SPEAKER=false

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      espeak-ng \
      ffmpeg \
      git \
      libgomp1 \
      libsndfile1 \
      rubberband-cli \
      sox && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/tts-story

RUN git clone https://github.com/${UPSTREAM_REPO}.git . && \
    git checkout "${SOURCE_VERSION}"

COPY patch_upstream.py /tmp/patch_upstream.py

RUN python /tmp/patch_upstream.py && rm -f /tmp/patch_upstream.py

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip uninstall -y torch torchvision torchaudio || true && \
    python -m pip install \
      torch==2.6.0+cpu \
      torchvision==0.21.0+cpu \
      torchaudio==2.6.0+cpu \
      --index-url https://download.pytorch.org/whl/cpu && \
    python -m pip install --upgrade \
      "numpy<1.26.0" \
      "pillow<12.0" \
      "fsspec<=2025.3.0" \
      "filelock>=3.20.1,<4" && \
    grep -qi '^scipy' requirements.txt || printf '\nscipy>=1.11.0\n' >> requirements.txt && \
    grep -vi '^torch' requirements.txt > /tmp/requirements.no-torch.txt && \
    grep -vi '^pyopenjtalk' /tmp/requirements.no-torch.txt > /tmp/requirements.runtime.txt && \
    python -m pip install -r /tmp/requirements.runtime.txt && \
    python -m pip install chatterbox-tts && \
    python -m pip install pocket-tts && \
    python -m pip install voxcpm --no-deps && \
    python -m pip install hf_xet && \
    python -m pip install \
      https://github.com/KittenML/KittenTTS/releases/download/0.8/kittentts-0.8.0-py3-none-any.whl && \
    rm -f /tmp/requirements.no-torch.txt /tmp/requirements.runtime.txt

RUN mkdir -p "${KITTEN_TTS_CACHE_DIR}" && \
    python - <<'PY'
import json
import os
from huggingface_hub import hf_hub_download

repo_id = os.environ.get("KITTEN_TTS_MODEL_ID", "KittenML/kitten-tts-mini-0.8")
cache_dir = os.environ["KITTEN_TTS_CACHE_DIR"]
config_path = hf_hub_download(repo_id=repo_id, filename="config.json", cache_dir=cache_dir)
with open(config_path, "r", encoding="utf-8") as fh:
    config = json.load(fh)
hf_hub_download(repo_id=repo_id, filename=config["model_file"], cache_dir=cache_dir)
hf_hub_download(repo_id=repo_id, filename=config["voices"], cache_dir=cache_dir)
PY

RUN rm -rf "${KITTEN_TTS_CACHE_DIR}/.locks"

COPY entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh && \
    mkdir -p /data /opt/tts-story/static/audio /opt/tts-story/models/qwen3 /opt/tts-story/.cache/kittentts

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
  CMD curl -fsS http://127.0.0.1:5000/api/health >/dev/null || exit 1

ENTRYPOINT ["/entrypoint.sh"]
