#!/usr/bin/env python3

from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg", ".oga", ".opus"}
OPENAI_TRANSCRIPTION_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
DEFAULT_ATTACHMENT_LOG_DIR = "registry/auto-migration/logs/attachment-runs"
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class AttachmentRecognitionConfig:
    repo_root: Path
    enabled: bool = True
    log_dir: Path = Path(DEFAULT_ATTACHMENT_LOG_DIR)
    vision_model: str = "gpt-4.1-mini"
    transcription_model: str = "gpt-4o-mini-transcribe"
    api_key: str = ""


@dataclass(frozen=True)
class AttachmentRecognitionResult:
    kind: str
    filename: str
    url: str
    status: str
    text: str = ""
    error: str = ""
    local_path: str = ""


AttachmentRecognizer = Callable[[dict[str, Any], str], AttachmentRecognitionResult]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_id_from_now(now: str) -> str:
    return now.replace(":", "").replace("-", "")


def resolve_path(repo_root: Path, path: Path | str) -> Path:
    value = Path(path).expanduser()
    if value.is_absolute():
        return value
    return repo_root / value


def classify_attachment(attachment: dict[str, Any]) -> str:
    content_type = str(attachment.get("content_type", "") or "").lower()
    filename = str(attachment.get("filename", "") or "").lower()
    suffix = Path(filename).suffix.lower()
    if content_type.startswith("image/") or suffix in IMAGE_EXTENSIONS:
        return "image"
    if content_type.startswith("audio/") or suffix in AUDIO_EXTENSIONS:
        return "audio"
    return ""


def attachment_log_path(config: AttachmentRecognitionConfig, now: str) -> Path:
    return resolve_path(config.repo_root, config.log_dir) / f"{run_id_from_now(now)}.jsonl"


def append_attachment_event(
    config: AttachmentRecognitionConfig,
    *,
    now: str,
    message_id: str,
    attachment: dict[str, Any],
    result: AttachmentRecognitionResult,
) -> None:
    path = attachment_log_path(config, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "run_id": run_id_from_now(now),
        "timestamp": utc_now_iso(),
        "stage": "attachment_recognition",
        "item_id": message_id,
        "inputs": {"attachment": attachment, "kind": result.kind},
        "outputs": {"status": result.status, "text": result.text, "error": result.error, "local_path": result.local_path},
        "decision": {"status": result.status},
        "evidence": [result.text or result.error],
        "source": "scripts.discord_attachment_recognition",
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def openai_api_key(config: AttachmentRecognitionConfig) -> str:
    return config.api_key or os.environ.get("OPENAI_API_KEY", "").strip()


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "lzcat-discord-attachment-recognition/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - Discord/OpenAI attachment URL.
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"attachment too large: {content_length} bytes")
        data = response.read(MAX_ATTACHMENT_BYTES + 1)
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"attachment too large: {len(data)} bytes")
    return data


def extract_openai_text(payload: dict[str, Any]) -> str:
    output_text = str(payload.get("output_text", "")).strip()
    if output_text:
        return output_text
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or block.get("transcript") or "").strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def post_openai_json(api_key: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "lzcat-discord-attachment-recognition/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 - OpenAI API endpoint.
        return json.loads(response.read().decode("utf-8", errors="replace"))


def recognize_image(attachment: dict[str, Any], config: AttachmentRecognitionConfig) -> AttachmentRecognitionResult:
    filename = str(attachment.get("filename", "") or "image")
    url = str(attachment.get("url", "") or attachment.get("proxy_url", "") or "")
    if not url:
        return AttachmentRecognitionResult("image", filename, url, "failed", error="missing attachment url")
    message_id = str(attachment.get("_message_id", "") or "unknown").strip()
    safe_name = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in filename).strip("-") or "image"
    target_dir = config.repo_root / "registry" / "auto-migration" / "attachments" / message_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / safe_name
    target_path.write_bytes(download_bytes(url))
    return AttachmentRecognitionResult(
        "image",
        filename,
        url,
        "attached",
        text=f"图片已作为 Codex 原生图片附件传入：{target_path}",
        local_path=str(target_path),
    )


def multipart_form_data(fields: dict[str, str], file_field: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----lzcatAttachmentBoundary"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            data,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts), boundary


def convert_audio_for_openai(path: Path) -> Path:
    if path.suffix.lower() in OPENAI_TRANSCRIPTION_EXTENSIONS:
        return path
    converted = path.with_suffix(".mp3")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-vn", "-acodec", "libmp3lame", str(converted)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg conversion failed").strip())
    return converted


def transcribe_audio(attachment: dict[str, Any], config: AttachmentRecognitionConfig) -> AttachmentRecognitionResult:
    filename = str(attachment.get("filename", "") or "audio")
    url = str(attachment.get("url", "") or attachment.get("proxy_url", "") or "")
    if not url:
        return AttachmentRecognitionResult("audio", filename, url, "failed", error="missing attachment url")
    api_key = openai_api_key(config)
    if not api_key:
        return AttachmentRecognitionResult("audio", filename, url, "failed", error="OPENAI_API_KEY is not configured")

    suffix = Path(filename).suffix.lower() or mimetypes.guess_extension(str(attachment.get("content_type", ""))) or ".bin"
    with tempfile.TemporaryDirectory(prefix="lzcat-audio-") as tmp:
        input_path = Path(tmp) / f"input{suffix}"
        input_path.write_bytes(download_bytes(url))
        upload_path = convert_audio_for_openai(input_path)
        data = upload_path.read_bytes()
        content_type = mimetypes.guess_type(upload_path.name)[0] or "application/octet-stream"
        body, boundary = multipart_form_data(
            {"model": config.transcription_model, "response_format": "json"},
            "file",
            upload_path.name,
            content_type,
            data,
        )
        request = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "lzcat-discord-attachment-recognition/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - OpenAI API endpoint.
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    text = str(payload.get("text", "")).strip()
    return AttachmentRecognitionResult("audio", filename, url, "recognized" if text else "failed", text=text, error="" if text else "empty transcription response")


def default_recognizer(config: AttachmentRecognitionConfig) -> AttachmentRecognizer:
    def recognize(attachment: dict[str, Any], kind: str) -> AttachmentRecognitionResult:
        try:
            if kind == "image":
                return recognize_image(attachment, config)
            if kind == "audio":
                return transcribe_audio(attachment, config)
            return AttachmentRecognitionResult(kind, str(attachment.get("filename", "")), str(attachment.get("url", "")), "skipped", error="unsupported attachment")
        except Exception as exc:
            return AttachmentRecognitionResult(
                kind,
                str(attachment.get("filename", "")),
                str(attachment.get("url", "")),
                "failed",
                error=str(exc),
            )

    return recognize


def recognize_message_attachments(
    message: dict[str, Any],
    config: AttachmentRecognitionConfig,
    *,
    now: str,
    recognizer: AttachmentRecognizer | None = None,
) -> list[AttachmentRecognitionResult]:
    if not config.enabled:
        return []
    attachments = message.get("attachments")
    if not isinstance(attachments, list):
        return []
    recognize = recognizer or default_recognizer(config)
    message_id = str(message.get("id", "")).strip()
    results: list[AttachmentRecognitionResult] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        kind = classify_attachment(attachment)
        if not kind:
            continue
        attachment_payload = dict(attachment)
        attachment_payload["_message_id"] = message_id
        result = recognize(attachment_payload, kind)
        append_attachment_event(config, now=now, message_id=message_id, attachment=attachment_payload, result=result)
        results.append(result)
    return results


def build_attachment_instruction(content: str, results: list[AttachmentRecognitionResult]) -> str:
    clean_content = str(content or "").strip()
    lines = [clean_content] if clean_content else []
    if results:
        lines.extend(["", "附件识别结果："])
    for index, result in enumerate(results, start=1):
        header = f"{index}. {result.kind} `{result.filename}` status={result.status}"
        if result.text:
            lines.append(f"{header}\n{result.text}")
        elif result.error:
            lines.append(f"{header}\n识别失败：{result.error}")
        else:
            lines.append(header)
    return "\n".join(line for line in lines if line).strip()


def image_paths_from_results(results: list[AttachmentRecognitionResult]) -> tuple[str, ...]:
    return tuple(result.local_path for result in results if result.kind == "image" and result.local_path)
