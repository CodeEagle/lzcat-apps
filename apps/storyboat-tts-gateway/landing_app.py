from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from storyboat_tts_gateway.app import app as upstream_app


app = FastAPI(
    title=upstream_app.title,
    version=upstream_app.version,
    docs_url=upstream_app.docs_url,
    redoc_url=upstream_app.redoc_url,
    openapi_url=upstream_app.openapi_url,
)
app.include_router(upstream_app.router)

APP_DIR = Path(__file__).resolve().parent
PAGE_TEMPLATE = (APP_DIR / "landing_page.html").read_text(encoding="utf-8")


TRANSLATIONS = {
    "zh": {
        "html_lang": "zh-CN",
        "switch_label": "EN",
        "title": "StoryBoat TTS Gateway",
        "subtitle": "统一 Edge TTS 与 Kokoro 的音频合成网关",
        "summary": "默认提供真实词级时间戳、multipart 音频打包，以及基于 SSE 的异步任务流。",
        "quickstart": "Quickstart",
        "quickstart_desc": "示例地址会自动跟随你当前访问的域名。",
        "demo": "在线 Demo",
        "demo_desc": "支持直接合成和异步 SSE 两种模式。生成后可以直接试听，不必先下载。",
        "providers": "Provider 说明",
        "provider_edge_title": "Edge",
        "provider_edge_body": "返回真实 WordBoundary 词级时间戳，voice 列表完整，兼容 alloy / echo / nova 等别名。",
        "provider_kokoro_title": "Kokoro",
        "provider_kokoro_body": "当前部署已经内置 kokoro-fastapi sidecar，词级时间戳来自 /dev/captioned_speech，并支持 per-request normalization_options。",
        "links": "常用入口",
        "tips": "返回体说明",
        "tips_body": "最小返回体优先用 multipart bundle 或异步 job bundle。JSON + audio_base64 会因为 base64 编码产生额外体积。",
        "bundle_structure": "Bundle 结构",
        "bundle_structure_desc": "直接返回 bundle 和异步任务完成后的 bundle 都是 multipart/mixed。页面会先按 boundary 切段，再分别处理 metadata 和音频。",
        "bundle_header_label": "响应头",
        "bundle_parts_label": "Part 结构",
        "bundle_parse_label": "页面解析步骤",
        "bundle_header_code": 'content-type: multipart/mixed; boundary="storyboat-<id>"',
        "bundle_parts_code": '--<boundary>\nContent-Type: application/json; charset=utf-8\nContent-Disposition: attachment; name="metadata"; filename="metadata.json"\n\n{"format":"mp3", ...}\n\n--<boundary>\nContent-Type: audio/mpeg\nContent-Disposition: attachment; name="audio"; filename="audio.mp3"\n\n<binary audio bytes>\n--<boundary>--',
        "bundle_parse_code": "1. 从 content-type 提取 boundary\n2. 用 boundary 在 Uint8Array 上逐段扫描\n3. 找到 metadata.json part，按 UTF-8 解码后 JSON.parse\n4. 找到 audio.mp3 / audio.wav part，保留原始 bytes\n5. 用音频 bytes 创建 Blob，提供试听和下载",
        "field_provider": "Provider",
        "field_model": "Model",
        "field_voice": "Voice",
        "field_format": "格式",
        "field_speed": "语速",
        "field_text": "文本",
        "field_mode": "模式",
        "field_normalize": "Kokoro 文本归一化",
        "mode_bundle": "直接返回 bundle",
        "mode_job": "异步任务 + SSE",
        "button_run": "生成 / 试听",
        "button_download": "下载音频",
        "status_idle": "等待请求",
        "status_loading": "处理中",
        "status_done": "已完成",
        "status_failed": "失败",
        "audio_preview": "试听",
        "job_log": "任务日志",
        "metadata": "Metadata",
        "curl_catalog": "读取完整目录",
        "curl_bundle": "直接返回 multipart bundle",
        "curl_job_create": "创建异步任务",
        "curl_job_sse": "监听 SSE 事件",
        "curl_job_bundle": "下载完成后的 bundle",
        "voice_loading": "加载声音列表中...",
        "voice_failed": "加载声音列表失败",
        "default_text": "欢迎使用 StoryBoat TTS Gateway。这一版已经支持 multipart bundle 和 SSE 任务流。",
    },
    "en": {
        "html_lang": "en",
        "switch_label": "中文",
        "title": "StoryBoat TTS Gateway",
        "subtitle": "A unified speech gateway for Edge TTS and Kokoro",
        "summary": "It exposes real word-level timestamps, multipart audio bundles, and async synthesis jobs streamed over SSE.",
        "quickstart": "Quickstart",
        "quickstart_desc": "Examples automatically use the current hostname you opened.",
        "demo": "Live Demo",
        "demo_desc": "Supports both direct bundle responses and async SSE jobs. Generated audio can be previewed immediately.",
        "providers": "Providers",
        "provider_edge_title": "Edge",
        "provider_edge_body": "Returns real WordBoundary timestamps, exposes the full voice catalog, and accepts aliases like alloy / echo / nova.",
        "provider_kokoro_title": "Kokoro",
        "provider_kokoro_body": "This deployment already bundles a kokoro-fastapi sidecar. Word timings come from /dev/captioned_speech, and normalization_options can be overridden per request.",
        "links": "Useful Paths",
        "tips": "Payload Size",
        "tips_body": "Use multipart bundle or async job bundle when payload size matters. JSON + audio_base64 is larger because of base64 overhead.",
        "bundle_structure": "Bundle Layout",
        "bundle_structure_desc": "Both direct bundle responses and completed async job bundles use multipart/mixed. The page splits the payload by boundary, then handles metadata and audio separately.",
        "bundle_header_label": "Response Header",
        "bundle_parts_label": "Part Layout",
        "bundle_parse_label": "Browser Parse Flow",
        "bundle_header_code": 'content-type: multipart/mixed; boundary="storyboat-<id>"',
        "bundle_parts_code": '--<boundary>\nContent-Type: application/json; charset=utf-8\nContent-Disposition: attachment; name="metadata"; filename="metadata.json"\n\n{"format":"mp3", ...}\n\n--<boundary>\nContent-Type: audio/mpeg\nContent-Disposition: attachment; name="audio"; filename="audio.mp3"\n\n<binary audio bytes>\n--<boundary>--',
        "bundle_parse_code": "1. Read boundary from content-type\n2. Scan the Uint8Array part by part\n3. Decode metadata.json as UTF-8 and JSON.parse it\n4. Keep audio.mp3 / audio.wav as raw bytes\n5. Build a Blob from the audio bytes for preview and download",
        "field_provider": "Provider",
        "field_model": "Model",
        "field_voice": "Voice",
        "field_format": "Format",
        "field_speed": "Speed",
        "field_text": "Text",
        "field_mode": "Mode",
        "field_normalize": "Kokoro normalization",
        "mode_bundle": "Direct bundle",
        "mode_job": "Async job + SSE",
        "button_run": "Generate / Preview",
        "button_download": "Download Audio",
        "status_idle": "Idle",
        "status_loading": "Processing",
        "status_done": "Completed",
        "status_failed": "Failed",
        "audio_preview": "Preview",
        "job_log": "Job Log",
        "metadata": "Metadata",
        "curl_catalog": "Read the full API catalog",
        "curl_bundle": "Request a direct multipart bundle",
        "curl_job_create": "Create an async job",
        "curl_job_sse": "Listen for SSE events",
        "curl_job_bundle": "Download the final bundle",
        "voice_loading": "Loading voices...",
        "voice_failed": "Failed to load voices",
        "default_text": "Welcome to StoryBoat TTS Gateway. This build supports multipart bundles and SSE-based async jobs.",
    },
}


MODEL_OPTIONS = {
    "edge": ["tts-1", "tts-1-hd"],
    "kokoro": ["kokoro"],
}


def resolve_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    proto = forwarded_proto or request.url.scheme
    host = forwarded_host or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def render_page(base_url: str, lang: str) -> str:
    current_lang = "en" if lang == "en" else "zh"
    other_lang = "zh" if current_lang == "en" else "en"
    text = TRANSLATIONS[current_lang]
    bootstrap = {
        "baseUrl": base_url,
        "lang": current_lang,
        "text": text,
        "modelOptions": MODEL_OPTIONS,
    }

    replacements = {
        "__HTML_LANG__": text["html_lang"],
        "__LANG_URL__": f"/?lang={other_lang}",
        "__SWITCH_LABEL__": text["switch_label"],
        "__TITLE__": text["title"],
        "__SUBTITLE__": text["subtitle"],
        "__SUMMARY__": text["summary"],
        "__QUICKSTART__": text["quickstart"],
        "__QUICKSTART_DESC__": text["quickstart_desc"],
        "__DEMO__": text["demo"],
        "__DEMO_DESC__": text["demo_desc"],
        "__PROVIDERS__": text["providers"],
        "__PROVIDER_EDGE_TITLE__": text["provider_edge_title"],
        "__PROVIDER_EDGE_BODY__": text["provider_edge_body"],
        "__PROVIDER_KOKORO_TITLE__": text["provider_kokoro_title"],
        "__PROVIDER_KOKORO_BODY__": text["provider_kokoro_body"],
        "__LINKS__": text["links"],
        "__TIPS__": text["tips"],
        "__TIPS_BODY__": text["tips_body"],
        "__BUNDLE_STRUCTURE__": text["bundle_structure"],
        "__BUNDLE_STRUCTURE_DESC__": text["bundle_structure_desc"],
        "__BUNDLE_HEADER_LABEL__": text["bundle_header_label"],
        "__BUNDLE_PARTS_LABEL__": text["bundle_parts_label"],
        "__BUNDLE_PARSE_LABEL__": text["bundle_parse_label"],
        "__BUNDLE_HEADER_CODE__": text["bundle_header_code"],
        "__BUNDLE_PARTS_CODE__": text["bundle_parts_code"],
        "__BUNDLE_PARSE_CODE__": text["bundle_parse_code"],
        "__FIELD_PROVIDER__": text["field_provider"],
        "__FIELD_MODEL__": text["field_model"],
        "__FIELD_VOICE__": text["field_voice"],
        "__FIELD_FORMAT__": text["field_format"],
        "__FIELD_SPEED__": text["field_speed"],
        "__FIELD_TEXT__": text["field_text"],
        "__FIELD_MODE__": text["field_mode"],
        "__FIELD_NORMALIZE__": text["field_normalize"],
        "__MODE_BUNDLE__": text["mode_bundle"],
        "__MODE_JOB__": text["mode_job"],
        "__BUTTON_RUN__": text["button_run"],
        "__BUTTON_DOWNLOAD__": text["button_download"],
        "__STATUS_IDLE__": text["status_idle"],
        "__AUDIO_PREVIEW__": text["audio_preview"],
        "__JOB_LOG__": text["job_log"],
        "__METADATA__": text["metadata"],
        "__DEFAULT_TEXT__": text["default_text"],
        "__BOOTSTRAP_JSON__": json.dumps(bootstrap, ensure_ascii=False),
    }

    page = PAGE_TEMPLATE
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(request: Request, lang: str = "zh") -> HTMLResponse:
    return HTMLResponse(render_page(resolve_base_url(request), lang))
