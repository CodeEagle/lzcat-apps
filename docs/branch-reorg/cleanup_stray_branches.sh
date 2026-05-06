#!/usr/bin/env bash
# Phase F: stray-branch cleanup. Run locally; sandbox proxy blocks deletes.
#
# Categories:
#   SAFE_TO_DELETE  : already merged into template/migration; deleting is loss-free
#   WIP_REVIEW      : has unique commits relative to migration/<slug>; do NOT delete
#                     without first cherry-picking the commits onto migration/<slug>
#   ARCHIVE         : rollback snapshots from the reorg; keep until you're sure
#                     the reorg is stable, then delete with the helper below.
#
# Re-running is safe — it skips branches that are already gone.

set -euo pipefail

REPO="${REPO:-CodeEagle/lzcat-apps}"

require() { command -v "$1" >/dev/null 2>&1 || { echo "missing $1"; exit 1; }; }
require git

git fetch origin --prune

delete_if_exists() {
  local br="$1"
  if git ls-remote --exit-code --heads origin "$br" >/dev/null 2>&1; then
    git push origin --delete "$br"
  else
    echo "  $br: already gone"
  fi
}

echo "==> SAFE_TO_DELETE: already merged or work adopted into template/migration"
SAFE=(
  # already merged into template at cutover
  codex/htmly-multica-startup-readiness
  codex/storayboat-landing-docs
  feature/ai-auto-migration
  fix/full-migrate-one-click-ab
  lazycat/fix-hermes-agent-bind

  # WIP work adopted/cherry-picked in Phase F follow-up
  codex/codex-web-lazycat                          # infra cherry-picks 35047e8/2e2da31/8fe9227 + migration/codex-web
  codex/migrate-cc-connect                         # apps/cc-connect adopted onto migration/cc-connect
  codex/multica-oidc                               # patch-login-build.js merged into migration/multica
  fix/app-profile-env-filter-image-state-validate  # apps/hermes adopted onto migration/hermes

  # WIP confirmed obsolete (superseded by newer state already on migration/<slug>)
  codex/multica-schema-readiness
  codex/htmly-build-fix
  codex/htmly-install-fix
  codex/deer-flow-official-deploy-params           # migration/deer-flow is 9 versions newer
)
for br in "${SAFE[@]}"; do delete_if_exists "$br"; done

echo ""
echo "==> ARCHIVE: 16 rollback snapshots retained."
echo "    To delete after reorg is verified stable, run:"
echo "      bash $(realpath "$0") --drop-archives"
if [ "${1:-}" = "--drop-archives" ]; then
  echo ""
  echo "==> Dropping archive/*-pre-reorg branches"
  for br in $(git ls-remote --heads origin 'archive/*-pre-reorg' | awk '{print $2}' | sed 's|refs/heads/||'); do
    delete_if_exists "$br"
  done
fi

echo ""
echo "==> Done."
