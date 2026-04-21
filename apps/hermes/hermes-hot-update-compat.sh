#!/usr/bin/env bash
set -euo pipefail

# hermes-hot-update-compat.sh
# Helper for external updaters: mark allowed dirty files as skip-worktree so
# "git pull" won't fail due to build-time patched files.
# Usage: HERMES_AGENT_GIT_IGNORE=tools/browser_tool.py /usr/local/bin/hermes-hot-update-compat.sh /opt/hermes-agent

REPO="${1:-/opt/hermes-agent}"
cd "$REPO" || { echo "Repository $REPO not found"; exit 1; }

# Get modified (and untracked) files
mapfile -t dirty_files < <(git ls-files -m -o --exclude-standard || true)

if [ "${#dirty_files[@]}" -eq 0 ]; then
  echo "No local modifications in $REPO"
  exit 0
fi

echo "Local modifications detected:";
for f in "${dirty_files[@]}"; do echo "  $f"; done

if [ -z "${HERMES_AGENT_GIT_IGNORE:-}" ]; then
  echo "HERMES_AGENT_GIT_IGNORE not set; aborting (dirty files present)"
  exit 2
fi

# Normalize ignore patterns (split by commas, semicolons, or whitespace)
IFS=',' read -r -a raw_parts <<< "${HERMES_AGENT_GIT_IGNORE//;/,}"
patterns=()
for part in "${raw_parts[@]}"; do
  for token in $part; do
    [ -n "$token" ] && patterns+=("$token")
  done
done

# Check if a file matches any pattern
matches_any() {
  local file="$1"
  for pat in "${patterns[@]}"; do
    # If pattern contains glob chars, use glob match
    if [[ "$pat" == *"*"* || "$pat" == *"?"* || "$pat" == *"["* ]]; then
      if [[ "$file" == $pat ]]; then return 0; fi
    else
      # allow exact match, prefix match, or suffix match
      if [[ "$file" == "$pat" || "$file" == "$pat"* || "$file" == *"$pat" ]]; then
        return 0
      fi
    fi
  done
  return 1
}

non_matching=()
for f in "${dirty_files[@]}"; do
  if ! matches_any "$f"; then
    non_matching+=("$f")
  fi
done

if [ "${#non_matching[@]}" -gt 0 ]; then
  echo "Found dirty files not in HERMES_AGENT_GIT_IGNORE:"
  for f in "${non_matching[@]}"; do echo "  $f"; done
  echo "Aborting. To allow, add patterns to HERMES_AGENT_GIT_IGNORE or clean these files."
  exit 2
fi

# Mark allowed files skip-worktree
for f in "${dirty_files[@]}"; do
  echo "Marking skip-worktree: $f"
  git update-index --skip-worktree -- "$f" || true
done

echo "Marked ${#dirty_files[@]} files with skip-worktree."
exit 0
