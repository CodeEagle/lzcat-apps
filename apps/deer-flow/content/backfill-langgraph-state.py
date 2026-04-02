#!/usr/bin/env python3
"""Backfill LangGraph thread state from persisted thread values.

DeerFlow UI thread detail relies on `/threads/{id}/state` and `/history`.
In some deployments, `/threads/search` and `/threads/{id}` still contain
`values` after restart while `/state` and `/history` are empty. This script
repairs those threads by writing `values` back to `/threads/{id}/state`.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


BASE_URL = os.environ.get("DEER_FLOW_INTERNAL_LANGGRAPH_BASE_URL", "http://127.0.0.1:2024").rstrip("/")
TIMEOUT = 10


def request_json(method: str, path: str, payload: dict | None = None) -> dict | list:
    data = None
    headers = {"accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def wait_until_ready(max_wait_seconds: int = 120) -> bool:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        try:
            request_json("POST", "/threads/search", {"limit": 1, "offset": 0})
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            time.sleep(2)
    return False


def state_is_empty(state: dict) -> bool:
    values = state.get("values")
    return not isinstance(values, dict) or len(values) == 0


def run() -> int:
    if not wait_until_ready():
        print("[backfill] LangGraph API not ready; skip.")
        return 0

    print(f"[backfill] API ready: {BASE_URL}")
    fixed = 0
    skipped = 0
    failed = 0
    total = 0
    offset = 0
    page_size = 100

    while True:
        batch = request_json(
            "POST",
            "/threads/search",
            {"limit": page_size, "offset": offset, "sort_by": "updated_at", "sort_order": "desc"},
        )
        if isinstance(batch, dict):
            threads = batch.get("data") or batch.get("threads") or []
        else:
            threads = batch

        if not threads:
            break

        for item in threads:
            thread_id = item.get("thread_id")
            if not thread_id:
                continue
            total += 1
            try:
                state = request_json("GET", f"/threads/{thread_id}/state")
                if isinstance(state, dict) and not state_is_empty(state):
                    skipped += 1
                    continue

                thread = request_json("GET", f"/threads/{thread_id}")
                values = thread.get("values") if isinstance(thread, dict) else None
                if not isinstance(values, dict) or len(values) == 0:
                    skipped += 1
                    continue

                resp = request_json("POST", f"/threads/{thread_id}/state", {"values": values})
                checkpoint_id = resp.get("checkpoint_id") if isinstance(resp, dict) else None
                if checkpoint_id:
                    fixed += 1
                    print(f"[backfill] fixed {thread_id}")
                else:
                    failed += 1
                    print(f"[backfill] failed {thread_id}: no checkpoint_id")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"[backfill] failed {thread_id}: {exc}")

        if len(threads) < page_size:
            break
        offset += len(threads)

    print(f"[backfill] done total={total} fixed={fixed} skipped={skipped} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

