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

echo "==> SAFE_TO_DELETE: already merged into template + migration/<slug>"
SAFE=(
  codex/htmly-multica-startup-readiness
  codex/storayboat-landing-docs
  feature/ai-auto-migration
  fix/full-migrate-one-click-ab
  lazycat/fix-hermes-agent-bind
)
for br in "${SAFE[@]}"; do delete_if_exists "$br"; done

echo ""
echo "==> WIP_REVIEW: NOT deleting these. Each has unique commits not yet"
echo "    integrated into migration/<slug>. Review and either cherry-pick"
echo "    the commits onto the migration branch, or explicitly abandon."
cat <<'EOF'
   codex/codex-web-lazycat                       slug: codex-web
       (codex-web is now migration/codex-web; consider rebasing
        codex/codex-web-lazycat onto migration/codex-web and PR-ing)
   codex/migrate-cc-connect                      slug: cc-connect      (24 files)
   codex/multica-oidc                            slug: multica         ( 3 files)
   codex/multica-schema-readiness                slug: multica         (13 files)
   codex/htmly-build-fix                         slug: htmly           ( 5 files)
   codex/htmly-install-fix                       slug: htmly           ( 5 files)
   codex/deer-flow-official-deploy-params        slug: deer-flow       ( 4 files)
   fix/app-profile-env-filter-image-state-validate  slug: hermes       ( 8 files)
EOF

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
