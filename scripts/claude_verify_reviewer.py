#!/usr/bin/env python3
"""Claude-driven post-verify review.

After auto-verify.yml runs the Playwright + functional check pipeline, this
script asks Claude to look at the resulting artifacts and write a verdict to
`apps/<slug>/.claude-verify-review.json`. It does NOT replace
functional_checker — it stacks on top of it. functional_checker writes the
mechanical pass/fail; this reviewer writes a judgment of fit-for-publish.

Inputs (all read from the slug's repo state):
  apps/<slug>/lzc-manifest.yml             (subdomain, package, services)
  apps/<slug>/.functional-check.json       (machine pass/fail)
  apps/<slug>/.browser-acceptance-plan.json (entry URL + smoke checks)
  apps/<slug>/acceptance/web-screenshots.json (captured screenshot metadata)

Output JSON shape (`apps/<slug>/.claude-verify-review.json`):
  {
    "schema_version": 1,
    "slug": "...",
    "verdict": "pass" | "needs_human" | "fail",
    "score": 0.0-1.0,
    "reasoning": "...",
    "blocking_issues": ["..."],
    "next_action": "publish" | "rebuild" | "human_review",
    "model": "claude-sonnet-4-6",
    "reviewed_at": "..."
  }

Exit codes:
  0  reviewer completed; verdict written
  1  upstream artifacts missing (cannot review)
  2  claude CLI failed (the Project still gets a Blocked update from the
     workflow; the JSON file is left absent so a re-run can retry)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "claude-sonnet-4-6"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read_text(path: Path, *, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n…[truncated, {len(text) - max_chars} more chars]"
    return text


def build_prompt(repo_root: Path, slug: str) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    app_dir = repo_root / "apps" / slug
    manifest = read_text(app_dir / "lzc-manifest.yml", max_chars=4000)
    functional = read_json(app_dir / ".functional-check.json")
    plan = read_json(app_dir / ".browser-acceptance-plan.json")
    screenshots_meta = read_json(app_dir / "acceptance" / "web-screenshots.json")

    if not (functional or plan):
        return None, None

    snapshot = {
        "slug": slug,
        "manifest_excerpt": manifest,
        "functional_check": functional,
        "acceptance_plan": plan,
        "screenshots": screenshots_meta,
    }

    instructions = f"""You are Claude reviewing a LazyCat app post-deployment for publish-readiness.

Goal: decide whether the migrated app is ready to ship to the LazyCat App
Store. The mechanical browser_acceptance_status was already produced by
scripts/functional_checker.py; you are the second-opinion reviewer that judges
the bigger picture (does the app actually work, do the screenshots look like
real product UI, are there blocking errors that the mechanical check missed).

Output requirements:
- Reply with ONE JSON object and nothing else.
- Required fields:
  - verdict: "pass" | "needs_human" | "fail"
  - score: number in [0.0, 1.0] (your confidence the app is publishable AS IS)
  - reasoning: ≤ 80-word summary of why
  - blocking_issues: array of short strings; empty if verdict=pass
  - next_action: "publish" | "rebuild" | "human_review"
- DO NOT wrap in markdown or code fences. Pure JSON.

Calibration:
  0.90+   confident publish (real app UI rendered, no errors, screenshot looks legit)
  0.80    threshold for AI auto-publish (workflow uses this gate)
  0.50    50/50 — prefer "needs_human"
  0.20-   confidently fail (broken render, error page, blank, redirect loop)

Inputs (all under apps/{slug}/):

```json
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
```

Reply with the JSON object now.
"""
    return instructions, snapshot


def call_claude(prompt: str, *, model: str, repo_root: Path) -> tuple[int, str, str]:
    cmd = [
        "claude",
        "--print",
        "--dangerously-skip-permissions",
        "--model",
        model,
        "--add-dir",
        str(repo_root),
        "--output-format",
        "text",
    ]
    proc = subprocess.run(cmd, input=prompt, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    # Try the whole response first.
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    # Fallback: greedy match of the outermost braces.
    match = _JSON_RE.search(raw)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def normalize_verdict(payload: dict[str, Any]) -> dict[str, Any]:
    verdict_raw = str(payload.get("verdict") or "").strip().lower()
    if verdict_raw not in {"pass", "needs_human", "fail"}:
        verdict_raw = "needs_human"

    try:
        score = float(payload.get("score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))

    next_action_raw = str(payload.get("next_action") or "").strip().lower()
    if next_action_raw not in {"publish", "rebuild", "human_review"}:
        if verdict_raw == "pass":
            next_action_raw = "publish"
        elif verdict_raw == "fail":
            next_action_raw = "rebuild"
        else:
            next_action_raw = "human_review"

    blocking = payload.get("blocking_issues") or []
    if not isinstance(blocking, list):
        blocking = [str(blocking)]
    blocking = [str(item) for item in blocking if str(item).strip()]

    reasoning = str(payload.get("reasoning") or "").strip()

    return {
        "verdict": verdict_raw,
        "score": score,
        "reasoning": reasoning,
        "blocking_issues": blocking,
        "next_action": next_action_raw,
    }


def write_review(repo_root: Path, slug: str, normalized: dict[str, Any], *, model: str) -> Path:
    out = {
        "schema_version": 1,
        "slug": slug,
        "model": model,
        "reviewed_at": utc_now_iso(),
        **normalized,
    }
    path = repo_root / "apps" / slug / ".claude-verify-review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("slug")
    p.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--model", default=os.environ.get("LZCAT_VERIFY_MODEL", DEFAULT_MODEL))
    p.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the assembled prompt to stdout and exit (testing).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    prompt, _snapshot = build_prompt(repo_root, args.slug)
    if prompt is None:
        print(
            f"claude_verify_reviewer: no .functional-check.json or "
            f".browser-acceptance-plan.json for slug={args.slug!r}; "
            f"cannot review",
            file=sys.stderr,
        )
        return 1
    if args.print_prompt:
        print(prompt)
        return 0
    rc, stdout, stderr = call_claude(prompt, model=args.model, repo_root=repo_root)
    if rc != 0:
        sys.stderr.write(stderr or stdout)
        sys.stderr.write("\n")
        return 2
    payload = extract_json(stdout)
    if payload is None:
        sys.stderr.write("claude_verify_reviewer: response was not valid JSON\n")
        sys.stderr.write(stdout[:1000])
        return 2
    normalized = normalize_verdict(payload)
    out_path = write_review(repo_root, args.slug, normalized, model=args.model)

    # Audit trail: every verify verdict goes into the cross-cycle log so
    # we can spot drift / Awaiting-Human items that AI confidently passed.
    try:
        from ai_review_log import append_review
    except ImportError:  # pragma: no cover
        from .ai_review_log import append_review  # type: ignore[no-redef]
    append_review(
        repo_root,
        reviewer="verify",
        slug=args.slug,
        item_id=args.slug,
        model=args.model,
        verdict=str(normalized.get("verdict") or ""),
        score=normalized.get("score"),
        reason=str(normalized.get("reasoning") or ""),
        evidence=list(normalized.get("blocking_issues") or []) or None,
        task_dir=str(out_path.parent),
        returncode=0,
        extra={"next_action": str(normalized.get("next_action") or "")},
    )

    print(json.dumps({**normalized, "path": str(out_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
