import os
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"patch failed: could not find snippet for {label}")
    return text.replace(old, new, 1)


def patch_main_js(root: Path) -> None:
    path = root / "static/js/main.js"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """        } else {\n            appendVoiceOptions(select);\n        }\n        restoreSelectValue(select, previousValue);\n""",
        """        } else {\n            appendVoiceOptions(select);\n        }\n        if (isKitten && !previousValue) {\n            const fallbackVoice = runtimeSettings?.kitten_tts_default_voice || 'Jasper';\n            if (Array.from(select.options).some(option => option.value === fallbackVoice)) {\n                select.value = fallbackVoice;\n            }\n        }\n        restoreSelectValue(select, previousValue);\n""",
        "main.js kitten select default",
    )

    text = replace_once(
        text,
        """    const turboSelections = (turboEnabled || qwenCloneEnabled) ? buildTurboSelectionMap() : {};\n    const globalReference = (turboEnabled || qwenCloneEnabled) ? getGlobalReferenceSelection() : '';\n""",
        """    const turboSelections = (turboEnabled || qwenCloneEnabled) ? buildTurboSelectionMap() : {};\n    const kittenEnabled = isKittenEngine(engineName);\n    const kittenDefault = kittenEnabled\n        ? runtimeSettings?.kitten_tts_default_voice?.trim() || 'Jasper'\n        : '';\n    const globalReference = (turboEnabled || qwenCloneEnabled) ? getGlobalReferenceSelection() : '';\n""",
        "main.js kitten assignment prelude",
    )

    text = replace_once(
        text,
        """        if (voiceName && window.availableVoices) {\n            const langCode = getLangCodeForVoice(voiceName);\n            assignments[speaker] = createAssignment(voiceName, langCode, speaker);\n        }\n""",
        """        if (voiceName && window.availableVoices) {\n            const langCode = getLangCodeForVoice(voiceName);\n            assignments[speaker] = createAssignment(voiceName, langCode, speaker);\n            return;\n        }\n\n        if (kittenEnabled) {\n            const kittenVoice = voiceName || kittenDefault;\n            if (kittenVoice) {\n                assignments[speaker] = createPresetAssignment(kittenVoice, speaker);\n            }\n        }\n""",
        "main.js kitten assignment fallback",
    )

    text = replace_once(
        text,
        """    if (pocketPresetEnabled && !Object.keys(assignments).length) {\n        const fallbackVoice = pocketPresetDefault;\n        if (fallbackVoice) {\n            assignments.default = createPresetAssignment(fallbackVoice, 'default');\n        }\n    }\n\n    if (turboEnabled || qwenCloneEnabled) {\n""",
        """    if (pocketPresetEnabled && !Object.keys(assignments).length) {\n        const fallbackVoice = pocketPresetDefault;\n        if (fallbackVoice) {\n            assignments.default = createPresetAssignment(fallbackVoice, 'default');\n        }\n    }\n    if (kittenEnabled && !Object.keys(assignments).length) {\n        const fallbackVoice = kittenDefault;\n        if (fallbackVoice) {\n            const targets = (currentStats?.speakers && currentStats.speakers.length)\n                ? currentStats.speakers\n                : ['default'];\n            targets.forEach(speakerKey => assignments[speakerKey] = createPresetAssignment(fallbackVoice, speakerKey));\n        }\n    }\n\n    if (turboEnabled || qwenCloneEnabled) {\n""",
        "main.js kitten assignment global fallback",
    )

    text = replace_once(
        text,
        'placeholder="Not available yet."',
        'placeholder="Describe the voice, e.g. warm narrator or deep male voice."',
        "main.js voice type placeholder",
    )

    path.write_text(text, encoding="utf-8")


def patch_app_py(root: Path) -> None:
    path = root / "app.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """            with queue_lock:\n                current_job_id = job_id\n                jobs[job_id]['status'] = 'processing'\n                jobs[job_id]['started_at'] = datetime.now().isoformat()\n            _persist_job_state(job_id)\n""",
        """            with queue_lock:\n                current_job_id = job_id\n                jobs[job_id]['status'] = 'processing'\n                jobs[job_id]['started_at'] = datetime.now().isoformat()\n                jobs[job_id]['status_message'] = 'Preparing job and loading models…'\n                jobs[job_id]['last_update'] = datetime.now().isoformat()\n            _persist_job_state(job_id)\n""",
        "app.py worker processing status",
    )

    text = replace_once(
        text,
        """        with queue_lock:\n            jobs[job_id] = {\n                "status": "queued",\n                "text_preview": text[:200],\n                "text_path": text_path,\n                "text_length": text_length,\n                "created_at": datetime.now().isoformat(),\n""",
        """        with queue_lock:\n            jobs[job_id] = {\n                "status": "queued",\n                "status_message": "Queued and waiting for worker…",\n                "text_preview": text[:200],\n                "text_path": text_path,\n                "text_length": text_length,\n                "created_at": datetime.now().isoformat(),\n                "last_update": datetime.now().isoformat(),\n""",
        "app.py queued status metadata",
    )

    text = replace_once(
        text,
        """        _persist_job_state(job_id)\n\n        def update_progress(increment: int = 1):\n""",
        """        _persist_job_state(job_id)\n\n        def set_status_message(message: str):\n            with queue_lock:\n                job_entry = jobs.get(job_id)\n                if job_entry:\n                    job_entry['status_message'] = message\n                    job_entry['last_update'] = datetime.now().isoformat()\n            _persist_job_state(job_id)\n\n        set_status_message('Preparing text and generation plan…')\n\n        def update_progress(increment: int = 1):\n""",
        "app.py status message helper",
    )

    text = replace_once(
        text,
        """            with queue_lock:\n                job_entry = jobs.get(job_id)\n                if job_entry:\n                    job_entry['processed_chunks'] = processed_chunks\n                    job_entry['total_chunks'] = total_chunks\n                    job_entry['progress'] = percent if job_entry.get('status') != 'completed' else 100\n                    job_entry['eta_seconds'] = eta_seconds\n                    job_entry['last_update'] = datetime.now().isoformat()\n                    if increment > 0:\n""",
        """            with queue_lock:\n                job_entry = jobs.get(job_id)\n                if job_entry:\n                    job_entry['processed_chunks'] = processed_chunks\n                    job_entry['total_chunks'] = total_chunks\n                    job_entry['progress'] = percent if job_entry.get('status') != 'completed' else 100\n                    job_entry['eta_seconds'] = eta_seconds\n                    job_entry['last_update'] = datetime.now().isoformat()\n                    job_entry['status_message'] = f'Generating audio chunks… ({processed_chunks}/{total_chunks})'\n                    if increment > 0:\n""",
        "app.py live progress status message",
    )

    text = replace_once(
        text,
        """        # Prepare TTS engine\n        engine_name = _normalize_engine_name(config.get("tts_engine"))\n        logger.info("Job %s: Creating TTS engine '%s'", job_id, engine_name)\n        job_log.info("Initializing TTS engine: %s", engine_name)\n        engine = get_tts_engine(engine_name, config=config)\n        _dev = getattr(engine, 'device', 'unknown')\n""",
        """        # Prepare TTS engine\n        engine_name = _normalize_engine_name(config.get("tts_engine"))\n        logger.info("Job %s: Creating TTS engine '%s'", job_id, engine_name)\n        job_log.info("Initializing TTS engine: %s", engine_name)\n        set_status_message(f"Loading {engine_name} engine and any required models…")\n        engine = get_tts_engine(engine_name, config=config)\n        _dev = getattr(engine, 'device', 'unknown')\n        set_status_message('Generating audio chunks…')\n""",
        "app.py engine loading status",
    )

    text = replace_once(
        text,
        """        with queue_lock:\n            jobs[job_id]['status'] = 'completed'\n            jobs[job_id]['progress'] = 100\n            jobs[job_id]['processed_chunks'] = total_chunks\n            jobs[job_id]['total_chunks'] = total_chunks\n            jobs[job_id]['eta_seconds'] = 0\n            jobs[job_id]['post_process_percent'] = 100\n            jobs[job_id]['post_process_active'] = False\n""",
        """        with queue_lock:\n            jobs[job_id]['status'] = 'completed'\n            jobs[job_id]['status_message'] = 'Completed'\n            jobs[job_id]['progress'] = 100\n            jobs[job_id]['processed_chunks'] = total_chunks\n            jobs[job_id]['total_chunks'] = total_chunks\n            jobs[job_id]['eta_seconds'] = 0\n            jobs[job_id]['last_update'] = datetime.now().isoformat()\n            jobs[job_id]['post_process_percent'] = 100\n            jobs[job_id]['post_process_active'] = False\n""",
        "app.py completed status message",
    )

    text = replace_once(
        text,
        """            payload = {\n                "job_id": job_id,\n                "status": job_entry.get("status"),\n                "created_at": job_entry.get("created_at"),\n                "started_at": job_entry.get("started_at"),\n                "completed_at": job_entry.get("completed_at"),\n                "engine": job_entry.get("engine"),\n""",
        """            payload = {\n                "job_id": job_id,\n                "status": job_entry.get("status"),\n                "status_message": job_entry.get("status_message"),\n                "created_at": job_entry.get("created_at"),\n                "started_at": job_entry.get("started_at"),\n                "completed_at": job_entry.get("completed_at"),\n                "last_update": job_entry.get("last_update"),\n                "engine": job_entry.get("engine"),\n""",
        "app.py details payload status metadata",
    )

    text = replace_once(
        text,
        """                    all_jobs.append({\n                        "job_id": job_id,\n                        "status": job_info.get("status", "unknown"),\n                        "progress": job_info.get("progress", 0),\n                        "created_at": job_info.get("created_at", ""),\n""",
        """                    all_jobs.append({\n                        "job_id": job_id,\n                        "status": job_info.get("status", "unknown"),\n                        "status_message": job_info.get("status_message", ""),\n                        "progress": job_info.get("progress", 0),\n                        "created_at": job_info.get("created_at", ""),\n                        "started_at": job_info.get("started_at", ""),\n                        "last_update": job_info.get("last_update", ""),\n                        "engine": job_info.get("engine", ""),\n""",
        "app.py queue payload status metadata",
    )

    path.write_text(text, encoding="utf-8")


def patch_kitten_engine(root: Path) -> None:
    path = root / "src/engines/kitten_tts_engine.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import logging\nfrom pathlib import Path\n",
        "import logging\nimport os\nimport re\nimport unicodedata\nfrom pathlib import Path\n",
        "kitten_tts_engine imports",
    )

    text = replace_once(
        text,
        """        self.model_id = model_id\n        self.default_voice = default_voice if default_voice in KITTEN_TTS_BUILTIN_VOICES else "Jasper"\n        self.post_processor = AudioPostProcessor()\n\n        logger.info("Loading KittenTTS model: %s", model_id)\n        self._model = _KittenTTS(model_id)\n        logger.info("KittenTTS model loaded (default voice: %s)", self.default_voice)\n""",
        """        self.model_id = model_id\n        self.default_voice = default_voice if default_voice in KITTEN_TTS_BUILTIN_VOICES else "Jasper"\n        self.post_processor = AudioPostProcessor()\n        self.cache_dir = os.environ.get("KITTEN_TTS_CACHE_DIR") or str(\n            Path(__file__).resolve().parents[2] / ".cache" / "kittentts"\n        )\n\n        logger.info("Loading KittenTTS model: %s (cache_dir=%s)", model_id, self.cache_dir)\n        self._model = _KittenTTS(model_id, cache_dir=self.cache_dir)\n        logger.info("KittenTTS model loaded (default voice: %s)", self.default_voice)\n""",
        "kitten_tts_engine cache dir",
    )

    text = replace_once(
        text,
        """    def _synthesize(\n        self,\n        text: str,\n        voice: str,\n        fx_settings: Optional[VoiceFXSettings] = None,\n    ) -> np.ndarray:\n        audio = self._model.generate(text, voice=voice)\n        if not isinstance(audio, np.ndarray):\n            audio = np.array(audio, dtype=np.float32)\n        audio = audio.astype(np.float32, copy=False)\n        return self.post_processor.apply_post_pipeline(audio, self.sample_rate, fx_settings)\n""",
        """    def _synthesize(\n        self,\n        text: str,\n        voice: str,\n        fx_settings: Optional[VoiceFXSettings] = None,\n    ) -> np.ndarray:\n        prepared_text = self._prepare_text(text)\n        audio = self._safe_generate(prepared_text, voice)\n        if not isinstance(audio, np.ndarray):\n            audio = np.array(audio, dtype=np.float32)\n        audio = audio.astype(np.float32, copy=False)\n        return self.post_processor.apply_post_pipeline(audio, self.sample_rate, fx_settings)\n\n    def _prepare_text(self, text: str) -> str:\n        normalized = unicodedata.normalize(\"NFKC\", text or \"\")\n        normalized = normalized.replace(\"\\u00a0\", \" \").replace(\"…\", \"...\")\n        normalized = normalized.replace(\"—\", \"-\").replace(\"–\", \"-\")\n        normalized = normalized.replace(\"“\", '\"').replace(\"”\", '\"')\n        normalized = normalized.replace(\"’\", \"'\").replace(\"`\", \"'\")\n        normalized = \"\".join(ch for ch in normalized if ch.isprintable() or ch in \"\\n\\t\")\n        normalized = re.sub(r\"\\s+\", \" \", normalized)\n        return normalized.strip()\n\n    def _safe_generate(self, text: str, voice: str) -> np.ndarray:\n        if not text:\n            return np.zeros(1, dtype=np.float32)\n\n        chunks = self._split_for_safe_generation(text, max_chars=90)\n        if len(chunks) > 1:\n            rendered_parts = [self._generate_single_chunk(chunk, voice) for chunk in chunks if chunk]\n            return np.concatenate(rendered_parts, axis=-1) if rendered_parts else np.zeros(1, dtype=np.float32)\n\n        return self._generate_single_chunk(text, voice)\n\n    def _generate_single_chunk(self, text: str, voice: str) -> np.ndarray:\n        if not text:\n            return np.zeros(1, dtype=np.float32)\n\n        last_exc: Optional[Exception] = None\n        try:\n            return self._model.generate(text, voice=voice)\n        except Exception as exc:\n            last_exc = exc\n            if not self._is_retryable_generation_error(exc):\n                raise\n            logger.warning(\"KittenTTS retrying with smaller chunks after model error: %s\", exc)\n\n        subchunks = self._split_for_safe_generation(text, max_chars=max(24, min(60, len(text) // 2 or 24)))\n        if len(subchunks) <= 1:\n            if last_exc is not None:\n                raise last_exc\n            raise RuntimeError(\"KittenTTS failed to generate audio\")\n\n        rendered_parts = [self._generate_single_chunk(subchunk, voice) for subchunk in subchunks if subchunk]\n        return np.concatenate(rendered_parts, axis=-1) if rendered_parts else np.zeros(1, dtype=np.float32)\n\n    def _is_retryable_generation_error(self, exc: Exception) -> bool:\n        message = str(exc).lower()\n        return \"invalid expand shape\" in message or \"onnxruntimeerror\" in message\n\n    def _split_for_safe_generation(self, text: str, max_chars: int = 90) -> List[str]:\n        text = (text or \"\").strip()\n        if not text:\n            return []\n        if len(text) <= max_chars:\n            return [text]\n\n        pieces = [piece.strip() for piece in re.split(r\"(?<=[.!?;:])\\s+\", text) if piece.strip()]\n        if len(pieces) <= 1:\n            pieces = [piece.strip() for piece in re.split(r\"(?<=[,])\\s+\", text) if piece.strip()]\n        if len(pieces) <= 1:\n            return self._split_by_words(text, max_chars=max_chars)\n\n        merged: List[str] = []\n        current = \"\"\n        for piece in pieces:\n            if len(piece) > max_chars:\n                if current:\n                    merged.append(current)\n                    current = \"\"\n                merged.extend(self._split_by_words(piece, max_chars=max_chars))\n                continue\n            candidate = piece if not current else f\"{current} {piece}\".strip()\n            if len(candidate) <= max_chars:\n                current = candidate\n            else:\n                merged.append(current)\n                current = piece\n        if current:\n            merged.append(current)\n        return [chunk for chunk in merged if chunk]\n\n    def _split_by_words(self, text: str, max_chars: int = 90) -> List[str]:\n        words = text.split()\n        if len(words) <= 1:\n            return self._split_by_chars(text, max_chars=max_chars)\n\n        chunks: List[str] = []\n        current_words: List[str] = []\n        current_len = 0\n        for word in words:\n            if len(word) > max_chars:\n                if current_words:\n                    chunks.append(\" \".join(current_words).strip())\n                    current_words = []\n                    current_len = 0\n                chunks.extend(self._split_by_chars(word, max_chars=max_chars))\n                continue\n            next_len = current_len + len(word) + (1 if current_words else 0)\n            if current_words and next_len > max_chars:\n                chunks.append(\" \".join(current_words).strip())\n                current_words = [word]\n                current_len = len(word)\n            else:\n                current_words.append(word)\n                current_len = next_len\n        if current_words:\n            chunks.append(\" \".join(current_words).strip())\n        return [chunk for chunk in chunks if chunk]\n\n    def _split_by_chars(self, text: str, max_chars: int = 90) -> List[str]:\n        text = text.strip()\n        if not text:\n            return []\n        return [text[i:i + max_chars].strip() for i in range(0, len(text), max_chars) if text[i:i + max_chars].strip()]\n""",
        "kitten_tts_engine safe synthesis",
    )

    path.write_text(text, encoding="utf-8")


def patch_queue_js(root: Path) -> None:
    path = root / "static/js/queue.js"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        """function renderJobProgress(job) {\n    const total = job.total_chunks || 0;\n    const processed = Math.min(job.processed_chunks || 0, total || Infinity);\n    const percent = total > 0 ? Math.round((processed / total) * 100) : (job.status === 'completed' ? 100 : 0);\n    const chunkLabel = total ? `${processed} / ${total} chunk${total === 1 ? '' : 's'}` : 'Estimating…';\n    const etaLabel = formatEta(job.eta_seconds, job.status);\n    const chapterLabel = job.chapter_mode\n        ? `${job.chapter_count || '?'} chapter${(job.chapter_count || 0) === 1 ? '' : 's'} (per chapter merge)`\n        : 'Single output file';\n    const postTotal = Number(job.post_process_total || 0);\n    const postDone = Math.min(Number(job.post_process_done || 0), postTotal || Infinity);\n    const postPercent = Number.isFinite(Number(job.post_process_percent))\n        ? Math.max(0, Math.min(Math.round(Number(job.post_process_percent)), 100))\n        : (postTotal > 0 ? Math.round((postDone / postTotal) * 100) : 0);\n    const isFinishing = job.status === 'processing'\n        && total > 0\n        && processed >= total\n        && (job.eta_seconds === 0 || job.eta_seconds === null || typeof job.eta_seconds !== 'number');\n    const showPost = (postTotal > 0 && (job.post_process_active || postDone > 0)) || isFinishing;\n    const postLabel = postTotal > 0\n        ? `Post-processing ${postDone} / ${postTotal}`\n        : 'Post-processing…';\n    const postFillClass = postTotal > 0 ? 'progress-bar-fill' : 'progress-bar-fill indeterminate';\n    const interruptedChip = job.status === 'interrupted'\n        ? '<span class=\"review-chip warning\">Interrupted</span>'\n        : '';\n    const resumeHint = job.status === 'interrupted' && Number.isFinite(Number(job.resume_from_chunk_index))\n        ? `<span class=\"review-chip muted\">Resume from chunk ${Number(job.resume_from_chunk_index) + 1}</span>`\n        : '';\n\n    return `\n        <div class=\"queue-progress\">\n            <div class=\"queue-progress-header\">\n                <span>${chunkLabel}</span>\n                <span>${etaLabel}</span>\n            </div>\n            <div class=\"progress-bar\">\n                <div class=\"progress-bar-fill\" style=\"width: ${Math.min(Math.max(percent, 0), 100)}%;\"></div>\n            </div>\n            <div class=\"queue-progress-footer\">\n                <span>${chapterLabel}</span>\n                <span>${job.status === 'completed' ? 'Done' : job.status}</span>\n            </div>\n            ${interruptedChip || resumeHint ? `\n                <div class=\"queue-progress-footer\">\n                    <span>${interruptedChip}</span>\n                    <span>${resumeHint}</span>\n                </div>\n            ` : ''}\n            ${showPost ? `\n                <div class=\"queue-post-progress\">\n                    <div class=\"queue-progress-header\">\n                        <span>${postLabel}</span>\n                        <span>${postPercent}%</span>\n                    </div>\n                    <div class=\"progress-bar\">\n                        <div class=\"${postFillClass}\" style=\"width: ${Math.min(Math.max(postPercent, 0), 100)}%;\"></div>\n                    </div>\n                </div>\n            ` : ''}\n        </div>\n    `;\n}\n\nfunction formatEta(seconds, status) {\n""",
        """function renderJobProgress(job) {\n    const total = job.total_chunks || 0;\n    const processed = Math.min(job.processed_chunks || 0, total || Infinity);\n    const percent = total > 0 ? Math.round((processed / total) * 100) : (job.status === 'completed' ? 100 : 0);\n    const chunkLabel = total ? `${processed} / ${total} chunk${total === 1 ? '' : 's'}` : 'Estimating…';\n    const etaLabel = formatEta(job.eta_seconds, job.status);\n    const chapterLabel = job.chapter_mode\n        ? `${job.chapter_count || '?'} chapter${(job.chapter_count || 0) === 1 ? '' : 's'} (per chapter merge)`\n        : 'Single output file';\n    const statusMessage = (job.status_message || '').trim();\n    const isInitializing = job.status === 'processing' && processed === 0;\n    const statusLabel = statusMessage || (job.status === 'completed' ? 'Done' : job.status);\n    const activeLabel = isInitializing ? formatElapsedSince(job.started_at || job.last_update) : etaLabel;\n    const primaryFillClass = isInitializing ? 'progress-bar-fill indeterminate' : 'progress-bar-fill';\n    const primaryFillWidth = isInitializing ? 100 : Math.min(Math.max(percent, 0), 100);\n    const postTotal = Number(job.post_process_total || 0);\n    const postDone = Math.min(Number(job.post_process_done || 0), postTotal || Infinity);\n    const postPercent = Number.isFinite(Number(job.post_process_percent))\n        ? Math.max(0, Math.min(Math.round(Number(job.post_process_percent)), 100))\n        : (postTotal > 0 ? Math.round((postDone / postTotal) * 100) : 0);\n    const isFinishing = job.status === 'processing'\n        && total > 0\n        && processed >= total\n        && (job.eta_seconds === 0 || job.eta_seconds === null || typeof job.eta_seconds !== 'number');\n    const showPost = (postTotal > 0 && (job.post_process_active || postDone > 0)) || isFinishing;\n    const postLabel = postTotal > 0\n        ? `Post-processing ${postDone} / ${postTotal}`\n        : 'Post-processing…';\n    const postFillClass = postTotal > 0 ? 'progress-bar-fill' : 'progress-bar-fill indeterminate';\n    const interruptedChip = job.status === 'interrupted'\n        ? '<span class=\"review-chip warning\">Interrupted</span>'\n        : '';\n    const resumeHint = job.status === 'interrupted' && Number.isFinite(Number(job.resume_from_chunk_index))\n        ? `<span class=\"review-chip muted\">Resume from chunk ${Number(job.resume_from_chunk_index) + 1}</span>`\n        : '';\n\n    return `\n        <div class=\"queue-progress\">\n            <div class=\"queue-progress-header\">\n                <span>${chunkLabel}</span>\n                <span>${activeLabel}</span>\n            </div>\n            <div class=\"progress-bar\">\n                <div class=\"${primaryFillClass}\" style=\"width: ${primaryFillWidth}%;\"></div>\n            </div>\n            <div class=\"queue-progress-footer\">\n                <span>${isInitializing ? statusLabel : chapterLabel}</span>\n                <span>${statusLabel}</span>\n            </div>\n            ${interruptedChip || resumeHint ? `\n                <div class=\"queue-progress-footer\">\n                    <span>${interruptedChip}</span>\n                    <span>${resumeHint}</span>\n                </div>\n            ` : ''}\n            ${showPost ? `\n                <div class=\"queue-post-progress\">\n                    <div class=\"queue-progress-header\">\n                        <span>${postLabel}</span>\n                        <span>${postPercent}%</span>\n                    </div>\n                    <div class=\"progress-bar\">\n                        <div class=\"${postFillClass}\" style=\"width: ${Math.min(Math.max(postPercent, 0), 100)}%;\"></div>\n                    </div>\n                </div>\n            ` : ''}\n        </div>\n    `;\n}\n\nfunction formatElapsedSince(isoString) {\n    if (!isoString) {\n        return 'Starting…';\n    }\n    const started = new Date(isoString);\n    if (Number.isNaN(started.getTime())) {\n        return 'Starting…';\n    }\n    const elapsedSeconds = Math.max(0, Math.floor((Date.now() - started.getTime()) / 1000));\n    const minutes = Math.floor(elapsedSeconds / 60);\n    const seconds = elapsedSeconds % 60;\n    if (minutes > 0) {\n        return `Running ${minutes}m ${seconds}s`;\n    }\n    return `Running ${seconds}s`;\n}\n\nfunction formatEta(seconds, status) {\n""",
        "queue.js render processing status",
    )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = Path(os.environ.get("TTS_STORY_ROOT", "/opt/tts-story"))
    patch_main_js(root)
    patch_app_py(root)
    patch_kitten_engine(root)
    patch_queue_js(root)


if __name__ == "__main__":
    main()
