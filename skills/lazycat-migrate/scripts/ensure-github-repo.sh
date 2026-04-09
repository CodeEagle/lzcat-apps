#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/github.sh
source "$SCRIPT_DIR/lib/github.sh"
# shellcheck source=./lib/progress.sh
source "$SCRIPT_DIR/lib/progress.sh"

usage() {
  cat <<USAGE
Usage: $(basename "$0") --upstream-repo owner/name [options]

Create or verify the target GitHub repository for a LazyCat migration.
The default target name is the upstream repository name, and gh auth is
switched to CodeEagle before any GitHub operation.

Options:
  --upstream-repo owner/name    Required upstream repository
  --repo-owner owner            Default: CodeEagle
  --repo-name name              Optional override; default: upstream repo name
  --description text            Optional repository description
  --clone-dir path              Optional directory used with gh repo create --clone
  --seed-dir path               Optional local directory used to bootstrap repository files
  --private                     Create as private repository
  --public                      Create as public repository (default)
  -h, --help
USAGE
}

UPSTREAM_REPO=""
REPO_OWNER="CodeEagle"
REPO_NAME=""
DESCRIPTION=""
CLONE_DIR=""
SEED_DIR=""
VISIBILITY="--public"
last_progress_step="ensure_target_repo"

on_error() {
  local line="$1"
  local code="$2"
  local summary="ensure-github-repo failed at line ${line} (exit ${code})"
  progress_emit "$last_progress_step" "failed" "$summary" "$(progress_classify_failure "$summary")"
  exit "$code"
}

trap 'on_error ${LINENO} $?' ERR

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upstream-repo) UPSTREAM_REPO="$2"; shift 2 ;;
    --repo-owner) REPO_OWNER="$2"; shift 2 ;;
    --repo-name) REPO_NAME="$2"; shift 2 ;;
    --description) DESCRIPTION="$2"; shift 2 ;;
    --clone-dir) CLONE_DIR="$2"; shift 2 ;;
    --seed-dir) SEED_DIR="$2"; shift 2 ;;
    --private) VISIBILITY="--private"; shift ;;
    --public) VISIBILITY="--public"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$UPSTREAM_REPO" ]] || { usage; exit 1; }

require_command git
last_progress_step="ensure_target_repo_auth"
progress_emit "ensure_target_repo_auth" "started" "checking GitHub auth before repository preparation"
ensure_gh_auth "CodeEagle"
progress_emit "ensure_target_repo_auth" "succeeded" "GitHub auth ready for repository preparation"

if [[ -z "$REPO_NAME" ]]; then
  REPO_NAME="$(repo_name_from_upstream "$UPSTREAM_REPO")"
fi

TARGET_REPO="${REPO_OWNER}/${REPO_NAME}"
progress_emit "ensure_target_repo_prepare" "running" "resolved target repository ${TARGET_REPO}"

if gh repo view "$TARGET_REPO" >/dev/null 2>&1; then
  echo "Repository already exists: $TARGET_REPO"
  progress_emit "ensure_target_repo_create" "succeeded" "target repository already exists: ${TARGET_REPO}"
else
  last_progress_step="ensure_target_repo_create"
  progress_emit "ensure_target_repo_create" "started" "creating target repository ${TARGET_REPO}"
  create_args=(repo create "$TARGET_REPO" "$VISIBILITY")
  if [[ -n "$DESCRIPTION" ]]; then
    create_args+=(--description "$DESCRIPTION")
  fi

  if [[ -n "$CLONE_DIR" ]]; then
    mkdir -p "$CLONE_DIR"
    (
      cd "$CLONE_DIR"
      gh "${create_args[@]}" --clone
    )
  else
    gh "${create_args[@]}"
  fi
  progress_emit "ensure_target_repo_create" "succeeded" "target repository created: ${TARGET_REPO}"
fi

needs_seed=0
if [[ -n "$SEED_DIR" ]]; then
  if [[ ! -d "$SEED_DIR" ]]; then
    echo "Seed directory not found: $SEED_DIR" >&2
    exit 1
  fi

  workflow_content="$(gh api "repos/$TARGET_REPO/contents/.github/workflows/update-image.yml" --jq '.content' 2>/dev/null | base64 -d 2>/dev/null || true)"
  if [[ -z "$workflow_content" ]]; then
    needs_seed=1
  elif grep -Eq '{{[A-Z_][A-Z0-9_]*}}' <<<"$workflow_content"; then
    needs_seed=1
  elif [[ -f "$SEED_DIR/.github/workflows/update-image.yml" ]]; then
    seed_workflow_content="$(cat "$SEED_DIR/.github/workflows/update-image.yml")"
    if [[ "$workflow_content" != "$seed_workflow_content" ]]; then
      needs_seed=1
    fi
  fi
fi

if [[ "$needs_seed" -eq 1 ]]; then
  last_progress_step="ensure_target_repo_seed"
  progress_emit "ensure_target_repo_seed" "started" "seeding repository template into ${TARGET_REPO}"
  echo "Seeding repository content for $TARGET_REPO from $SEED_DIR"
  default_branch="$(gh repo view "$TARGET_REPO" --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || true)"
  if [[ -z "$default_branch" || "$default_branch" == "null" ]]; then
    default_branch="main"
  fi
  github_token="${GH_TOKEN:-$(gh auth token)}"
  authed_remote="https://x-access-token:${github_token}@github.com/${TARGET_REPO}.git"
  ssh_remote="git@github.com:${TARGET_REPO}.git"
  using_https=0
  ssh_key=""
  if [[ -f "${HOME}/.ssh/id_ed25519" ]]; then
    ssh_key="${HOME}/.ssh/id_ed25519"
  elif [[ -f "${HOME}/.ssh/id_rsa" ]]; then
    ssh_key="${HOME}/.ssh/id_rsa"
  fi
  ssh_cmd="ssh -F /dev/null -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  if [[ -n "$ssh_key" ]]; then
    ssh_cmd="${ssh_cmd} -i ${ssh_key}"
  fi
  export GIT_SSH_COMMAND="$ssh_cmd"
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT

  if command -v ssh >/dev/null 2>&1 && [[ -d "${HOME}/.ssh" ]]; then
    if ! git clone "$ssh_remote" "$tmp_dir/repo" --depth=1 >/dev/null 2>&1; then
      using_https=1
      git clone "$authed_remote" "$tmp_dir/repo" --depth=1 >/dev/null
    fi
  else
    using_https=1
    git clone "$authed_remote" "$tmp_dir/repo" --depth=1 >/dev/null
  fi

  find "$tmp_dir/repo" -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +
  (cd "$SEED_DIR" && tar cf - --exclude=.git .) | (cd "$tmp_dir/repo" && tar xf -)

  (
    cd "$tmp_dir/repo"
    git add -A
    if ! git diff --cached --quiet; then
      git config user.name "lazycat-migration-bot"
      git config user.email "lazycat-migration-bot@users.noreply.github.com"
      git commit -m "chore: bootstrap lazycat migration template"
      if [[ "$using_https" -eq 1 ]]; then
        git remote set-url origin "$authed_remote"
      else
        git remote set-url origin "$ssh_remote"
      fi
      git push origin "HEAD:$default_branch"
      progress_emit "ensure_target_repo_seed" "succeeded" "seed content pushed to ${TARGET_REPO}:${default_branch}"
    else
      echo "No seed changes detected for $TARGET_REPO"
      progress_emit "ensure_target_repo_seed" "succeeded" "seed content already up to date for ${TARGET_REPO}"
    fi
  )
fi

REPO_URL="$(gh repo view "$TARGET_REPO" --json url --jq '.url')"
progress_emit "ensure_target_repo" "succeeded" "target repository ready: ${TARGET_REPO}"
echo "TARGET_REPO=$TARGET_REPO"
echo "TARGET_REPO_URL=$REPO_URL"
