from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from storayboat_tts_gateway.app import app as upstream_app


app = FastAPI(
    title=upstream_app.title,
    version=upstream_app.version,
    docs_url=upstream_app.docs_url,
    redoc_url=upstream_app.redoc_url,
    openapi_url=upstream_app.openapi_url,
)
app.include_router(upstream_app.router)


TRANSLATIONS = {
    "zh": {
        "html_lang": "zh-CN",
        "switch_label": "EN",
        "title": "StorayBoat TTS Gateway",
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
    },
    "en": {
        "html_lang": "en",
        "switch_label": "中文",
        "title": "StorayBoat TTS Gateway",
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
    },
}


MODEL_OPTIONS = {
    "edge": ["tts-1", "tts-1-hd"],
    "kokoro": ["kokoro"],
}


PAGE_TEMPLATE = """<!doctype html>
<html lang="__HTML_LANG__">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StorayBoat TTS Gateway</title>
  <style>
    :root {
      --bg: #05070b;
      --panel: rgba(12, 16, 24, 0.84);
      --panel-strong: rgba(9, 12, 18, 0.96);
      --line: rgba(103, 222, 255, 0.22);
      --line-strong: rgba(103, 222, 255, 0.42);
      --text: #edf6ff;
      --muted: #8da3b5;
      --accent: #67deff;
      --accent-2: #4fffb0;
      --danger: #ff6b81;
      --shadow: 0 24px 80px rgba(0, 0, 0, 0.42);
      --radius: 22px;
      --mono: "SFMono-Regular", "JetBrains Mono", "Menlo", monospace;
      --sans: "SF Pro Display", "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: var(--sans);
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(103, 222, 255, 0.16), transparent 30%),
        radial-gradient(circle at 80% 20%, rgba(79, 255, 176, 0.12), transparent 26%),
        linear-gradient(180deg, #05070b 0%, #080d14 42%, #04060a 100%);
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      background-image:
        linear-gradient(rgba(103, 222, 255, 0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(103, 222, 255, 0.05) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: linear-gradient(180deg, rgba(255,255,255,0.36), transparent 92%);
      pointer-events: none;
    }
    .shell {
      width: min(1200px, calc(100vw - 28px));
      margin: 0 auto;
      padding: 20px 0 56px;
      position: relative;
      z-index: 1;
    }
    .topbar {
      display: flex;
      justify-content: flex-end;
      margin-bottom: 18px;
    }
    .lang-switch {
      border: 1px solid var(--line);
      background: rgba(8, 12, 18, 0.72);
      color: var(--text);
      text-decoration: none;
      padding: 10px 14px;
      border-radius: 999px;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .hero, .grid-card, .demo, .quickstart, .links, .tips {
      backdrop-filter: blur(16px);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: var(--radius);
    }
    .hero {
      padding: 28px;
      overflow: hidden;
      position: relative;
    }
    .hero::after {
      content: "";
      position: absolute;
      inset: auto -5% -25% 45%;
      height: 320px;
      background: radial-gradient(circle, rgba(103, 222, 255, 0.18), transparent 68%);
      pointer-events: none;
    }
    h1 {
      margin: 0 0 10px;
      font-size: clamp(34px, 5vw, 62px);
      line-height: 0.94;
      letter-spacing: -0.04em;
    }
    .subtitle {
      color: var(--accent);
      font-size: 14px;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .summary {
      max-width: 760px;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.7;
      margin: 0;
    }
    .hero-links {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 22px;
    }
    .hero-links a {
      color: var(--text);
      text-decoration: none;
      padding: 12px 16px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.02);
      font-size: 14px;
    }
    .section-title {
      margin: 0 0 8px;
      font-size: 22px;
    }
    .section-desc {
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.65;
    }
    .content-grid {
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 18px;
      margin-top: 18px;
    }
    .stack {
      display: grid;
      gap: 18px;
    }
    .quickstart, .links, .tips, .demo {
      padding: 22px;
    }
    .providers-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .grid-card {
      padding: 18px;
      min-height: 180px;
      position: relative;
      overflow: hidden;
    }
    .grid-card::before {
      content: "";
      position: absolute;
      inset: 0 auto auto 0;
      width: 100%;
      height: 2px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }
    .card-kicker {
      color: var(--accent);
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .grid-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }
    pre {
      margin: 0;
      padding: 16px;
      border-radius: 16px;
      background: var(--panel-strong);
      border: 1px solid rgba(255,255,255,0.06);
      color: #d8f6ff;
      overflow-x: auto;
      font: 13px/1.7 var(--mono);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .quickstart-block + .quickstart-block { margin-top: 14px; }
    .quickstart-label {
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }
    .link-list {
      display: grid;
      gap: 10px;
    }
    .link-list a {
      color: var(--text);
      text-decoration: none;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.03);
      padding: 14px 16px;
      border-radius: 14px;
      font: 13px/1.5 var(--mono);
    }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }
    .field {
      display: grid;
      gap: 8px;
    }
    .field-full { grid-column: 1 / -1; }
    label {
      color: var(--muted);
      font-size: 13px;
    }
    input, select, textarea, button {
      width: 100%;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(3, 8, 14, 0.88);
      color: var(--text);
      padding: 13px 14px;
      font: inherit;
    }
    textarea {
      min-height: 118px;
      resize: vertical;
      line-height: 1.65;
    }
    button {
      cursor: pointer;
      background: linear-gradient(135deg, rgba(103,222,255,0.22), rgba(79,255,176,0.18));
      border-color: var(--line-strong);
      font-weight: 600;
    }
    .status-row {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 12px;
      margin: 18px 0 12px;
      font-size: 13px;
      color: var(--muted);
    }
    .status-pill {
      padding: 9px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(255,255,255,0.03);
    }
    .status-pill.error {
      color: #ffd7df;
      border-color: rgba(255,107,129,0.28);
      background: rgba(255,107,129,0.12);
    }
    .status-pill.ok {
      color: #d3fff0;
      border-color: rgba(79,255,176,0.28);
      background: rgba(79,255,176,0.12);
    }
    .audio-box, .meta-box, .log-box {
      margin-top: 14px;
      padding: 16px;
      border-radius: 16px;
      background: var(--panel-strong);
      border: 1px solid rgba(255,255,255,0.06);
    }
    audio {
      width: 100%;
      margin-top: 10px;
    }
    .download-link {
      display: inline-flex;
      margin-top: 12px;
      color: var(--text);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 10px 14px;
    }
    .hidden { display: none !important; }
    .log-box pre, .meta-box pre {
      background: transparent;
      border: 0;
      padding: 0;
    }
    @media (max-width: 920px) {
      .content-grid {
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 720px) {
      .shell {
        width: min(100vw - 16px, 100%);
        padding-top: 10px;
      }
      .hero, .quickstart, .links, .tips, .demo, .grid-card {
        padding: 18px;
      }
      .providers-grid, .form-grid {
        grid-template-columns: 1fr;
      }
      .hero-links a {
        width: 100%;
        justify-content: center;
        text-align: center;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <a class="lang-switch" href="__LANG_URL__">__SWITCH_LABEL__</a>
    </div>
    <section class="hero">
      <div class="subtitle">SSE / BUNDLE / TIMESTAMPS</div>
      <h1>__TITLE__</h1>
      <p class="summary">__SUMMARY__</p>
      <div class="hero-links">
        <a href="#demo">__DEMO__</a>
        <a href="#quickstart">__QUICKSTART__</a>
        <a href="/docs" target="_blank">/docs</a>
        <a href="/v1/catalog" target="_blank">/v1/catalog</a>
      </div>
    </section>

    <div class="content-grid">
      <div class="stack">
        <section class="quickstart" id="quickstart">
          <h2 class="section-title">__QUICKSTART__</h2>
          <p class="section-desc">__QUICKSTART_DESC__</p>
          <div id="quickstart-content"></div>
        </section>

        <section class="demo" id="demo">
          <h2 class="section-title">__DEMO__</h2>
          <p class="section-desc">__DEMO_DESC__</p>
          <form id="demo-form" class="form-grid">
            <div class="field">
              <label for="provider">__FIELD_PROVIDER__</label>
              <select id="provider" name="provider">
                <option value="edge">edge</option>
                <option value="kokoro">kokoro</option>
              </select>
            </div>
            <div class="field">
              <label for="mode">__FIELD_MODE__</label>
              <select id="mode" name="mode">
                <option value="bundle">__MODE_BUNDLE__</option>
                <option value="job">__MODE_JOB__</option>
              </select>
            </div>
            <div class="field">
              <label for="model">__FIELD_MODEL__</label>
              <select id="model" name="model"></select>
            </div>
            <div class="field">
              <label for="voice">__FIELD_VOICE__</label>
              <select id="voice" name="voice"></select>
            </div>
            <div class="field">
              <label for="format">__FIELD_FORMAT__</label>
              <select id="format" name="format">
                <option value="mp3">mp3</option>
                <option value="wav">wav</option>
              </select>
            </div>
            <div class="field">
              <label for="speed">__FIELD_SPEED__</label>
              <input id="speed" name="speed" type="number" min="0.25" max="4" step="0.05" value="1">
            </div>
            <div class="field field-full hidden" id="normalize-field">
              <label>
                <input id="normalize" name="normalize" type="checkbox">
                __FIELD_NORMALIZE__
              </label>
            </div>
            <div class="field field-full">
              <label for="text">__FIELD_TEXT__</label>
              <textarea id="text" name="text">欢迎使用 StorayBoat TTS Gateway。这一版已经支持 multipart bundle 和 SSE 任务流。</textarea>
            </div>
            <div class="field field-full">
              <button type="submit">__BUTTON_RUN__</button>
            </div>
          </form>

          <div class="status-row">
            <div class="status-pill" id="status-pill">__STATUS_IDLE__</div>
            <div class="status-pill" id="job-pill">__JOB_LOG__</div>
          </div>

          <div class="audio-box hidden" id="audio-box">
            <strong>__AUDIO_PREVIEW__</strong>
            <audio id="audio-player" controls></audio>
            <a id="download-link" class="download-link hidden" download="tts-audio.mp3">__BUTTON_DOWNLOAD__</a>
          </div>

          <div class="meta-box hidden" id="meta-box">
            <strong>__METADATA__</strong>
            <pre id="meta-output"></pre>
          </div>

          <div class="log-box">
            <strong>__JOB_LOG__</strong>
            <pre id="log-output">__STATUS_IDLE__</pre>
          </div>
        </section>
      </div>

      <div class="stack">
        <section class="quickstart">
          <h2 class="section-title">__PROVIDERS__</h2>
          <div class="providers-grid">
            <article class="grid-card">
              <div class="card-kicker">__PROVIDER_EDGE_TITLE__</div>
              <p>__PROVIDER_EDGE_BODY__</p>
            </article>
            <article class="grid-card">
              <div class="card-kicker">__PROVIDER_KOKORO_TITLE__</div>
              <p>__PROVIDER_KOKORO_BODY__</p>
            </article>
          </div>
        </section>

        <section class="links">
          <h2 class="section-title">__LINKS__</h2>
          <div class="link-list">
            <a href="/healthz" target="_blank">/healthz</a>
            <a href="/v1/providers" target="_blank">/v1/providers</a>
            <a href="/v1/voices?provider=edge" target="_blank">/v1/voices?provider=edge</a>
            <a href="/v1/voices?provider=kokoro" target="_blank">/v1/voices?provider=kokoro</a>
            <a href="/v1/catalog" target="_blank">/v1/catalog</a>
            <a href="/docs" target="_blank">/docs</a>
          </div>
        </section>

        <section class="tips">
          <h2 class="section-title">__TIPS__</h2>
          <p class="section-desc">__TIPS_BODY__</p>
        </section>
      </div>
    </div>
  </div>
  <script>
    window.__BOOTSTRAP__ = __BOOTSTRAP_JSON__;
  </script>
  <script>
    const boot = window.__BOOTSTRAP__;
    const text = boot.text;
    const modelOptions = boot.modelOptions;
    const voiceCache = {};
    let currentAudioUrl = null;
    let currentEventSource = null;

    const providerEl = document.getElementById("provider");
    const modeEl = document.getElementById("mode");
    const modelEl = document.getElementById("model");
    const voiceEl = document.getElementById("voice");
    const formatEl = document.getElementById("format");
    const speedEl = document.getElementById("speed");
    const textEl = document.getElementById("text");
    const normalizeEl = document.getElementById("normalize");
    const normalizeFieldEl = document.getElementById("normalize-field");
    const statusEl = document.getElementById("status-pill");
    const jobEl = document.getElementById("job-pill");
    const audioBoxEl = document.getElementById("audio-box");
    const audioPlayerEl = document.getElementById("audio-player");
    const downloadLinkEl = document.getElementById("download-link");
    const metaBoxEl = document.getElementById("meta-box");
    const metaOutputEl = document.getElementById("meta-output");
    const logOutputEl = document.getElementById("log-output");
    const quickstartEl = document.getElementById("quickstart-content");

    function setStatus(label, kind) {
      statusEl.textContent = label;
      statusEl.className = "status-pill" + (kind ? " " + kind : "");
    }

    function setJob(label, kind) {
      jobEl.textContent = label;
      jobEl.className = "status-pill" + (kind ? " " + kind : "");
    }

    function resetAudio() {
      if (currentAudioUrl) {
        URL.revokeObjectURL(currentAudioUrl);
        currentAudioUrl = null;
      }
      audioPlayerEl.removeAttribute("src");
      audioPlayerEl.load();
      downloadLinkEl.classList.add("hidden");
      audioBoxEl.classList.add("hidden");
      metaBoxEl.classList.add("hidden");
    }

    function appendLog(line) {
      const current = logOutputEl.textContent.trim();
      logOutputEl.textContent = current ? current + "\\n" + line : line;
    }

    function setLog(lines) {
      logOutputEl.textContent = Array.isArray(lines) ? lines.join("\\n") : String(lines);
    }

    function resolveBaseUrl() {
      return boot.baseUrl.replace(/\\/$/, "");
    }

    function buildCurlSamples() {
      const baseUrl = resolveBaseUrl();
      const samples = [
        {
          label: text.curl_catalog,
          content: `curl ${baseUrl}/v1/catalog`
        },
        {
          label: text.curl_bundle,
          content: `curl -X POST ${baseUrl}/v1/audio/speech_bundle \\\\\n+  -H 'Content-Type: application/json' \\\\\n+  -d '{\\n+    "provider": "edge",\\n+    "model": "tts-1",\\n+    "input": "Hello from StorayBoat.",\\n+    "voice": "alloy",\\n+    "response_format": "mp3",\\n+    "speed": 1.0\\n+  }'`
        },
        {
          label: text.curl_job_create,
          content: `curl -X POST ${baseUrl}/v1/audio/jobs \\\\\n+  -H 'Content-Type: application/json' \\\\\n+  -d '{\\n+    "provider": "kokoro",\\n+    "model": "kokoro",\\n+    "input": "SSE async jobs are now available.",\\n+    "voice": "af_sarah",\\n+    "response_format": "mp3",\\n+    "speed": 1.0,\\n+    "normalization_options": {"normalize": false}\\n+  }'`
        },
        {
          label: text.curl_job_sse,
          content: `curl -N ${baseUrl}/v1/audio/jobs/<job_id>/events`
        },
        {
          label: text.curl_job_bundle,
          content: `curl -L ${baseUrl}/v1/audio/jobs/<job_id>/bundle -o result.multipart`
        }
      ];
      quickstartEl.innerHTML = samples.map((item) => (
        `<div class="quickstart-block"><div class="quickstart-label">${escapeHtml(item.label)}</div><pre>${escapeHtml(item.content)}</pre></div>`
      )).join("");
    }

    function escapeHtml(value) {
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function updateModelOptions() {
      const provider = providerEl.value;
      const options = modelOptions[provider] || [];
      modelEl.innerHTML = options.map((item) => `<option value="${item}">${item}</option>`).join("");
      normalizeFieldEl.classList.toggle("hidden", provider !== "kokoro");
    }

    async function loadVoiceOptions() {
      const provider = providerEl.value;
      voiceEl.innerHTML = `<option value="">${text.voice_loading}</option>`;
      try {
        if (!voiceCache[provider]) {
          const response = await fetch(`/v1/voices?provider=${encodeURIComponent(provider)}`);
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          voiceCache[provider] = await response.json();
        }
        const voices = voiceCache[provider];
        voiceEl.innerHTML = voices.map((voice) => {
          const label = [voice.id, voice.locale].filter(Boolean).join(" · ");
          return `<option value="${escapeHtml(voice.id)}">${escapeHtml(label)}</option>`;
        }).join("");
        if (!voices.length) {
          voiceEl.innerHTML = `<option value="">(empty)</option>`;
        }
      } catch (error) {
        voiceEl.innerHTML = `<option value="">${text.voice_failed}</option>`;
      }
    }

    function buildPayload() {
      const provider = providerEl.value;
      const payload = {
        provider,
        model: modelEl.value,
        input: textEl.value,
        voice: voiceEl.value || null,
        response_format: formatEl.value,
        speed: Number(speedEl.value || "1")
      };
      if (provider === "kokoro") {
        payload.normalization_options = { normalize: Boolean(normalizeEl.checked) };
      }
      return payload;
    }

    function parseMultipart(buffer, contentType) {
      const boundaryMatch = /boundary="?([^=";]+)"?/i.exec(contentType || "");
      if (!boundaryMatch) {
        throw new Error("missing multipart boundary");
      }
      const boundary = `--${boundaryMatch[1]}`;
      const textPayload = new TextDecoder("latin1").decode(buffer);
      const parts = textPayload.split(boundary).slice(1, -1);
      const parsed = {};

      for (const rawPart of parts) {
        const trimmed = rawPart.replace(/^\\r\\n/, "");
        const headerEnd = trimmed.indexOf("\\r\\n\\r\\n");
        if (headerEnd === -1) {
          continue;
        }
        const headerText = trimmed.slice(0, headerEnd);
        const bodyText = trimmed.slice(headerEnd + 4).replace(/\\r\\n$/, "");
        const headers = {};
        headerText.split("\\r\\n").forEach((line) => {
          const idx = line.indexOf(":");
          if (idx !== -1) {
            headers[line.slice(0, idx).trim().toLowerCase()] = line.slice(idx + 1).trim();
          }
        });
        const disposition = headers["content-disposition"] || "";
        const nameMatch = /name="([^"]+)"/.exec(disposition);
        const filenameMatch = /filename="([^"]+)"/.exec(disposition);
        const key = (nameMatch && nameMatch[1]) || (filenameMatch && filenameMatch[1]) || "part";
        const bytes = Uint8Array.from(bodyText, (char) => char.charCodeAt(0));
        parsed[key] = {
          filename: filenameMatch ? filenameMatch[1] : key,
          contentType: headers["content-type"] || "application/octet-stream",
          bytes
        };
      }
      return parsed;
    }

    function presentBundle(parts) {
      const metadataPart = parts.metadata || parts["metadata.json"];
      const audioPart = parts.audio || Object.values(parts).find((item) => item.contentType.startsWith("audio/"));
      if (!metadataPart || !audioPart) {
        throw new Error("bundle missing metadata or audio part");
      }
      const metadataText = new TextDecoder("utf-8").decode(metadataPart.bytes);
      const metadata = JSON.parse(metadataText);
      const blob = new Blob([audioPart.bytes], { type: audioPart.contentType });
      currentAudioUrl = URL.createObjectURL(blob);
      audioPlayerEl.src = currentAudioUrl;
      audioBoxEl.classList.remove("hidden");
      metaBoxEl.classList.remove("hidden");
      downloadLinkEl.classList.remove("hidden");
      downloadLinkEl.href = currentAudioUrl;
      downloadLinkEl.download = audioPart.filename || `tts-audio.${metadata.format || "mp3"}`;
      metaOutputEl.textContent = JSON.stringify(metadata, null, 2);
      setStatus(text.status_done, "ok");
      setJob(text.status_done, "ok");
      audioPlayerEl.play().catch(() => {});
    }

    async function fetchAndPresentBundle(url) {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const buffer = await response.arrayBuffer();
      const parts = parseMultipart(buffer, response.headers.get("content-type") || "");
      presentBundle(parts);
    }

    async function runBundle(payload) {
      const response = await fetch("/v1/audio/speech_bundle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const buffer = await response.arrayBuffer();
      const parts = parseMultipart(buffer, response.headers.get("content-type") || "");
      presentBundle(parts);
      appendLog("bundle: completed");
    }

    async function runJob(payload) {
      const createResponse = await fetch("/v1/audio/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!createResponse.ok) {
        throw new Error(await createResponse.text());
      }
      const created = await createResponse.json();
      const jobId = created.id;
      setJob(`${jobId}`, "");
      appendLog(`job created: ${jobId}`);

      if (currentEventSource) {
        currentEventSource.close();
      }
      await new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/v1/audio/jobs/${encodeURIComponent(jobId)}/events`);
        currentEventSource = eventSource;
        const finish = async (downloadUrl) => {
          eventSource.close();
          currentEventSource = null;
          try {
            await fetchAndPresentBundle(downloadUrl);
            appendLog(`bundle ready: ${downloadUrl}`);
            resolve();
          } catch (error) {
            reject(error);
          }
        };

        ["snapshot", "started", "synth_progress", "packaging", "bundle_ready", "completed", "failed"].forEach((eventName) => {
          eventSource.addEventListener(eventName, (event) => {
            const payload = JSON.parse(event.data);
            appendLog(`${eventName}: ${JSON.stringify(payload)}`);
            if (eventName === "failed") {
              setStatus(text.status_failed, "error");
              setJob(text.status_failed, "error");
              eventSource.close();
              currentEventSource = null;
              reject(new Error(payload.error || "job failed"));
              return;
            }
            if (eventName === "completed" && payload.download_url) {
              void finish(payload.download_url);
            }
          });
        });

        eventSource.onerror = () => {
          appendLog("sse: connection error");
        };
      });
    }

    async function handleSubmit(event) {
      event.preventDefault();
      resetAudio();
      setLog(text.status_loading);
      setStatus(text.status_loading, "");
      setJob(text.status_loading, "");
      const payload = buildPayload();
      try {
        if (modeEl.value === "job") {
          await runJob(payload);
        } else {
          await runBundle(payload);
        }
      } catch (error) {
        setStatus(text.status_failed, "error");
        setJob(text.status_failed, "error");
        appendLog(String(error));
      }
    }

    providerEl.addEventListener("change", async () => {
      updateModelOptions();
      await loadVoiceOptions();
    });

    document.getElementById("demo-form").addEventListener("submit", handleSubmit);

    buildCurlSamples();
    updateModelOptions();
    loadVoiceOptions();
  </script>
</body>
</html>
"""


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
    lang_url = f"/?lang={other_lang}"
    bootstrap = {
        "baseUrl": base_url,
        "lang": current_lang,
        "text": text,
        "modelOptions": MODEL_OPTIONS,
    }

    page = PAGE_TEMPLATE
    replacements = {
        "__HTML_LANG__": text["html_lang"],
        "__LANG_URL__": lang_url,
        "__SWITCH_LABEL__": text["switch_label"],
        "__TITLE__": text["title"],
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
        "__BOOTSTRAP_JSON__": json.dumps(bootstrap, ensure_ascii=False),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(request: Request, lang: str = "zh") -> HTMLResponse:
    return HTMLResponse(render_page(resolve_base_url(request), lang))
