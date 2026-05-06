#!/usr/bin/env bash
# Phase E remainder: branch deletions blocked by sandbox proxy.
# Run this locally (with a token that has push+delete on CodeEagle/lzcat-apps).
#
# Pre-conditions (already done from the agent session):
#   - origin/template == new "clean" trunk
#   - origin/migration/<slug> populated for all 57 slugs
#   - archive/<name>-pre-reorg branches exist as rollback points
#
# This script:
#   1. Switches default branch to "template" via gh API (so main can be deleted)
#   2. Deletes obsolete migrate/* and migration-warp branches
#   3. Deletes the 57 staged/migration/<slug> branches
#   4. Deletes template-clean (now identical to template)
#   5. Deletes main (after default-branch switch confirmed)
#
# Rollback for any step is documented in docs/branch-reorg/README.md.

set -euo pipefail

REPO="${REPO:-CodeEagle/lzcat-apps}"

require() { command -v "$1" >/dev/null 2>&1 || { echo "missing $1"; exit 1; }; }
require git
require gh

echo "==> 1. Switch default branch to 'template'"
gh api -X PATCH "repos/$REPO" -f default_branch=template
echo "    OK"

echo ""
echo "==> 2. Fetch origin so we can see remote refs"
git fetch origin --prune

echo ""
echo "==> 3. Delete obsolete branches"
for br in migrate/fusion migrate/hermes-webui migration-warp migrate/fix-rebase-conflict template-clean; do
  if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
    git push origin --delete "$br"
  else
    echo "    $br: already gone"
  fi
done

echo ""
echo "==> 4. Delete all staged/migration/* branches"
mapfile -t STAGED < <(git ls-remote --heads origin 'staged/migration/*' | awk '{print $2}' | sed 's|refs/heads/||')
echo "    ${#STAGED[@]} staged branches to delete"
DEL_REFS=()
for br in "${STAGED[@]}"; do DEL_REFS+=(":refs/heads/$br"); done
[ ${#DEL_REFS[@]} -gt 0 ] && git push origin "${DEL_REFS[@]}"

echo ""
echo "==> 5. Delete main (after default branch switched in step 1)"
if git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
  git push origin --delete main
else
  echo "    main: already gone"
fi

echo ""
echo "==> Done."
echo "    archive/* branches retained for rollback."
echo "    To clean up archives later: see docs/branch-reorg/README.md."
