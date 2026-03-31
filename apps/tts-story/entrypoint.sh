#!/bin/sh
set -eu

APP_DIR="/opt/tts-story"
STATE_DIR="${TTS_STORY_DATA_ROOT:-/data}"
SEEDED_CONFIG=0

mkdir -p \
  "${STATE_DIR}" \
  "${STATE_DIR}/audio" \
  "${STATE_DIR}/data" \
  "${STATE_DIR}/models/qwen3" \
  "${STATE_DIR}/.cache/huggingface" \
  "${STATE_DIR}/.cache/torch" \
  "${STATE_DIR}/.cache/matplotlib"

if [ ! -f "${STATE_DIR}/.seeded_data_v1" ]; then
  cp -R "${APP_DIR}/data/." "${STATE_DIR}/data/" 2>/dev/null || true
  touch "${STATE_DIR}/.seeded_data_v1"
fi

if [ ! -f "${STATE_DIR}/config.json" ]; then
  cp "${APP_DIR}/config.json" "${STATE_DIR}/config.json"
  SEEDED_CONFIG=1
fi

rm -rf "${APP_DIR}/data"
ln -sfn "${STATE_DIR}/data" "${APP_DIR}/data"

rm -rf "${APP_DIR}/static/audio"
ln -sfn "${STATE_DIR}/audio" "${APP_DIR}/static/audio"

mkdir -p "${APP_DIR}/models"
rm -rf "${APP_DIR}/models/qwen3"
ln -sfn "${STATE_DIR}/models/qwen3" "${APP_DIR}/models/qwen3"

rm -f "${APP_DIR}/config.json"
ln -sfn "${STATE_DIR}/config.json" "${APP_DIR}/config.json"

SEEDED_CONFIG="${SEEDED_CONFIG}" python - <<'PY'
import json
import os
from pathlib import Path

config_path = Path("/data/config.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
seeded = os.environ.get("SEEDED_CONFIG") == "1"

if seeded:
    default_engine = os.environ.get("TTS_STORY_DEFAULT_ENGINE", "pocket_tts_preset")
    default_voice = os.environ.get("TTS_STORY_DEFAULT_VOICE", "alba")
    config.update(
        {
            "tts_engine": default_engine,
            "kitten_tts_default_voice": default_voice if default_engine == "kitten_tts" else "Jasper",
            "pocket_tts_default_prompt": default_voice
            if default_engine in {"pocket_tts", "pocket_tts_preset"}
            else (config.get("pocket_tts_default_prompt") or ""),
            "parallel_chunks": int(os.environ.get("TTS_STORY_PARALLEL_CHUNKS", "1")),
            "group_chunks_by_speaker": os.environ.get(
                "TTS_STORY_GROUP_CHUNKS_BY_SPEAKER", "false"
            ).lower()
            in {"1", "true", "yes", "on"},
            "chatterbox_turbo_local_device": "cpu",
            "voxcpm_local_device": "cpu",
            "qwen3_custom_device": "cpu",
            "qwen3_clone_device": "cpu",
            "index_tts_device": "cpu",
            "index_tts_use_fp16": False,
            "index_tts_use_accel": False,
            "index_tts_use_torch_compile": False,
            "cleanup_vram_after_job": False,
            "output_format": "mp3",
            "output_bitrate_kbps": 128,
        }
    )

optional_env_map = {
    "GEMINI_API_KEY": "gemini_api_key",
    "REPLICATE_API_KEY": "replicate_api_key",
    "CHATTERBOX_TURBO_REPLICATE_API_TOKEN": "chatterbox_turbo_replicate_api_token",
}
for env_name, config_key in optional_env_map.items():
    value = os.environ.get(env_name, "").strip()
    if value and not str(config.get(config_key, "")).strip():
        config[config_key] = value

config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
PY

cd "${APP_DIR}"

exec python - <<'PY'
import os

from app import (
    _archive_old_jobs,
    _auto_register_voice_prompt_files,
    _cleanup_orphaned_chatterbox_voices,
    _cleanup_orphaned_regen_folders,
    _init_jobs_db,
    _purge_stale_jobs,
    _restore_jobs_from_db,
    app,
)

_init_jobs_db()
_purge_stale_jobs()
_restore_jobs_from_db()
_archive_old_jobs()
_cleanup_orphaned_chatterbox_voices()
_auto_register_voice_prompt_files()
_cleanup_orphaned_regen_folders()

app.run(
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "5000")),
    debug=False,
    use_reloader=False,
)
PY
