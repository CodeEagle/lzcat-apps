#!/usr/bin/env python3
"""Append-only audit log for every AI review in the auto-migration pipeline.

Both `scripts/codex_discovery_reviewer.py` (which calls itself "codex" but
runs Claude under the hood) and `scripts/claude_verify_reviewer.py` write
one line per review here so we can periodically scan the log to:
  * Spot calibration drift (consistently low/high scores)
  * Catch cases where Claude marked something migrate but later builds failed
  * Audit Project Status changes against verdicts
  * Compute reviewer-vs-reviewer agreement rates if we add a second model

File: registry/auto-migration/ai-reviews.jsonl  (one JSON object per line)

Schema:
{
  "ts":         ISO-8601 UTC timestamp
  "reviewer":   "discovery" | "verify"        # which review stage
  "slug":       "<slug>"                      # repo / app slug
  "item_id":    "<queue item id>"             # for discovery: queue.json id; for verify: same as slug
  "model":      "claude-sonnet-4-6" | ...
  "verdict":    "migrate"|"skip"|"needs_human" | "pass"|"fail"|"needs_human"
  "score":      0.0-1.0  (nullable for early discovery rows that didn't score)
  "reason":     short summary
  "evidence":   [list of strings] | null
  "task_dir":   path to the per-task working dir (raw stdout, prompt etc.)
  "returncode": int  (claude CLI exit code; 0 = ok)
  "extra":      arbitrary additional context per reviewer kind
}

The log is gitignored under registry/auto-migration/ but kept across cron
cycles via the same canonical-state commit step that auto-discover.yml
already runs (we'll opt the file into the .gitignore re-include list).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path("registry") / "auto-migration" / "ai-reviews.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_review(
    repo_root: Path,
    *,
    reviewer: str,
    slug: str,
    item_id: str = "",
    model: str = "",
    verdict: str = "",
    score: float | None = None,
    reason: str = "",
    evidence: list[str] | None = None,
    task_dir: str = "",
    returncode: int | None = None,
    extra: dict[str, Any] | None = None,
    ts: str | None = None,
    log_path: Path | str | None = None,
) -> Path:
    """Append one structured row to the audit log. Caller-friendly defaults.

    Returns the file path that was written so the caller can log/commit it.
    Best-effort: any IOError is allowed to propagate so the caller can
    decide whether to surface it (workflows tend to log + continue).
    """
    base = Path(log_path) if log_path else (repo_root / DEFAULT_LOG_PATH)
    base.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ts": ts or _utc_now_iso(),
        "reviewer": str(reviewer or "").strip() or "unknown",
        "slug": str(slug or "").strip(),
        "item_id": str(item_id or slug or "").strip(),
        "model": str(model or "").strip(),
        "verdict": str(verdict or "").strip(),
        "score": float(score) if score is not None else None,
        "reason": str(reason or "").strip(),
        "evidence": list(evidence) if isinstance(evidence, list) else None,
        "task_dir": str(task_dir or "").strip(),
        "returncode": int(returncode) if returncode is not None else None,
        "extra": dict(extra) if isinstance(extra, dict) else None,
    }
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    with base.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return base


def iter_reviews(log_path: Path | str) -> list[dict[str, Any]]:
    """Read the entire audit log. Tolerates malformed lines (skips them)."""
    p = Path(log_path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out
