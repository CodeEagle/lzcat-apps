#!/usr/bin/env bash
set -euo pipefail

# hermes-auto-update.sh
# Safe updater wrapper for hermes-agent repo. Usage:
#   HERMES_AGENT_GIT_IGNORE=tools/browser_tool.py /usr/local/bin/hermes-auto-update.sh /opt/hermes-agent
# If HERMES_AGENT_GIT_IGNORE is set, allowed dirty files will be marked skip-worktree
# (using /usr/local/bin/hermes-hot-update-compat.sh if present). Otherwise the script
# falls back to stash/pull/pop with a backup if needed.

REPO="${1:-/opt/hermes-agent}"
HELPER="/usr/local/bin/hermes-hot-update-compat.sh"
TS=$(date -u +%Y%m%dT%H%M%SZ)

log(){ printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

if [ ! -d "$REPO/.git" ]; then
  log "No git repository at $REPO"
  exit 1
fi
cd "$REPO"

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)
if [ -z "$BRANCH" ] || [ "$BRANCH" = "HEAD" ]; then
  BRANCH=main
fi

log "Repo: $REPO (branch: $BRANCH)"

# fetch updates (don't fail hard if network hiccup)
git fetch --all --prune || log "git fetch failed (continuing)"

# gather dirty files
mapfile -t dirty_files < <(git ls-files -m -o --exclude-standard || true)
if [ ${#dirty_files[@]} -eq 0 ]; then
  log "No local modifications. Attempting fast-forward pull..."
  if git pull --ff-only origin "$BRANCH"; then
    log "Pulled successfully (ff-only)."
    exit 0
  fi
  log "ff-only failed, trying rebase..."
  if git pull --rebase origin "$BRANCH"; then
    log "Pulled successfully (rebase)."
    exit 0
  fi
  log "Pull failed; creating backup bundle and resetting to origin/$BRANCH"
  mkdir -p "/tmp/hermes-agent-backup-$TS"
  git bundle create "/tmp/hermes-agent-backup-$TS/hermes-agent.$TS.bundle" --all || log "bundle creation failed"
  git reset --hard "origin/$BRANCH" || true
  log "Reset to origin/$BRANCH"
  exit 0
fi

log "Local modifications detected:"
for f in "${dirty_files[@]}"; do log "  $f"; done

# If a whitelist is provided, prefer marking skip-worktree
if [ -n "${HERMES_AGENT_GIT_IGNORE:-}" ]; then
  log "HERMES_AGENT_GIT_IGNORE=$HERMES_AGENT_GIT_IGNORE"
  if [ -x "$HELPER" ]; then
    log "Running helper: $HELPER"
    HERMES_AGENT_GIT_IGNORE="$HERMES_AGENT_GIT_IGNORE" "$HELPER" "$REPO" || { log "Helper failed"; exit 2; }
  else
    # Fallback inline: ensure all dirty files match allowed patterns then mark skip-worktree
    raw="${HERMES_AGENT_GIT_IGNORE//;/,}"
    IFS=',' read -r -a parts <<< "$raw"
    patterns=()
    for p in "${parts[@]}"; do
      for tok in $p; do
        [ -n "$tok" ] && patterns+=("$tok")
      done
    done

    non_matching=()
    for f in "${dirty_files[@]}"; do
      matched=0
      for pat in "${patterns[@]}"; do
        case "$pat" in
          *\**|*\?|*\[*) [[ "$f" == $pat ]] && matched=1 ;;
          *) [[ "$f" == "$pat" || "$f" == "$pat"* || "$f" == *"$pat" ]] && matched=1 ;;
        esac
      done
      if [ "$matched" -eq 0 ]; then
        non_matching+=("$f")
      fi
    done
    if [ ${#non_matching[@]} -gt 0 ]; then
      log "Found dirty files not in HERMES_AGENT_GIT_IGNORE:"
      for nf in "${non_matching[@]}"; do log "  $nf"; done
      log "Aborting; update script must either clean these files or extend HERMES_AGENT_GIT_IGNORE"
      exit 2
    fi
    for f in "${dirty_files[@]}"; do
      log "Marking skip-worktree: $f"
      git update-index --skip-worktree -- "$f" || true
    done
  fi

  # Pull after skip-worktree
  if git pull --ff-only origin "$BRANCH"; then
    log "Pulled successfully after skip-worktree"
    exit 0
  fi
  log "ff-only failed after skip-worktree, trying rebase"
  if git pull --rebase origin "$BRANCH"; then
    log "Pulled successfully (rebase) after skip-worktree"
    exit 0
  fi
  log "Pull failed even after skip-worktree; aborting"
  exit 2
fi

# No whitelist: stash/pop flow with backup if necessary
log "No HERMES_AGENT_GIT_IGNORE set — stashing local changes"
stash_ref=$(git stash push -u -m "autoupdate-$TS" || true)
log "Stashed: ${stash_ref:-<none>}"

pulled=1
if git pull --ff-only origin "$BRANCH"; then
  pulled=0
else
  log "ff-only failed; trying rebase"
  if git pull --rebase origin "$BRANCH"; then
    pulled=0
  fi
fi

if [ $pulled -ne 0 ]; then
  log "Pull failed. Creating backup bundle and resetting to origin/$BRANCH"
  mkdir -p "/tmp/hermes-agent-backup-$TS"
  git bundle create "/tmp/hermes-agent-backup-$TS/hermes-agent.$TS.bundle" --all || log "bundle failed"
  git reset --hard "origin/$BRANCH" || true
  log "Reset to origin/$BRANCH"
  exit 0
fi

# Pull succeeded; try to pop stash
if [ -n "$stash_ref" ]; then
  if git stash pop --index; then
    log "Stash pop succeeded"
    exit 0
  else
    log "Stash pop had conflicts. Manual resolution required. Stash is saved in stash list."
    exit 2
  fi
fi

exit 0
