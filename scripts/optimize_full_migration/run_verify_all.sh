#!/usr/bin/env bash
set -euo pipefail
REPO="/Volumes/ORICO/Development/Github/lzcat/lzcat-apps"
PYTHON="/opt/homebrew/bin/python3"
SCRIPTS="$REPO/scripts"
OUT_BASE="$REPO/optimize_full_migration_test"
mkdir -p "$OUT_BASE"
summary="$OUT_BASE/verify_all_summary.jsonl"
: > "$summary"
count_total=0
count_match=0
count_diff=0
count_error=0
ALL=false
if [ "${1:-}" = "--all" ]; then
  ALL=true
fi

for f in "$REPO/registry/repos/"*.json; do
  if [ "$ALL" = "false" ]; then
    migration_status=$(jq -r '.migration_status // "none"' "$f")
    if [ "$migration_status" != "migrated" ]; then continue; fi
  fi
  slug=$(jq -r '.slug // empty' "$f")
  if [ -z "$slug" ]; then slug=$(basename "$f" .json); fi
  upstream=$(jq -r '.upstream_repo // empty' "$f")
  echo "=== VERIFY ALL: $slug ==="
  count_total=$((count_total+1))
  tmp_clone="/tmp/lzcat-fullmigrate-${slug}.$$"
  rm -rf "$tmp_clone"
  if ! git clone --depth 1 "$REPO" "$tmp_clone" >/dev/null 2>&1; then
    echo "CLONE_FAILED:$slug"
    echo "{\"slug\":\"$slug\",\"status\":\"clone_failed\"}" >> "$summary"
    count_error=$((count_error+1))
    continue
  fi
  mkdir -p "$OUT_BASE/$slug/logs"
  "$PYTHON" "$tmp_clone/scripts/full_migrate.py" "$upstream" --repo-root "$tmp_clone" --no-build --verify > "$OUT_BASE/$slug/logs/full_migrate.verify_all.stdout" 2>&1 || true
  gen_dir="$OUT_BASE/$slug/generated"
  mkdir -p "$gen_dir/registry/repos" "$gen_dir/apps/$slug"
  if [ -f "$tmp_clone/registry/repos/$slug.json" ]; then cp "$tmp_clone/registry/repos/$slug.json" "$gen_dir/registry/repos/$slug.json"; fi
  if [ -f "$tmp_clone/apps/$slug/lzc-manifest.yml" ]; then cp "$tmp_clone/apps/$slug/lzc-manifest.yml" "$gen_dir/apps/$slug/lzc-manifest.yml"; fi
  if [ -f "$tmp_clone/apps/$slug/lzc-build.yml" ]; then cp "$tmp_clone/apps/$slug/lzc-build.yml" "$gen_dir/apps/$slug/lzc-build.yml"; fi
  if [ ! -f "$gen_dir/registry/repos/$slug.json" ]; then
    found=$(find "$tmp_clone" -maxdepth 5 -type f -name "$slug.json" -print -quit || true)
    if [ -n "$found" ]; then cp "$found" "$gen_dir/registry/repos/$slug.json"; fi
  fi
  if [ ! -f "$gen_dir/apps/$slug/lzc-manifest.yml" ]; then
    found=$(find "$tmp_clone" -maxdepth 7 -type f -iname "lzc-manifest.yml" -print -quit || true)
    if [ -n "$found" ]; then cp "$found" "$gen_dir/apps/$slug/lzc-manifest.yml"; fi
  fi
  if [ ! -f "$gen_dir/apps/$slug/lzc-build.yml" ]; then
    found=$(find "$tmp_clone" -maxdepth 7 -type f -iname "lzc-build.yml" -print -quit || true)
    if [ -n "$found" ]; then cp "$found" "$gen_dir/apps/$slug/lzc-build.yml"; fi
  fi
  echo "Running compare_configs.py for $slug"
  "$PYTHON" "$SCRIPTS/optimize_full_migration/compare_configs.py" "$slug" --repo-root "$REPO" --actual-dir "$REPO" --generated-dir "$gen_dir" --diff-dir "$OUT_BASE/$slug/diff.verify_all"
  rc=$?
  tar -czf "$OUT_BASE/$slug/logs/temp_clone_saved.verify_all.tar.gz" -C "$tmp_clone" . || true
  rm -rf "$tmp_clone"
  if [ $rc -eq 0 ]; then
    echo "{\"slug\":\"$slug\",\"upstream\":\"$upstream\",\"status\":\"match\",\"diff_dir\":\"$OUT_BASE/$slug/diff.verify_all\"}" >> "$summary"
    count_match=$((count_match+1))
  else
    echo "{\"slug\":\"$slug\",\"upstream\":\"$upstream\",\"status\":\"diff\",\"diff_dir\":\"$OUT_BASE/$slug/diff.verify_all\"}" >> "$summary"
    count_diff=$((count_diff+1))
  fi
done
echo "{\"total\":$count_total,\"match\":$count_match,\"diff\":$count_diff,\"error\":$count_error}" | tee "$OUT_BASE/verify_all_summary.stats.json"
echo "Summary written to $summary"
