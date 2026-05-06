#!/usr/bin/env bash
# Generate staged/migration/<slug> branches from template-clean.
# Each branch contains template-clean + apps/<slug>/ + registry/repos/<slug>.json
# + 1 line in registry/repos/index.json + 1 line in trigger-build.yml options.
set -euo pipefail

REPO=/home/user/lzcat-apps
cd "$REPO"

MANIFEST=/tmp/migration_manifest.json
LOG=/tmp/staged_gen.log
: > "$LOG"

isolate_one() {
  local slug="$1"
  local source_ref="$2"
  local branch="staged/migration/$slug"
  echo "=== $slug from $source_ref ===" | tee -a "$LOG"

  # Reset to template-clean (we may already be on a previous staged branch)
  git checkout -q template-clean
  git checkout -q -b "$branch"

  # Restore apps/<slug>/ — accept missing dir for stub-only cases
  if git rev-parse --verify "$source_ref:apps/$slug" >/dev/null 2>&1; then
    git checkout -q "$source_ref" -- "apps/$slug"
  else
    echo "  WARN: $source_ref:apps/$slug not found" | tee -a "$LOG"
  fi
  git rm -qf apps/.gitkeep 2>/dev/null || true

  # Restore registry/repos/<slug>.json: prefer source_ref, fall back to template
  if git rev-parse --verify "$source_ref:registry/repos/$slug.json" >/dev/null 2>&1; then
    git checkout -q "$source_ref" -- "registry/repos/$slug.json"
  elif git rev-parse --verify "origin/template:registry/repos/$slug.json" >/dev/null 2>&1; then
    git checkout -q origin/template -- "registry/repos/$slug.json"
  elif git rev-parse --verify "origin/main:registry/repos/$slug.json" >/dev/null 2>&1; then
    git checkout -q origin/main -- "registry/repos/$slug.json"
  else
    echo "  WARN: no registry/repos/$slug.json anywhere" | tee -a "$LOG"
  fi

  # Add slug to registry index
  python3 - "$slug" << 'PY'
import json, sys
slug = sys.argv[1]
p = 'registry/repos/index.json'
d = json.load(open(p))
entry = f"{slug}.json"
if entry not in d['repos']:
    d['repos'].append(entry)
with open(p, 'w') as f:
    json.dump(d, f, indent=2); f.write('\n')
PY

  # Add slug to trigger-build.yml options
  python3 - "$slug" << 'PY'
import sys
from pathlib import Path
slug = sys.argv[1]
p = Path('.github/workflows/trigger-build.yml')
text = p.read_text()
end_marker = '# END AUTO-GENERATED APP OPTIONS'
indent = '          '
new_line = f'{indent}- "{slug}"\n'
if f'- "{slug}"' in text:
    sys.exit(0)
idx = text.find(end_marker)
text = text[:idx] + new_line + indent + text[idx:]
p.write_text(text)
PY

  git add -A
  git commit -q -m "feat($slug): isolate migration artifacts onto migration/$slug

Source: $source_ref
Branched from: template-clean

Rollback: archive/main-pre-reorg, archive/template-pre-reorg, or
archive/$(echo $source_ref | sed 's|^origin/||' | tr '/' '-')-pre-reorg"

  echo "  -> $(git rev-parse --short HEAD)" | tee -a "$LOG"
}

# Read manifest
mapfile -t FROM_MAIN < <(python3 -c "import json; print('\n'.join(json.load(open('$MANIFEST'))['from_main']))")
mapfile -t FROM_MB   < <(python3 -c "import json; print('\n'.join(json.load(open('$MANIFEST'))['from_migration_branch']))")

for slug in "${FROM_MAIN[@]}";  do isolate_one "$slug" "origin/main"; done
for slug in "${FROM_MB[@]}";    do isolate_one "$slug" "origin/migration/$slug"; done

# Specials
isolate_one "fusion"       "origin/migrate/fusion"
isolate_one "hermes-webui" "origin/migrate/hermes-webui"
isolate_one "warp"         "origin/migration-warp"

echo ""
echo "Generated $(git branch | grep -c '^  staged/migration/') staged branches"
git checkout -q claude/merge-apps-migration-setup-2OrDV
