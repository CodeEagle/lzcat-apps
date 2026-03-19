#!/usr/bin/env python3
"""
LazyCat-friendly FastAPI entrypoint for Edit Banana.

Changes from upstream:
- root page provides a branded upload UI
- models can be downloaded on demand after user consent
- model download progress and reset are exposed to the UI
- /convert returns the generated file directly
- model/config validation errors are surfaced as 503
"""

import copy
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RUNTIME_SETTINGS_PATH = os.environ.get("MODEL_DOWNLOAD_CONFIG_PATH", "/app/config/runtime-settings.json")
CONFIG_YAML_PATH = os.environ.get("EDIT_BANANA_CONFIG_PATH", "/app/config/config.yaml")
DEFAULT_SAM3_CHECKPOINT_URL = "https://www.modelscope.cn/models/facebook/sam3/resolve/master/sam3.pt"
DEFAULT_SAM3_BPE_URL = "https://raw.githubusercontent.com/openai/CLIP/main/clip/bpe_simple_vocab_16e6.txt.gz"
DEFAULT_SAM3_DEVICE = "cpu"
MODEL_DOWNLOAD_LOCK = threading.Lock()
MODEL_STATE_LOCK = threading.Lock()
MODEL_DOWNLOAD_STATE = {
    "status": "idle",
    "message": "",
    "error": "",
    "current_file": "",
    "current_bytes": 0,
    "total_bytes": 0,
    "files": {},
}

app = FastAPI(
    title="Edit Banana API",
    description="Universal Content Re-Editor: image to editable DrawIO XML",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=os.path.join(PROJECT_ROOT, "static")), name="static")


class InitializeModelsRequest(BaseModel):
    checkpoint_url: Optional[str] = None

class RuntimeSettingsRequest(BaseModel):
    sam3_device: Optional[str] = None


def _normalize_url(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_device(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in {"cpu", "cuda"} else ""


def _load_runtime_settings() -> dict:
    try:
        with open(RUNTIME_SETTINGS_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _save_runtime_settings(checkpoint_url: Optional[str] = None, sam3_device: Optional[str] = None) -> dict:
    data = _load_runtime_settings()
    normalized = _normalize_url(checkpoint_url)
    normalized_device = _normalize_device(sam3_device)

    if checkpoint_url is not None:
        if normalized:
            data["checkpoint_url"] = normalized
        else:
            data.pop("checkpoint_url", None)

    if sam3_device is not None:
        if normalized_device:
            data["sam3_device"] = normalized_device
        else:
            data.pop("sam3_device", None)

    os.makedirs(os.path.dirname(RUNTIME_SETTINGS_PATH), exist_ok=True)
    with open(RUNTIME_SETTINGS_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=True, indent=2)

    return data


def _effective_sam3_device() -> tuple[str, str]:
    settings = _load_runtime_settings()
    custom_device = _normalize_device(settings.get("sam3_device"))
    if custom_device:
        return custom_device, "custom"

    env_device = _normalize_device(os.environ.get("SAM3_DEVICE", ""))
    if env_device:
        return env_device, "env"

    return DEFAULT_SAM3_DEVICE, "default"


def _build_runtime_config() -> dict:
    sam3_device, _device_source = _effective_sam3_device()
    return {
        "sam3": {
            "checkpoint_path": os.environ.get("SAM3_CHECKPOINT_PATH", "/app/models/sam3.pt"),
            "bpe_path": os.environ.get("SAM3_BPE_PATH", "/app/models/bpe_simple_vocab_16e6.txt.gz"),
            "device": sam3_device,
            "score_threshold": 0.5,
            "epsilon_factor": 0.02,
            "min_area": 100,
        },
        "prompt_groups": {
            "image": {
                "name": "image",
                "score_threshold": 0.5,
                "min_area": 100,
                "priority": 2,
            },
            "arrow": {
                "name": "arrow",
                "score_threshold": 0.45,
                "min_area": 50,
                "priority": 4,
            },
            "shape": {
                "name": "shape",
                "score_threshold": 0.5,
                "min_area": 200,
                "priority": 3,
            },
            "background": {
                "name": "background",
                "score_threshold": 0.25,
                "min_area": 500,
                "priority": 1,
            },
        },
        "ocr": {
            "engine": os.environ.get("OCR_ENGINE", "tesseract"),
        },
        "multimodal": {
            "mode": os.environ.get("MULTIMODAL_MODE", "api"),
            "api_key": os.environ.get("MULTIMODAL_API_KEY", ""),
            "base_url": os.environ.get("MULTIMODAL_BASE_URL", ""),
            "model": os.environ.get("MULTIMODAL_MODEL", ""),
            "local_base_url": os.environ.get("MULTIMODAL_LOCAL_BASE_URL", "http://localhost:11434/v1"),
            "local_api_key": os.environ.get("MULTIMODAL_LOCAL_API_KEY", "ollama"),
            "local_model": os.environ.get("MULTIMODAL_LOCAL_MODEL", ""),
            "force_vlm_ocr": os.environ.get("MULTIMODAL_FORCE_VLM_OCR", "false").strip().lower() == "true",
            "max_tokens": int(os.environ.get("MULTIMODAL_MAX_TOKENS", "4000") or "4000"),
            "timeout": int(os.environ.get("MULTIMODAL_TIMEOUT", "60") or "60"),
            "ca_cert_path": os.environ.get("MULTIMODAL_CA_CERT_PATH", ""),
            "proxy": os.environ.get("MULTIMODAL_PROXY", ""),
        },
        "paths": {
            "output_dir": os.environ.get("OUTPUT_DIR", "/app/output"),
        },
    }


def _write_runtime_config() -> None:
    os.makedirs(os.path.dirname(CONFIG_YAML_PATH), exist_ok=True)
    config = _build_runtime_config()
    with open(CONFIG_YAML_PATH, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, allow_unicode=False, sort_keys=False)


def _load_config():
    from main import load_config

    _write_runtime_config()
    return load_config()


def _runtime_settings_payload() -> dict:
    device_value, device_source = _effective_sam3_device()
    return {
        "sam3_device": device_value,
        "sam3_device_source": device_source,
        "sam3_device_options": [
            {"value": "cpu", "label": "CPU"},
            {"value": "cuda", "label": "GPU"},
        ],
    }


def _load_download_overrides() -> dict:
    return _load_runtime_settings()


def _save_runtime_device(sam3_device: Optional[str]) -> dict:
    settings = _save_runtime_settings(sam3_device=sam3_device)
    _write_runtime_config()
    return settings


def _save_download_overrides(checkpoint_url: Optional[str]) -> None:
    _save_runtime_settings(checkpoint_url=checkpoint_url)
    _write_runtime_config()


_write_runtime_config()


def _resolve_download_url(config_key: str, env_key: str, default_url: str) -> tuple[str, str, str]:
    overrides = _load_download_overrides()
    custom_url = _normalize_url(overrides.get(config_key))
    if custom_url:
        return custom_url, "custom", custom_url

    env_url = _normalize_url(os.environ.get(env_key, ""))
    if env_url:
        return env_url, "env", custom_url

    default_value = _normalize_url(default_url)
    if default_value:
        return default_value, "default", custom_url

    return "", "missing", custom_url


def _model_definitions():
    config = _load_config()
    sam3_cfg = config.get("sam3", {})
    checkpoint_url, checkpoint_source, checkpoint_custom = _resolve_download_url(
        "checkpoint_url",
        "SAM3_CHECKPOINT_URL",
        DEFAULT_SAM3_CHECKPOINT_URL,
    )
    tokenizer_url, tokenizer_source, _ = _resolve_download_url(
        "tokenizer_url",
        "SAM3_BPE_URL",
        DEFAULT_SAM3_BPE_URL,
    )
    return [
        {
            "key": "checkpoint",
            "label": "SAM3 checkpoint",
            "path": sam3_cfg.get("checkpoint_path", "") or "/app/models/sam3.pt",
            "url": checkpoint_url,
            "url_source": checkpoint_source,
            "custom_url": checkpoint_custom,
            "default_url": DEFAULT_SAM3_CHECKPOINT_URL,
        },
        {
            "key": "tokenizer",
            "label": "Tokenizer",
            "path": sam3_cfg.get("bpe_path", "") or "/app/models/bpe_simple_vocab_16e6.txt.gz",
            "url": tokenizer_url,
            "url_source": tokenizer_source,
            "custom_url": "",
            "default_url": DEFAULT_SAM3_BPE_URL,
        },
    ]


def _reset_download_state():
    with MODEL_STATE_LOCK:
        MODEL_DOWNLOAD_STATE.update(
            {
                "status": "idle",
                "message": "",
                "error": "",
                "current_file": "",
                "current_bytes": 0,
                "total_bytes": 0,
                "files": {},
            }
        )


def _update_download_state(**updates):
    with MODEL_STATE_LOCK:
        MODEL_DOWNLOAD_STATE.update(updates)


def _update_file_progress(key: str, **updates):
    with MODEL_STATE_LOCK:
        file_state = MODEL_DOWNLOAD_STATE["files"].setdefault(key, {})
        file_state.update(updates)


def _snapshot_download_state():
    with MODEL_STATE_LOCK:
        return copy.deepcopy(MODEL_DOWNLOAD_STATE)


def _model_status():
    files = []
    missing = []
    missing_keys = []

    for item in _model_definitions():
        exists = os.path.exists(item["path"])
        if not exists:
            missing.append(item["label"])
            missing_keys.append(item["key"])

        files.append(
            {
                "key": item["key"],
                "label": item["label"],
                "path": item["path"],
                "exists": exists,
                "url_configured": bool(item["url"]),
                "url_source": item.get("url_source", "missing"),
                "custom_url": item.get("custom_url", ""),
                "default_url": item.get("default_url", ""),
            }
        )

    downloadable = all(file["exists"] or file["url_configured"] for file in files)
    progress = _snapshot_download_state()
    total_bytes = progress.get("total_bytes") or 0
    current_bytes = progress.get("current_bytes") or 0
    percent = 0
    if total_bytes > 0:
        percent = round((current_bytes / total_bytes) * 100, 2)

    status = progress.get("status", "idle")
    if not missing and status != "downloading":
        status = "ready"

    return {
        "ready": not missing,
        "missing": missing,
        "missing_keys": missing_keys,
        "downloadable": downloadable,
        "downloading": MODEL_DOWNLOAD_LOCK.locked(),
        "files": files,
        "download_config": {
            "checkpoint_url": next((file["custom_url"] for file in files if file["key"] == "checkpoint"), ""),
            "checkpoint_default_url": next((file["default_url"] for file in files if file["key"] == "checkpoint"), ""),
            "checkpoint_source": next((file["url_source"] for file in files if file["key"] == "checkpoint"), "missing"),
        },
        "runtime_settings": _runtime_settings_payload(),
        "progress": {
            "status": status,
            "message": progress.get("message", ""),
            "error": progress.get("error", ""),
            "current_file": progress.get("current_file", ""),
            "current_bytes": current_bytes,
            "total_bytes": total_bytes,
            "percent": percent,
            "files": progress.get("files", {}),
        },
    }


def _download_file(file_info: dict) -> None:
    target_path = file_info["path"]
    source_url = file_info["url"]
    label = file_info["label"]
    key = file_info["key"]
    temp_path = f"{target_path}.tmp"

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    request = Request(source_url, headers={"User-Agent": "Edit-Banana-LazyCat/1.0"})

    try:
        with urlopen(request, timeout=300) as response, open(temp_path, "wb") as output_file:
            total_bytes = int(response.headers.get("Content-Length", "0") or "0")
            _update_download_state(
                status="downloading",
                message=f"Downloading {label}",
                error="",
                current_file=key,
                current_bytes=0,
                total_bytes=total_bytes,
            )
            _update_file_progress(
                key,
                status="downloading",
                downloaded_bytes=0,
                total_bytes=total_bytes,
                label=label,
            )

            downloaded = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output_file.write(chunk)
                downloaded += len(chunk)
                _update_download_state(current_bytes=downloaded, total_bytes=total_bytes)
                _update_file_progress(
                    key,
                    status="downloading",
                    downloaded_bytes=downloaded,
                    total_bytes=total_bytes,
                )

        os.replace(temp_path, target_path)
        _update_file_progress(
            key,
            status="ready",
            downloaded_bytes=os.path.getsize(target_path),
            total_bytes=os.path.getsize(target_path),
        )
    except Exception as exc:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise RuntimeError(f"Failed to download {label}: {exc}") from exc


def _download_models_worker():
    try:
        _reset_download_state()
        _update_download_state(status="downloading", message="Preparing download")

        for file_info in _model_definitions():
            if os.path.exists(file_info["path"]):
                size = os.path.getsize(file_info["path"])
                _update_file_progress(
                    file_info["key"],
                    status="ready",
                    downloaded_bytes=size,
                    total_bytes=size,
                    label=file_info["label"],
                )
                continue

            if not file_info["url"]:
                raise RuntimeError(f"{file_info['label']} download URL is not configured.")

            _download_file(file_info)

        _update_download_state(
            status="ready",
            message="All model files are ready.",
            error="",
            current_file="",
            current_bytes=0,
            total_bytes=0,
        )
    except Exception as exc:
        _update_download_state(
            status="error",
            message="Model download failed.",
            error=str(exc),
            current_file="",
        )
    finally:
        MODEL_DOWNLOAD_LOCK.release()


def _load_pipeline():
    from main import Pipeline

    config = _load_config()
    checkpoint_path = config.get("sam3", {}).get("checkpoint_path", "")
    bpe_path = config.get("sam3", {}).get("bpe_path", "")

    if not checkpoint_path or not os.path.exists(checkpoint_path):
        raise HTTPException(
            status_code=503,
            detail="Model files are not ready yet. Download them from the home page first.",
        )

    if not bpe_path or not os.path.exists(bpe_path):
        raise HTTPException(
            status_code=503,
            detail="Model files are not ready yet. Download them from the home page first.",
        )

    output_dir = config.get("paths", {}).get("output_dir", "/app/output")
    os.makedirs(output_dir, exist_ok=True)
    return Pipeline(config), output_dir


@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html>
      <head>
        <title>Edit Banana</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <style>
          :root {
            color-scheme: light;
            --banana: #e28709;
            --banana-dark: #c46d00;
            --ink: #24324c;
            --muted: #75839b;
            --card: rgba(249, 247, 241, 0.94);
            --card-border: rgba(226, 210, 173, 0.7);
            --chip: #f5ddb0;
            --overlay: rgba(25, 22, 16, 0.5);
          }
          * {
            box-sizing: border-box;
          }
          body {
            margin: 0;
            min-height: 100vh;
            font-family: "Avenir Next", "Trebuchet MS", "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
            background:
              radial-gradient(circle at 18% 20%, rgba(255, 250, 212, 0.7), transparent 24%),
              radial-gradient(circle at 78% 70%, rgba(245, 222, 149, 0.55), transparent 22%),
              linear-gradient(180deg, #efe2b0 0%, #f6efcf 42%, #f2e8bc 100%);
            color: var(--ink);
            overflow-x: hidden;
          }
          body::before,
          body::after {
            content: "";
            position: fixed;
            inset: 0;
            pointer-events: none;
          }
          body::before {
            opacity: 0.18;
            background-image:
              radial-gradient(circle at 24% 30%, rgba(255, 255, 255, 0.8) 0, rgba(255, 255, 255, 0) 16%),
              radial-gradient(circle at 76% 18%, rgba(255, 255, 255, 0.64) 0, rgba(255, 255, 255, 0) 13%),
              radial-gradient(circle at 70% 76%, rgba(255, 255, 255, 0.5) 0, rgba(255, 255, 255, 0) 15%);
          }
          body::after {
            opacity: 0.1;
            background:
              linear-gradient(90deg, rgba(255, 255, 255, 0.24) 0 1px, transparent 1px 46px),
              linear-gradient(rgba(255, 255, 255, 0.2) 0 1px, transparent 1px 46px);
            background-size: 46px 46px;
          }
          .shell {
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 42px 18px;
          }
          .panel {
            position: relative;
            width: min(100%, 582px);
            padding: 44px 46px 36px;
            border-radius: 36px;
            border: 1px solid var(--card-border);
            background: var(--card);
            box-shadow:
              0 30px 80px rgba(138, 109, 28, 0.12),
              inset 0 1px 0 rgba(255, 255, 255, 0.72);
            backdrop-filter: blur(12px);
            transition: filter 180ms ease, opacity 180ms ease;
          }
          .panel.blocked {
            filter: blur(4px);
            opacity: 0.55;
            pointer-events: none;
            user-select: none;
          }
          .stamp {
            position: absolute;
            width: 114px;
            height: 114px;
            border-radius: 999px;
            background: rgba(236, 201, 96, 0.14) url("/static/banana.jpg") center/72% no-repeat;
            opacity: 0.42;
            filter: saturate(0.9);
            pointer-events: none;
          }
          .stamp-left {
            left: 28px;
            bottom: 32px;
          }
          .stamp-right {
            right: 30px;
            top: 66px;
          }
          .brand {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 16px;
          }
          .brand img {
            width: 86px;
            height: 86px;
            object-fit: cover;
            border-radius: 999px;
            box-shadow: 0 16px 30px rgba(226, 135, 9, 0.2);
          }
          h1 {
            margin: 0;
            font-size: clamp(34px, 7vw, 58px);
            line-height: 0.96;
            letter-spacing: -0.05em;
            color: var(--banana);
          }
          .tagline {
            position: relative;
            z-index: 1;
            margin: 18px auto 0;
            max-width: 430px;
            text-align: center;
            line-height: 1.45;
            font-size: 17px;
            color: #687894;
          }
          .dropzone {
            position: relative;
            z-index: 1;
            margin-top: 28px;
            border: 2px dashed rgba(226, 135, 9, 0.8);
            border-radius: 28px;
            padding: 38px 24px 32px;
            background: linear-gradient(180deg, rgba(255, 251, 238, 0.88), rgba(250, 241, 212, 0.94));
            text-align: center;
          }
          label {
            cursor: pointer;
          }
          input[type="file"] {
            display: none;
          }
          .upload-button {
            width: 72px;
            height: 72px;
            margin: 0 auto 22px;
            display: grid;
            place-items: center;
            border-radius: 24px;
            background: linear-gradient(180deg, #f2a012, #e18405);
            box-shadow: 0 16px 24px rgba(225, 132, 5, 0.24);
            color: white;
          }
          .upload-button svg {
            width: 32px;
            height: 32px;
          }
          .dropzone h2 {
            margin: 0;
            font-size: clamp(24px, 5vw, 33px);
            line-height: 1.12;
            color: #24324c;
          }
          .dropzone p {
            margin: 10px 0 0;
            font-size: 16px;
            color: #98a3b7;
          }
          .file-name {
            min-height: 20px;
            margin-top: 14px;
            font-size: 14px;
            color: var(--banana-dark);
          }
          .chips {
            margin-top: 18px;
            display: flex;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
          }
          .chip {
            padding: 7px 12px;
            border-radius: 999px;
            background: var(--chip);
            color: var(--banana-dark);
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.06em;
          }
          .actions {
            margin-top: 20px;
            display: flex;
            justify-content: center;
          }
          button {
            appearance: none;
            border: 0;
            border-radius: 999px;
            padding: 15px 28px;
            font-size: 15px;
            font-weight: 800;
            color: white;
            background: linear-gradient(180deg, #f09a0d 0%, #d87d00 100%);
            box-shadow: 0 16px 26px rgba(216, 125, 0, 0.22);
            cursor: pointer;
            transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
          }
          button:hover {
            transform: translateY(-1px);
            box-shadow: 0 20px 30px rgba(216, 125, 0, 0.26);
          }
          button:disabled {
            opacity: 0.58;
            cursor: not-allowed;
            transform: none;
          }
          button.is-busy,
          button.is-busy:disabled {
            cursor: wait;
          }
          .status {
            margin-top: 24px;
            min-height: 24px;
            text-align: center;
            font-size: 14px;
            color: var(--muted);
          }
          .status.error {
            color: #b54708;
          }
          .status.success {
            color: #2f7f43;
          }
          .feature-grid {
            position: relative;
            z-index: 1;
            margin-top: 24px;
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 18px;
          }
          .feature {
            min-height: 72px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 14px 12px;
            border-radius: 18px;
            background: rgba(235, 226, 211, 0.74);
            color: #776d60;
            text-align: center;
            font-weight: 700;
          }
          .feature-badge {
            min-width: 32px;
            height: 32px;
            padding: 0 8px;
            display: grid;
            place-items: center;
            border-radius: 999px;
            background: rgba(226, 135, 9, 0.14);
            color: var(--banana-dark);
            font-size: 11px;
            font-weight: 900;
            letter-spacing: 0.08em;
          }
          .feature-copy {
            line-height: 1.24;
          }
          .assist {
            margin-top: 18px;
            text-align: center;
            font-size: 13px;
            color: #8a95aa;
          }
          .assist strong {
            color: var(--ink);
          }
          .modal {
            position: fixed;
            inset: 0;
            display: none;
            place-items: center;
            padding: 20px;
            background: var(--overlay);
            z-index: 20;
          }
          .modal.visible {
            display: grid;
          }
          .modal-card {
            width: min(100%, 440px);
            padding: 28px 24px;
            border-radius: 28px;
            background: rgba(255, 251, 240, 0.98);
            border: 1px solid rgba(224, 205, 163, 0.92);
            box-shadow: 0 24px 60px rgba(50, 38, 15, 0.22);
          }
          .modal-card h3 {
            margin: 0;
            font-size: 28px;
            line-height: 1.05;
            color: var(--ink);
          }
          .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
          }
          .close-modal-btn {
            flex-shrink: 0;
            width: 32px;
            height: 32px;
            padding: 0;
            border-radius: 999px;
            background: rgba(236, 225, 203, 0.95);
            color: #65563d;
            font-size: 20px;
            line-height: 1;
            box-shadow: none;
          }
          .close-modal-btn:hover {
            background: rgba(226, 215, 193, 0.98);
          }
          .modal-card p {
            margin: 14px 0 0;
            font-size: 15px;
            line-height: 1.55;
            color: #6c7890;
          }
          .modal-card ul {
            margin: 14px 0 0;
            padding-left: 18px;
            color: #6c7890;
            font-size: 14px;
            line-height: 1.5;
          }
          .consent {
            display: flex;
            gap: 10px;
            align-items: flex-start;
            margin-top: 18px;
            padding: 12px 14px;
            border-radius: 16px;
            background: rgba(244, 231, 193, 0.42);
            color: #5d563f;
            font-size: 14px;
          }
          .consent input {
            margin-top: 3px;
          }
          .modal-actions {
            display: flex;
            gap: 12px;
            margin-top: 18px;
            flex-wrap: wrap;
          }
          .url-config {
            margin-top: 16px;
          }
          .render-mode {
            margin-top: 16px;
          }
          .render-mode-options {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-top: 10px;
          }
          .render-mode-option {
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 14px 14px 14px 42px;
            border: 1px solid rgba(215, 190, 136, 0.92);
            border-radius: 16px;
            background: rgba(255, 252, 245, 0.96);
            cursor: pointer;
          }
          .render-mode-option input {
            position: absolute;
            top: 16px;
            left: 14px;
          }
          .render-mode-option strong {
            font-size: 14px;
            color: var(--ink);
          }
          .render-mode-option span {
            font-size: 12px;
            line-height: 1.45;
            color: #7c879b;
          }
          .runtime-note {
            margin-top: 10px;
            font-size: 12px;
            line-height: 1.45;
            color: #8b95aa;
          }
          .advanced-settings {
            margin-top: 16px;
            border: 1px solid rgba(224, 205, 163, 0.92);
            border-radius: 18px;
            background: rgba(250, 243, 226, 0.72);
            overflow: hidden;
          }
          .advanced-settings summary {
            list-style: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 16px;
            color: #5d563f;
            font-size: 14px;
            font-weight: 800;
            cursor: pointer;
            user-select: none;
          }
          .advanced-settings summary::-webkit-details-marker {
            display: none;
          }
          .advanced-settings summary::after {
            content: "+";
            font-size: 18px;
            line-height: 1;
            color: var(--banana-dark);
          }
          .advanced-settings[open] summary::after {
            content: "−";
          }
          .advanced-settings-body {
            padding: 0 16px 16px;
            border-top: 1px solid rgba(224, 205, 163, 0.72);
          }
          .url-config label {
            display: block;
            margin-bottom: 8px;
            color: #5d563f;
            font-size: 14px;
            font-weight: 700;
            cursor: default;
          }
          .url-config input {
            width: 100%;
            border: 1px solid rgba(215, 190, 136, 0.92);
            border-radius: 14px;
            padding: 12px 14px;
            font-size: 14px;
            color: var(--ink);
            background: rgba(255, 252, 245, 0.98);
          }
          .url-config input:focus {
            outline: 2px solid rgba(226, 135, 9, 0.26);
            border-color: rgba(226, 135, 9, 0.9);
          }
          .field-hint {
            margin-top: 8px;
            font-size: 12px;
            line-height: 1.45;
            color: #8b95aa;
          }
          .secondary-button {
            background: rgba(236, 225, 203, 0.95);
            color: #65563d;
            box-shadow: none;
          }
          .model-status-btn {
            position: absolute;
            top: 18px;
            right: 18px;
            padding: 8px 14px;
            font-size: 13px;
            border-radius: 999px;
            background: rgba(236, 225, 203, 0.95);
            color: #65563d;
            box-shadow: none;
            z-index: 10;
          }
          .model-status-btn:hover {
            background: rgba(226, 215, 193, 0.98);
          }
          .danger-button {
            background: #fff1ec;
            color: #af3f17;
            box-shadow: none;
          }
          .modal-note {
            margin-top: 14px;
            min-height: 20px;
            font-size: 13px;
            color: #8b95aa;
          }
          .modal-note.error {
            color: #b54708;
          }
          .modal-note.success {
            color: #2f7f43;
          }
          .progress-wrap {
            margin-top: 16px;
          }
          .progress-label {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            font-size: 13px;
            color: #6c7890;
          }
          .progress-bar {
            margin-top: 8px;
            height: 10px;
            border-radius: 999px;
            background: rgba(230, 214, 183, 0.85);
            overflow: hidden;
          }
          .progress-fill {
            width: 0%;
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, #f0a318 0%, #dd7f00 100%);
            transition: width 180ms ease;
          }
          .hidden {
            display: none;
          }
          @media (max-width: 820px) {
            .panel {
              padding: 34px 22px 26px;
              border-radius: 28px;
            }
            .brand {
              align-items: flex-start;
            }
            .brand img {
              width: 72px;
              height: 72px;
            }
            .feature-grid {
              grid-template-columns: 1fr;
              gap: 12px;
            }
            .stamp {
              width: 88px;
              height: 88px;
            }
            .modal-actions {
              flex-direction: column;
            }
          }
        </style>
      </head>
      <body>
        <main class="shell">
          <section id="main-panel" class="panel blocked">
            <button id="model-status-btn" class="model-status-btn hidden" type="button">Model Settings</button>
            <div class="stamp stamp-left"></div>
            <div class="stamp stamp-right"></div>
            <div class="brand">
              <img src="/static/banana.jpg" alt="Edit Banana logo" />
              <h1>Edit Banana</h1>
            </div>
            <p id="tagline" class="tagline">Transform your images or PDF into editable Draw.io diagrams with AI magic</p>
            <form id="convert-form">
              <div class="dropzone">
                <label for="file">
                  <span class="upload-button" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none">
                      <path d="M12 16V4m0 0-4 4m4-4 4 4M5 14v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                  </span>
                  <h2 id="drop-title">Drop your images or PDF here</h2>
                  <p id="drop-subtitle">or click to browse</p>
                </label>
                <input id="file" type="file" accept=".png,.jpg,.jpeg,.pdf,.bmp,.tiff,.webp" />
                <div id="file-name" class="file-name"></div>
                <div class="chips">
                  <span class="chip">JPG</span>
                  <span class="chip">PNG</span>
                  <span class="chip">WEBP</span>
                  <span class="chip">PDF</span>
                </div>
              </div>
              <div class="actions">
                <button id="submit" type="submit">Convert and download</button>
              </div>
              <div id="status" class="status">Checking model status...</div>
            </form>
            <div class="feature-grid" aria-hidden="true">
              <div class="feature"><span class="feature-badge">AI</span><span id="feature-ai" class="feature-copy">AI-<br/>Powered</span></div>
              <div class="feature"><span class="feature-badge">ED</span><span id="feature-edit" class="feature-copy">Fully<br/>Editable</span></div>
              <div class="feature"><span class="feature-badge">IO</span><span id="feature-export" class="feature-copy">Export to<br/>Draw.io</span></div>
            </div>
            <div id="assist" class="assist">Upload one file and the generated <strong>.drawio.xml</strong> download will start automatically.</div>
          </section>
        </main>

        <div id="model-modal" class="modal visible" role="dialog" aria-modal="true" aria-labelledby="modal-title">
          <div class="modal-card">
            <div class="modal-header">
              <h3 id="modal-title">Prepare model files</h3>
              <button id="close-modal" class="close-modal-btn hidden" type="button" aria-label="Close">×</button>
            </div>
            <p id="modal-body">This app needs model files before it can convert diagrams.</p>
            <ul id="missing-files"></ul>
            <div id="progress-wrap" class="progress-wrap hidden">
              <div class="progress-label">
                <span id="progress-file">Preparing download</span>
                <span id="progress-percent">0%</span>
              </div>
              <div class="progress-bar">
                <div id="progress-fill" class="progress-fill"></div>
              </div>
            </div>
            <label class="consent" for="consent-checkbox">
              <input id="consent-checkbox" type="checkbox" />
              <span id="consent-text">I agree to download the required model files into this workspace storage.</span>
            </label>
            <details id="advanced-download-settings" class="advanced-settings">
              <summary id="advanced-settings-summary">Advanced settings</summary>
              <div class="advanced-settings-body">
                <div class="render-mode">
                  <label id="render-mode-label">SAM3 render mode</label>
                  <div class="render-mode-options">
                    <label class="render-mode-option" for="sam3-device-cpu">
                      <input id="sam3-device-cpu" type="radio" name="sam3-device" value="cpu" />
                      <strong id="render-mode-cpu-title">CPU</strong>
                      <span id="render-mode-cpu-hint">Compatible path for the current image build.</span>
                    </label>
                    <label class="render-mode-option" for="sam3-device-cuda">
                      <input id="sam3-device-cuda" type="radio" name="sam3-device" value="cuda" />
                      <strong id="render-mode-gpu-title">GPU</strong>
                      <span id="render-mode-gpu-hint">Use upstream CUDA mode when the runtime provides a GPU.</span>
                    </label>
                  </div>
                  <div id="runtime-note" class="runtime-note">The selection is saved to workspace storage and applied to the next conversion request.</div>
                </div>
                <div class="url-config">
                  <label id="checkpoint-url-label" for="checkpoint-url">Custom SAM3 checkpoint URL (optional)</label>
                  <input id="checkpoint-url" type="url" spellcheck="false" placeholder="Leave blank to use the default mirror" />
                  <div id="checkpoint-url-hint" class="field-hint">Leave this empty to use the built-in default source. Filling it will save your custom address for later retries.</div>
                </div>
              </div>
            </details>
            <div class="modal-actions">
              <button id="download-models" type="button">Download and continue</button>
              <button id="refresh-status" class="secondary-button" type="button">Refresh status</button>
              <button id="reset-download" class="danger-button hidden" type="button">Delete and retry</button>
            </div>
            <div id="modal-note" class="modal-note">Waiting for confirmation.</div>
          </div>
        </div>

        <script>
          const messages = {
            en: {
              tagline: "Transform your images or PDF into editable Draw.io diagrams with AI magic",
              dropTitle: "Drop your images or PDF here",
              dropSubtitle: "or click to browse",
              submit: "Convert and download",
              checking: "Checking model status...",
              featureAi: "AI-<br/>Powered",
              featureEdit: "Fully<br/>Editable",
              featureExport: "Export to<br/>Draw.io",
              assist: "Upload one file and the generated <strong>.drawio.xml</strong> download will start automatically.",
              modalTitle: "Prepare model files",
              modalBodyNeed: "This app needs model files before it can convert diagrams.",
              modalBodyUnavailable: "The required model files are missing, and at least one download link is not configured yet.",
              modalBodyDownloading: "Model download is running. This page will unlock once the files are ready.",
              consent: "I agree to download the required model files into this workspace storage.",
              download: "Download and continue",
              refresh: "Refresh status",
              reset: "Delete and retry",
              waiting: "Waiting for confirmation.",
              ready: "Ready when you are.",
              selectFirst: "Select a file first.",
              uploading: "Uploading and converting. Large files can take a while.",
              convertDone: "Conversion finished. Download started.",
              modelNotReady: "Models are not ready yet.",
              modelNotConfigured: "Model download is not configured yet.",
              refreshFailed: "Failed to load model status.",
              refreshing: "Refreshing status...",
              confirmFirst: "Please confirm the download agreement first.",
              downloading: "Downloading model files. This can take several minutes.",
              downloadDone: "Download complete. Unlocking the upload page.",
              resetDone: "Failed files were removed. You can start the download again.",
              resetting: "Deleting downloaded files...",
              resetFailed: "Failed to delete downloaded files.",
              missingCheckpoint: "SAM3 checkpoint",
              missingTokenizer: "Tokenizer",
              progressPreparing: "Preparing download",
              downloadUnavailable: "Download unavailable",
              downloadLinkMissingTag: "download link missing",
              downloadConfigPrefix: "Missing download link for:",
              checkpointUrlLabel: "Custom SAM3 checkpoint URL (optional)",
              checkpointUrlPlaceholder: "Leave blank to use the default mirror",
              checkpointUrlHint: "Leave this empty to use the built-in default source. Filling it will save your custom address for later retries.",
              checkpointUrlSaved: "Custom download address saved.",
              usingDefaultSource: "Using the default model source.",
              advancedSettings: "Advanced settings",
              modelStatusBtn: "Model Settings",
              closeModal: "Close",
              renderModeLabel: "SAM3 render mode",
              renderModeCpuTitle: "CPU",
              renderModeCpuHint: "Compatible path for the current image build.",
              renderModeGpuTitle: "GPU",
              renderModeGpuHint: "Use upstream CUDA mode when the runtime provides a GPU.",
              runtimeSaved: "Render mode saved.",
              runtimeSaveFailed: "Failed to save render mode.",
              runtimeHint: "The selection is saved to workspace storage and applied to the next conversion request.",
            },
            zh: {
              tagline: "把图片或 PDF 转成可编辑的 Draw.io 图，交给 AI 处理",
              dropTitle: "将图片或 PDF 拖到这里",
              dropSubtitle: "或点击选择文件",
              submit: "转换并下载",
              checking: "正在检查模型状态...",
              featureAi: "AI<br/>驱动",
              featureEdit: "完全<br/>可编辑",
              featureExport: "导出为<br/>Draw.io",
              assist: "上传单个文件后，系统会自动开始下载生成的 <strong>.drawio.xml</strong> 文件。",
              modalTitle: "准备模型文件",
              modalBodyNeed: "在开始转换前，需要先下载模型文件。",
              modalBodyUnavailable: "缺少模型文件，而且至少有一个下载地址还没有配置。",
              modalBodyDownloading: "模型下载进行中，文件准备完成后页面会自动解锁。",
              consent: "我同意将所需模型文件下载到当前工作区存储中。",
              download: "同意并开始下载",
              refresh: "刷新状态",
              reset: "删除后重下",
              waiting: "等待确认。",
              ready: "已经就绪，可以开始使用。",
              selectFirst: "请先选择一个文件。",
              uploading: "正在上传并转换，较大的文件会稍慢一些。",
              convertDone: "转换完成，已开始下载。",
              modelNotReady: "模型尚未准备好。",
              modelNotConfigured: "模型下载地址还没有配置好。",
              refreshFailed: "读取模型状态失败。",
              refreshing: "正在刷新状态...",
              confirmFirst: "请先勾选同意下载。",
              downloading: "正在下载模型文件，这可能需要几分钟。",
              downloadDone: "下载完成，正在解锁上传页面。",
              resetDone: "失败文件已删除，可以重新开始下载。",
              resetting: "正在删除已下载文件...",
              resetFailed: "删除已下载文件失败。",
              missingCheckpoint: "SAM3 模型权重",
              missingTokenizer: "Tokenizer 词表",
              progressPreparing: "正在准备下载",
              downloadUnavailable: "下载地址未配置",
              downloadLinkMissingTag: "未配置下载地址",
              downloadConfigPrefix: "以下文件缺少下载地址：",
              checkpointUrlLabel: "自定义 SAM3 模型下载地址（可选）",
              checkpointUrlPlaceholder: "留空则使用默认镜像地址",
              checkpointUrlHint: "留空会使用内置默认下载源；填写后会保存你的自定义地址，后续重试继续使用。",
              checkpointUrlSaved: "自定义下载地址已保存。",
              usingDefaultSource: "当前使用默认模型下载源。",
              advancedSettings: "高级设置",
              modelStatusBtn: "模型设置",
              closeModal: "关闭",
              renderModeLabel: "SAM3 渲染方式",
              renderModeCpuTitle: "CPU",
              renderModeCpuHint: "兼容当前这套镜像构建的保守模式。",
              renderModeGpuTitle: "GPU",
              renderModeGpuHint: "在运行环境提供 GPU 时，按上游 CUDA 模式执行。",
              runtimeSaved: "渲染方式已保存。",
              runtimeSaveFailed: "保存渲染方式失败。",
              runtimeHint: "选择会保存到当前工作区存储，并在下一次转换请求时生效。",
            },
          };

          const locale = navigator.language && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
          const t = (key) => messages[locale][key] || messages.en[key] || key;
          const fieldLabels = {
            checkpoint: () => t("missingCheckpoint"),
            tokenizer: () => t("missingTokenizer"),
          };

          const form = document.getElementById("convert-form");
          const fileInput = document.getElementById("file");
          const submitButton = document.getElementById("submit");
          const statusEl = document.getElementById("status");
          const fileNameEl = document.getElementById("file-name");
          const mainPanel = document.getElementById("main-panel");
          const modelModal = document.getElementById("model-modal");
          const modelStatusBtn = document.getElementById("model-status-btn");
          const modalBody = document.getElementById("modal-body");
          const missingFiles = document.getElementById("missing-files");
          const consentCheckbox = document.getElementById("consent-checkbox");
          const downloadButton = document.getElementById("download-models");
          const refreshButton = document.getElementById("refresh-status");
          const resetButton = document.getElementById("reset-download");
          const modalNote = document.getElementById("modal-note");
          const progressWrap = document.getElementById("progress-wrap");
          const progressFill = document.getElementById("progress-fill");
          const progressFile = document.getElementById("progress-file");
          const progressPercent = document.getElementById("progress-percent");
          const advancedSettings = document.getElementById("advanced-download-settings");
          const checkpointUrlInput = document.getElementById("checkpoint-url");
          const checkpointUrlHint = document.getElementById("checkpoint-url-hint");
          const closeModalBtn = document.getElementById("close-modal");
          const runtimeNote = document.getElementById("runtime-note");
          const sam3DeviceInputs = Array.from(document.querySelectorAll('input[name="sam3-device"]'));

          let pollTimer = null;
          let currentModelState = null;
          let modalPinnedOpen = false;
          let refreshRequestId = 0;
          let suppressDeviceSave = false;

          function localizeStaticText() {
            document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
            document.getElementById("tagline").textContent = t("tagline");
            document.getElementById("drop-title").textContent = t("dropTitle");
            document.getElementById("drop-subtitle").textContent = t("dropSubtitle");
            document.getElementById("submit").textContent = t("submit");
            document.getElementById("status").textContent = t("checking");
            document.getElementById("feature-ai").innerHTML = t("featureAi");
            document.getElementById("feature-edit").innerHTML = t("featureEdit");
            document.getElementById("feature-export").innerHTML = t("featureExport");
            document.getElementById("assist").innerHTML = t("assist");
            document.getElementById("modal-title").textContent = t("modalTitle");
            document.getElementById("modal-body").textContent = t("modalBodyNeed");
            document.getElementById("consent-text").textContent = t("consent");
            document.getElementById("download-models").textContent = t("download");
            document.getElementById("refresh-status").textContent = t("refresh");
            document.getElementById("reset-download").textContent = t("reset");
            document.getElementById("modal-note").textContent = t("waiting");
            document.getElementById("progress-file").textContent = t("progressPreparing");
            document.getElementById("advanced-settings-summary").textContent = t("advancedSettings");
            document.getElementById("render-mode-label").textContent = t("renderModeLabel");
            document.getElementById("render-mode-cpu-title").textContent = t("renderModeCpuTitle");
            document.getElementById("render-mode-cpu-hint").textContent = t("renderModeCpuHint");
            document.getElementById("render-mode-gpu-title").textContent = t("renderModeGpuTitle");
            document.getElementById("render-mode-gpu-hint").textContent = t("renderModeGpuHint");
            document.getElementById("runtime-note").textContent = t("runtimeHint");
            document.getElementById("checkpoint-url-label").textContent = t("checkpointUrlLabel");
            document.getElementById("checkpoint-url").placeholder = t("checkpointUrlPlaceholder");
            document.getElementById("checkpoint-url-hint").textContent = t("checkpointUrlHint");
            document.getElementById("model-status-btn").textContent = t("modelStatusBtn");
          }

          function formatBytes(value) {
            if (!value) return "0 B";
            const units = ["B", "KB", "MB", "GB"];
            let size = value;
            let unit = 0;
            while (size >= 1024 && unit < units.length - 1) {
              size /= 1024;
              unit += 1;
            }
            return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
          }

          function setStatus(message, kind) {
            statusEl.textContent = message;
            statusEl.className = "status" + (kind ? " " + kind : "");
          }

          function setModalNote(message, kind) {
            modalNote.textContent = message;
            modalNote.className = "modal-note" + (kind ? " " + kind : "");
          }

          function setBusyState(button, isBusy) {
            button.classList.toggle("is-busy", Boolean(isBusy));
          }

          function syncDownloadConfig(state) {
            const config = state.download_config || {};
            const hasCustomUrl = Boolean(config.checkpoint_url);
            if (document.activeElement !== checkpointUrlInput) {
              checkpointUrlInput.value = config.checkpoint_url || "";
            }
            if (hasCustomUrl) {
              advancedSettings.open = true;
            }

            checkpointUrlHint.textContent =
              config.checkpoint_source === "custom"
                ? t("checkpointUrlSaved")
                : t("checkpointUrlHint");
          }

          function syncRuntimeSettings(state) {
            const runtime = state.runtime_settings || {};
            suppressDeviceSave = true;
            sam3DeviceInputs.forEach((input) => {
              input.checked = input.value === runtime.sam3_device;
            });
            suppressDeviceSave = false;
            runtimeNote.textContent = t("runtimeHint");
          }

          function stopPolling() {
            if (pollTimer) {
              window.clearTimeout(pollTimer);
              pollTimer = null;
            }
          }

          function schedulePolling() {
            stopPolling();
            pollTimer = window.setTimeout(async () => {
              await refreshModelStatus();
            }, 1200);
          }

          function getFileLabel(key, fallbackLabel) {
            if (fieldLabels[key]) {
              return fieldLabels[key]();
            }
            return fallbackLabel || key;
          }

          function getMissingDownloadLinks(state) {
            return (state.files || []).filter((file) => !file.exists && !file.url_configured);
          }

          function getNotConfiguredMessage(state) {
            const missingLinks = getMissingDownloadLinks(state);
            if (!missingLinks.length) {
              return t("modelNotConfigured");
            }

            const separator = locale === "zh" ? "、" : ", ";
            const names = missingLinks.map((file) => getFileLabel(file.key, file.label)).join(separator);
            return `${t("downloadConfigPrefix")} ${names}`;
          }

          function renderMissingFiles(keys, files) {
            const filesByKey = new Map((files || []).map((file) => [file.key, file]));
            missingFiles.innerHTML = "";
            keys.forEach((key) => {
              const file = filesByKey.get(key);
              const li = document.createElement("li");
              const label = getFileLabel(key, file && file.label);
              li.textContent =
                file && !file.exists && !file.url_configured
                  ? `${label} (${t("downloadLinkMissingTag")})`
                  : label;
              missingFiles.appendChild(li);
            });
            missingFiles.classList.toggle("hidden", keys.length === 0);
          }

          function updateProgress(progress) {
            const isActive = progress.status === "downloading";
            progressWrap.classList.toggle("hidden", !isActive);
            if (!isActive) {
              progressFill.style.width = "0%";
              progressPercent.textContent = "0%";
              progressFile.textContent = t("progressPreparing");
              return;
            }

            const fileKey = progress.current_file;
            const fileLabel = fieldLabels[fileKey] ? fieldLabels[fileKey]() : t("progressPreparing");
            progressFile.textContent =
              progress.total_bytes > 0
                ? `${fileLabel} · ${formatBytes(progress.current_bytes)} / ${formatBytes(progress.total_bytes)}`
                : `${fileLabel} · ${formatBytes(progress.current_bytes)}`;

            const percent = progress.total_bytes > 0 ? Math.min(progress.percent || 0, 100) : 0;
            progressPercent.textContent = progress.total_bytes > 0 ? `${Math.round(percent)}%` : "...";
            progressFill.style.width = progress.total_bytes > 0 ? `${percent}%` : "12%";
          }

          function applyModelState(state) {
            currentModelState = state;
            updateProgress(state.progress);
            syncDownloadConfig(state);
            syncRuntimeSettings(state);
            setBusyState(downloadButton, false);
            setBusyState(refreshButton, false);
            setBusyState(resetButton, false);
            downloadButton.textContent = t("download");
            const ready = Boolean(state.ready);
            const downloading = state.progress.status === "downloading";

            mainPanel.classList.toggle("blocked", !ready);
            submitButton.disabled = !ready;
            modelModal.classList.toggle("visible", !ready || modalPinnedOpen);
            modelStatusBtn.classList.toggle("hidden", !ready || modalPinnedOpen);
            closeModalBtn.classList.toggle("hidden", !(ready && modalPinnedOpen));

            if (ready) {
              stopPolling();
              resetButton.classList.add("hidden");
              setStatus(t("ready"), "");
              return;
            }

            renderMissingFiles(state.missing_keys || [], state.files || []);

            if (downloading) {
              modalBody.textContent = t("modalBodyDownloading");
              downloadButton.disabled = true;
              refreshButton.disabled = true;
              resetButton.classList.add("hidden");
              setBusyState(downloadButton, true);
              setModalNote(t("downloading"), "");
              setStatus(t("downloading"), "");
              schedulePolling();
              return;
            }

            stopPolling();

            if (state.progress.status === "error") {
              modalBody.textContent = t("modalBodyNeed");
              downloadButton.disabled = false;
              refreshButton.disabled = false;
              resetButton.classList.remove("hidden");
              setModalNote(state.progress.error || t("resetFailed"), "error");
              setStatus(state.progress.error || t("resetFailed"), "error");
              return;
            }

            if (!state.downloadable) {
              modalBody.textContent = t("modalBodyUnavailable");
              downloadButton.disabled = false;
              downloadButton.textContent = t("downloadUnavailable");
              refreshButton.disabled = false;
              resetButton.classList.add("hidden");
              const detail = getNotConfiguredMessage(state);
              setModalNote(detail, "error");
              setStatus(detail, "error");
              return;
            }

            modalBody.textContent = t("modalBodyNeed");
            downloadButton.disabled = false;
            refreshButton.disabled = false;
            resetButton.classList.add("hidden");
            setModalNote(t("waiting"), "");
            setStatus(t("modelNotReady"), "");
          }

          async function fetchModelStatus() {
            const response = await fetch("/model-status", { cache: "no-store" });
            if (!response.ok) {
              throw new Error(t("refreshFailed"));
            }
            return response.json();
          }

          async function refreshModelStatus() {
            const requestId = ++refreshRequestId;
            try {
              const state = await fetchModelStatus();
              if (requestId !== refreshRequestId) {
                return state;
              }
              applyModelState(state);
              return state;
            } catch (error) {
              if (requestId !== refreshRequestId) {
                return null;
              }
              stopPolling();
              setModalNote(error.message || t("refreshFailed"), "error");
              setStatus(error.message || t("refreshFailed"), "error");
              modelModal.classList.add("visible");
              return null;
            }
          }

          modelStatusBtn.addEventListener("click", () => {
            modalPinnedOpen = true;
            if (currentModelState) {
              applyModelState(currentModelState);
            } else {
              modelModal.classList.add("visible");
              modelStatusBtn.classList.add("hidden");
              closeModalBtn.classList.remove("hidden");
            }
          });

          closeModalBtn.addEventListener("click", () => {
            modalPinnedOpen = false;
            if (currentModelState) {
              applyModelState(currentModelState);
            } else {
              modelModal.classList.remove("visible");
              modelStatusBtn.classList.remove("hidden");
            }
          });

          sam3DeviceInputs.forEach((input) => {
            input.addEventListener("change", async () => {
              if (suppressDeviceSave || !input.checked) {
                return;
              }

              try {
                const response = await fetch("/runtime-settings", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ sam3_device: input.value }),
                });
                if (!response.ok) {
                  let detail = t("runtimeSaveFailed");
                  try {
                    const payload = await response.json();
                    detail = payload.detail || detail;
                  } catch (_err) {
                  }
                  throw new Error(detail);
                }

                const runtime = await response.json();
                currentModelState = {
                  ...(currentModelState || {}),
                  runtime_settings: runtime,
                };
                runtimeNote.textContent = t("runtimeSaved");
              } catch (error) {
                runtimeNote.textContent = error.message || t("runtimeSaveFailed");
                if (currentModelState) {
                  syncRuntimeSettings(currentModelState);
                }
              }
            });
          });

          fileInput.addEventListener("change", () => {
            const file = fileInput.files[0];
            fileNameEl.textContent = file
              ? locale === "zh"
                ? `已选择：${file.name}`
                : `Selected: ${file.name}`
              : "";
          });

          refreshButton.addEventListener("click", async () => {
            refreshButton.disabled = true;
            setBusyState(refreshButton, true);
            setModalNote(t("refreshing"), "");
            await refreshModelStatus();
            refreshButton.disabled = false;
            setBusyState(refreshButton, false);
          });

          resetButton.addEventListener("click", async () => {
            resetButton.disabled = true;
            downloadButton.disabled = true;
            refreshButton.disabled = true;
            setBusyState(resetButton, true);
            setModalNote(t("resetting"), "");

            try {
              const response = await fetch("/initialize-models", { method: "DELETE" });
              if (!response.ok) {
                let detail = t("resetFailed");
                try {
                  const payload = await response.json();
                  detail = payload.detail || detail;
                } catch (_err) {
                }
                throw new Error(detail);
              }

              consentCheckbox.checked = false;
              setModalNote(t("resetDone"), "success");
              await refreshModelStatus();
            } catch (error) {
              setModalNote(error.message || t("resetFailed"), "error");
            } finally {
              resetButton.disabled = false;
              downloadButton.disabled = false;
              refreshButton.disabled = false;
              setBusyState(resetButton, false);
            }
          });

          downloadButton.addEventListener("click", async () => {
            if (currentModelState && !currentModelState.downloadable) {
              const detail = getNotConfiguredMessage(currentModelState);
              setModalNote(detail, "error");
              setStatus(detail, "error");
              return;
            }

            if (!consentCheckbox.checked) {
              setModalNote(t("confirmFirst"), "error");
              return;
            }

            downloadButton.disabled = true;
            refreshButton.disabled = true;
            resetButton.classList.add("hidden");
            setBusyState(downloadButton, true);
            setModalNote(t("downloading"), "");
            setStatus(t("downloading"), "");

            // Show progress bar immediately to indicate download is starting
            progressWrap.classList.remove("hidden");
            progressFile.textContent = t("progressPreparing");
            progressPercent.textContent = "0%";
            progressFill.style.width = "0%";

            modalPinnedOpen = false;
            modelModal.classList.add("visible");

            try {
              const response = await fetch("/initialize-models", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  checkpoint_url: checkpointUrlInput.value.trim() || null,
                }),
              });
              if (!response.ok) {
                let detail = t("modelNotConfigured");
                try {
                  const payload = await response.json();
                  detail = payload.detail || detail;
                } catch (_err) {
                }
                throw new Error(detail);
              }

              const state = await refreshModelStatus();
              if (state && state.ready) {
                setModalNote(t("downloadDone"), "success");
              }
            } catch (error) {
              setModalNote(error.message || t("modelNotConfigured"), "error");
              setStatus(error.message || t("modelNotConfigured"), "error");
              downloadButton.disabled = false;
              refreshButton.disabled = false;
              resetButton.classList.remove("hidden");
              setBusyState(downloadButton, false);
              // Hide progress bar on error
              progressWrap.classList.add("hidden");
            }
          });

          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const file = fileInput.files[0];
            if (!file) {
              setStatus(t("selectFirst"), "error");
              return;
            }

            const formData = new FormData();
            formData.append("file", file);

            submitButton.disabled = true;
            setStatus(t("uploading"), "");

            try {
              const response = await fetch("/convert", {
                method: "POST",
                body: formData,
              });

              if (!response.ok) {
                let detail = "Conversion failed.";
                try {
                  const payload = await response.json();
                  detail = payload.detail || detail;
                } catch (_err) {
                }
                throw new Error(detail);
              }

              const blob = await response.blob();
              const disposition = response.headers.get("content-disposition") || "";
              const match = disposition.match(/filename="?([^"]+)"?/);
              const downloadName = match ? match[1] : "edit-banana-output.drawio.xml";

              const url = window.URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = downloadName;
              document.body.appendChild(link);
              link.click();
              link.remove();
              window.URL.revokeObjectURL(url);
              setStatus(t("convertDone"), "success");
            } catch (error) {
              setStatus(error.message || "Conversion failed.", "error");
            } finally {
              submitButton.disabled = false;
            }
          });

          localizeStaticText();
          console.log("[init] page loaded, VERSION=2, calling refreshModelStatus...");
          refreshModelStatus();
        </script>
      </body>
    </html>
    """


@app.get("/model-status")
def model_status():
    return _model_status()


@app.get("/runtime-settings")
def runtime_settings():
    return _runtime_settings_payload()


@app.post("/runtime-settings")
def update_runtime_settings(payload: RuntimeSettingsRequest):
    normalized_device = _normalize_device(payload.sam3_device)
    if not normalized_device:
        raise HTTPException(status_code=400, detail="Unsupported SAM3 device. Use cpu or cuda.")

    _save_runtime_device(normalized_device)
    return _runtime_settings_payload()


@app.post("/initialize-models", status_code=202)
def initialize_models(payload: Optional[InitializeModelsRequest] = None):
    if payload is not None:
        _save_download_overrides(payload.checkpoint_url)

    status = _model_status()
    if status["ready"]:
        return {"status": "ok", "ready": True}

    if not status["downloadable"]:
        raise HTTPException(status_code=400, detail="Model download is not configured yet.")

    if not MODEL_DOWNLOAD_LOCK.acquire(blocking=False):
        return {"status": "accepted", "ready": False}

    thread = threading.Thread(target=_download_models_worker, daemon=True)
    thread.start()
    return {"status": "accepted", "ready": False}


@app.delete("/initialize-models")
def reset_models():
    if MODEL_DOWNLOAD_LOCK.locked():
        raise HTTPException(status_code=409, detail="Model download is in progress.")

    for file_info in _model_definitions():
        for path in (file_info["path"], f"{file_info['path']}.tmp"):
            if os.path.exists(path):
                os.unlink(path)

    _reset_download_state()
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    name = file.filename or "diagram"
    ext = Path(name).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".pdf", ".bmp", ".tiff", ".webp"}:
        raise HTTPException(status_code=400, detail="Unsupported format. Use image or PDF.")

    pipeline, output_dir = _load_pipeline()

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result_path = pipeline.process_image(
            tmp_path,
            output_dir=output_dir,
            with_refinement=False,
            with_text=True,
        )
        if not result_path or not os.path.exists(result_path):
            raise HTTPException(status_code=500, detail="Conversion failed.")

        result_file = Path(result_path)
        return FileResponse(
            path=result_path,
            media_type="application/xml",
            filename=result_file.name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
