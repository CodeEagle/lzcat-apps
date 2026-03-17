# lzcat-apps Consolidation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `lzcat-apps` the single repo for everything — apps, registry configs, CI/CD scripts, and workflows — eliminating all individual standalone repos and `lzcat-trigger`.

**Architecture:** Scripts and workflows from `lzcat-trigger` move into `lzcat-apps`; `config_repo`/`config_ref` indirection is removed and workflows use `$GITHUB_WORKSPACE` directly; `collect_targets.py` derives app identity from filename stem instead of `repo` field; `run_build.py` uses `lzcat-apps/apps/<app>/` directly instead of cloning individual repos; commit/push goes back to `lzcat-apps` with `git pull --rebase` for concurrency safety. Dev notes live in `docs/notes/`.

**Tech Stack:** Python 3, GitHub Actions, `lzc-cli`, Docker/GHCR

**Spec:** `docs/superpowers/specs/2026-03-17-lzcat-apps-consolidation-design.md`

---

## Chunk 1: Migrate Scripts into lzcat-apps + Update Them

> **Note:** Scripts are copied from `lzcat-trigger` into `lzcat-apps/scripts/` first (Task 0), then all edits in Tasks 1–2 target `lzcat-apps/scripts/` directly. Do NOT modify `lzcat-trigger` scripts.

### Task 0: Copy scripts and create notes directory

**Files:**
- Create: `lzcat-apps/scripts/collect_targets.py`
- Create: `lzcat-apps/scripts/run_build.py`
- Create: `lzcat-apps/docs/notes/README.md`

- [ ] **Step 1: Copy scripts from lzcat-trigger**

```bash
cd lzcat-apps
mkdir -p scripts docs/notes
cp ../lzcat-trigger/scripts/collect_targets.py scripts/
cp ../lzcat-apps/scripts/run_build.py scripts/
```

- [ ] **Step 2: Create notes README**

Create `docs/notes/README.md`:

```markdown
# Dev Notes

Development notes, known issues, and workarounds for lzcat-apps.
Each note is a dated markdown file: `YYYY-MM-DD-<topic>.md`.
```

- [ ] **Step 3: Commit**

```bash
git add scripts/ docs/notes/
git commit -m "chore: migrate CI scripts from lzcat-trigger into lzcat-apps"
```

---

### Task 1: Update `collect_targets.py`

**Files:**
- Modify: `lzcat-apps/scripts/collect_targets.py`

**What changes:**
- `load_configs`: key `by_repo` dict by filename stem (app name) instead of `config["repo"]`; validate manifest path exists; store `_app_name` on config
- `main`: use `by_app` dict (not `by_repo`); matrix item uses `app_name` instead of `target_repo`

- [ ] **Step 1: Replace `load_configs` and `main` in `collect_targets.py`**

Full replacement of `lzcat-trigger/scripts/collect_targets.py`:

```python
#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def load_event_payload() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        return json.loads(Path(event_path).read_text())
    except Exception:
        return {}


def load_configs(config_root: Path) -> tuple[list[dict], dict[str, dict]]:
    index = json.loads((config_root / "repos" / "index.json").read_text())
    apps_root = config_root.parent / "apps"
    configs: list[dict] = []
    by_app: dict[str, dict] = {}
    for file_name in index.get("repos", []):
        config_path = config_root / "repos" / file_name
        config = json.loads(config_path.read_text())
        app_name = Path(file_name).stem
        config["_config_file"] = file_name
        config["_app_name"] = app_name
        manifest = apps_root / app_name / "lzc-manifest.yml"
        if not manifest.exists():
            print(
                f"ERROR: {manifest} not found for config {file_name}. "
                f"Ensure apps/{app_name}/ exists in lzcat-apps.",
                file=sys.stderr,
            )
            sys.exit(1)
        configs.append(config)
        by_app[app_name] = config
    return configs, by_app


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def main() -> int:
    config_root = Path(os.environ["CONFIG_ROOT"]).resolve()
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = load_event_payload()
    payload = event.get("client_payload", {}) if isinstance(event, dict) else {}

    configs, by_app = load_configs(config_root)

    target_repo = (
        os.environ.get("INPUT_TARGET_REPO")
        or str(payload.get("target_repo", "")).strip()
    )
    target_version = (
        os.environ.get("INPUT_TARGET_VERSION")
        or str(payload.get("target_version", "")).strip()
    )
    force_build = parse_bool(
        os.environ.get("INPUT_FORCE_BUILD"),
        parse_bool(payload.get("force_build"), False),
    )
    publish_to_store = parse_bool(
        os.environ.get("INPUT_PUBLISH_TO_STORE"),
        parse_bool(payload.get("publish_to_store"), False),
    )
    check_only = parse_bool(
        os.environ.get("INPUT_CHECK_ONLY"),
        parse_bool(payload.get("check_only"), False),
    )

    selected: list[dict] = []
    if target_repo:
        config = by_app.get(target_repo)
        if not config:
            print(f"Config not found for app: {target_repo}", file=sys.stderr)
            return 1
        selected.append(config)
    else:
        if event_name not in {"schedule", "workflow_dispatch"}:
            print("No target repo provided for non-schedule event", file=sys.stderr)
            return 1
        selected.extend(config for config in configs if parse_bool(config.get("enabled"), True))

    matrix = []
    for config in selected:
        matrix.append(
            {
                "app_name": config["_app_name"],
                "config_file": config["_config_file"],
                "target_version": target_version,
                "force_build": force_build,
                "publish_to_store": publish_to_store,
                "check_only": check_only,
            }
        )

    payload_json = json.dumps(matrix, separators=(",", ":"))
    write_output("matrix", payload_json)
    write_output("has_targets", "true" if matrix else "false")
    print(payload_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the script parses correctly**

```bash
cd lzcat-apps
python3 -c "import ast; ast.parse(open('scripts/collect_targets.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd lzcat-apps
git add scripts/collect_targets.py
git commit -m "feat(collect_targets): derive app identity from filename, validate manifest path"
```

---

### Task 2: Update `run_build.py`

**Files:**
- Modify: `lzcat-apps/scripts/run_build.py`

**What changes:**
- Add `--app-root` and `--lzcat-apps-root` CLI args
- Remove `clone_repo` call for target repo; `repo_dir = Path(args.app_root)`
- `work_root` becomes artifacts-only temp dir (LPK + report)
- `build_target_image`: accept `app_name` param; derive GHCR owner from `GITHUB_REPOSITORY_OWNER` env
- `build_report_base`: accept `app_name`; use it as report `"repo"` identifier
- LPK built into `work_root` (not into repo_dir)
- Commit/push to `lzcat-apps` with `git pull --rebase` before push

- [ ] **Step 1: Add `--app-root` and `--lzcat-apps-root` args to `main()`**

In `run_build.py`, find:
```python
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--artifact-repo", required=True)
```

Replace with:
```python
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--artifact-repo", required=True)
    parser.add_argument("--app-root", required=True, help="Path to lzcat-apps/apps/<app>/")
    parser.add_argument("--lzcat-apps-root", required=True, help="Path to lzcat-apps/ root")
```

- [ ] **Step 2: Replace target-repo clone with direct path in `main()`**

Find:
```python
    work_root = Path(tempfile.mkdtemp(prefix="lzcat-target-"))
    repo_dir = work_root / "target"
    report_path = work_root / "build-report.json"
    report: dict[str, Any] | None = None
    try:
        branch, head_sha = clone_repo(config["repo"], gh_token, repo_dir)
        publish_to_store = args.publish_to_store or parse_bool(config.get("publish_to_store"), False)
        report = build_report_base(
            config=config,
            artifact_repo=args.artifact_repo,
            branch=branch,
            head_sha=head_sha,
            force_build=args.force_build,
            publish_to_store=publish_to_store,
            check_only=args.check_only,
            target_version=args.target_version,
        )
```

Replace with:
```python
    app_name = Path(args.config_file).stem
    repo_dir = Path(args.app_root)
    lzcat_apps_root = Path(args.lzcat_apps_root)
    work_root = Path(tempfile.mkdtemp(prefix="lzcat-artifacts-"))
    report_path = work_root / "build-report.json"
    report: dict[str, Any] | None = None
    try:
        head_sha = sh(["git", "rev-parse", "--short=12", "HEAD"], cwd=lzcat_apps_root)
        publish_to_store = args.publish_to_store or parse_bool(config.get("publish_to_store"), False)
        report = build_report_base(
            config=config,
            app_name=app_name,
            artifact_repo=args.artifact_repo,
            branch="main",
            head_sha=head_sha,
            force_build=args.force_build,
            publish_to_store=publish_to_store,
            check_only=args.check_only,
            target_version=args.target_version,
        )
```

- [ ] **Step 3: Update `build_report_base` to accept `app_name`**

Find:
```python
def build_report_base(
    *,
    config: dict[str, Any],
    artifact_repo: str,
    branch: str,
    head_sha: str,
    force_build: bool,
    publish_to_store: bool,
    check_only: bool,
    target_version: str,
) -> dict[str, Any]:
    return {
        "repo": config["repo"],
```

Replace with:
```python
def build_report_base(
    *,
    config: dict[str, Any],
    app_name: str,
    artifact_repo: str,
    branch: str,
    head_sha: str,
    force_build: bool,
    publish_to_store: bool,
    check_only: bool,
    target_version: str,
) -> dict[str, Any]:
    return {
        "repo": app_name,
```

- [ ] **Step 4: Update `build_target_image` to accept `app_name` param**

Find:
```python
def build_target_image(
    repo_dir: Path,
    config: dict[str, Any],
    env: dict[str, str],
    source_version: str,
    build_version: str,
    head_sha: str,
) -> str:
    owner, name = config["repo"].split("/", 1)
    owner_lower = owner.lower()
    name_lower = name.lower()
    image_tag = head_sha[:12]
    target_image = f"ghcr.io/{owner_lower}/{name_lower}:{image_tag}"
```

Replace with:
```python
def build_target_image(
    repo_dir: Path,
    config: dict[str, Any],
    env: dict[str, str],
    source_version: str,
    build_version: str,
    head_sha: str,
    app_name: str,
) -> str:
    owner_lower = env.get("GITHUB_REPOSITORY_OWNER", "codeagle").lower()
    name_lower = app_name.lower()
    image_tag = head_sha[:12]
    target_image = f"ghcr.io/{owner_lower}/{name_lower}:{image_tag}"
```

- [ ] **Step 5: Update `build_target_image` call site in `main()` to pass `app_name`**

Find:
```python
        target_image = build_target_image(repo_dir, config, env, source_version, build_version, head_sha)
```

Replace with:
```python
        target_image = build_target_image(repo_dir, config, env, source_version, build_version, head_sha, app_name)
```

- [ ] **Step 6: Fix `config["repo"]` in the status print block**

Find:
```python
        print(
            json.dumps(
                {
                    "repo": config["repo"],
                    "source_version": source_version,
                    "build_version": build_version,
                    "update_needed": update_needed,
                    "check_only": args.check_only,
                },
                ensure_ascii=True,
            )
        )
```

Replace with:
```python
        print(
            json.dumps(
                {
                    "repo": app_name,
                    "source_version": source_version,
                    "build_version": build_version,
                    "update_needed": update_needed,
                    "check_only": args.check_only,
                },
                ensure_ascii=True,
            )
        )
```

- [ ] **Step 7: Update LPK output path and `project_name_lower` in `main()`**

Find:
```python
        project_name_lower = config["repo"].split("/", 1)[1].lower()
        lpk_path = repo_dir / f"{project_name_lower}.lpk"
```

Replace with:
```python
        project_name_lower = app_name.lower()
        lpk_path = work_root / f"{project_name_lower}.lpk"
```

- [ ] **Step 8: Update `report["artifact_release_tag"]` in `main()` to not use `config["repo"]`**

Find:
```python
        report["artifact_release_tag"] = f"{config['repo'].replace('/', '--')}-v{build_version}-{build_stamp}"
        write_report(report, report_path)
        report["artifact_release_url"] = publish_release_asset(
            args.artifact_repo,
            report["artifact_release_tag"],
            f"{config['repo']} v{build_version} ({build_stamp})",
            f"Auto-built version {build_version} (source: {source_version}, label: {build_label})",
```

Replace with:
```python
        report["artifact_release_tag"] = f"{app_name}-v{build_version}-{build_stamp}"
        write_report(report, report_path)
        report["artifact_release_url"] = publish_release_asset(
            args.artifact_repo,
            report["artifact_release_tag"],
            f"{app_name} v{build_version} ({build_stamp})",
            f"Auto-built version {build_version} (source: {source_version}, label: {build_label})",
```

- [ ] **Step 9: Add `upstream_repo` to `.lazycat-build.json`**

Find:
```python
        meta_path.write_text(
            json.dumps(
                {
                    "source_version": source_version,
                    "build_version": build_version,
```

Replace with:
```python
        meta_path.write_text(
            json.dumps(
                {
                    "upstream_repo": config.get("upstream_repo", ""),
                    "source_version": source_version,
                    "build_version": build_version,
```

- [ ] **Step 10: Replace commit/push block to target `lzcat-apps`**

Find:
```python
        report["phase"] = "commit_target_repo"
        write_report(report, report_path)
        sh(["git", "config", "user.name", "github-actions[bot]"], cwd=repo_dir)
        sh(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=repo_dir)
        sh(["git", "add", "lzc-manifest.yml", ".lazycat-build.json"], cwd=repo_dir)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
        if diff.returncode != 0:
            sh(["git", "commit", "-m", f"Update to version {build_version}"], cwd=repo_dir)
            sh(["git", "push", "origin", f"HEAD:{branch}"], cwd=repo_dir, env=env)
```

Replace with:
```python
        report["phase"] = "commit_target_repo"
        write_report(report, report_path)
        sh(["git", "config", "user.name", "github-actions[bot]"], cwd=lzcat_apps_root)
        sh(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], cwd=lzcat_apps_root)
        sh(["git", "add", f"apps/{app_name}/lzc-manifest.yml", f"apps/{app_name}/.lazycat-build.json"], cwd=lzcat_apps_root)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=lzcat_apps_root, check=False)
        if diff.returncode != 0:
            sh(["git", "commit", "-m", f"chore({app_name}): update to version {build_version}"], cwd=lzcat_apps_root)
            sh(["git", "pull", "--rebase", "origin", "main"], cwd=lzcat_apps_root, env=env)
            sh(["git", "push", "origin", "HEAD:main"], cwd=lzcat_apps_root, env=env)
```

- [ ] **Step 11: Also update the error handler in `except` block — `config["repo"]` reference**

Find:
```python
        report = {
                "repo": config["repo"] if "config" in locals() else "",
```

Replace with:
```python
        report = {
                "repo": (Path(args.config_file).stem if "args" in locals() else ""),
```

- [ ] **Step 12: Update the `publish_report_summary` references (no change needed — it reads `report["repo"]` which is now `app_name`)**

No change needed.

- [ ] **Step 13: Verify the script parses correctly**

```bash
cd lzcat-apps
python3 -c "import ast; ast.parse(open('scripts/run_build.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 14: Commit**

```bash
git add scripts/run_build.py
git commit -m "feat(run_build): use lzcat-apps app dir directly, commit back to lzcat-apps"
```

---

## Chunk 2: Workflow Changes + Registry JSON Cleanup

### Task 3: Update `update-image.yml`

**Files:**
- Modify: `lzcat-apps/.github/workflows/update-image.yml`

**What changes:**
- `contents: write` permission (needed to push back to lzcat-apps)
- Remove `--depth=1` from config repo clone (needed for push-back to work cleanly)
- Derive `APP_NAME` from `config_file` input in bash; pass `--app-root` and `--lzcat-apps-root` to `run_build.py`

- [ ] **Step 1: Update permissions and clone in `update-image.yml`**

Find:
```yaml
    permissions:
      contents: read
      packages: write
```

Replace with:
```yaml
    permissions:
      contents: write
      packages: write
```

- [ ] **Step 2: Remove `--depth=1` from config repo clone**

Find:
```yaml
          git clone --depth=1 --branch "$CONFIG_REF" "https://x-access-token:${GH_TOKEN}@github.com/${CONFIG_REPO}.git" "$RUNNER_TEMP/lzcat-config"
```

Replace with:
```yaml
          git clone --branch "$CONFIG_REF" "https://x-access-token:${GH_TOKEN}@github.com/${CONFIG_REPO}.git" "$RUNNER_TEMP/lzcat-config"
```

- [ ] **Step 3: Pass `--app-root` and `--lzcat-apps-root` to `run_build.py`**

Find:
```yaml
      - name: Run shared image update flow
        env:
          CONFIG_ROOT: ${{ runner.temp }}/lzcat-config/registry
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GHCR_TOKEN: ${{ secrets.GHCR_TOKEN }}
          GHCR_USERNAME: ${{ secrets.GHCR_USERNAME }}
          LZC_CLI_TOKEN: ${{ secrets.LZC_CLI_TOKEN }}
          GITHUB_REPOSITORY_OWNER: ${{ github.repository_owner }}
        run: |
          args=(
            --config-root "$CONFIG_ROOT"
            --config-file "${{ inputs.config_file }}"
            --artifact-repo "${{ inputs.artifact_repo }}"
          )
```

Replace with:
```yaml
      - name: Run shared image update flow
        env:
          CONFIG_ROOT: ${{ runner.temp }}/lzcat-config/registry
          LZCAT_APPS_ROOT: ${{ runner.temp }}/lzcat-config
          CONFIG_FILE: ${{ inputs.config_file }}
          ARTIFACT_REPO: ${{ inputs.artifact_repo }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GHCR_TOKEN: ${{ secrets.GHCR_TOKEN }}
          GHCR_USERNAME: ${{ secrets.GHCR_USERNAME }}
          LZC_CLI_TOKEN: ${{ secrets.LZC_CLI_TOKEN }}
          GITHUB_REPOSITORY_OWNER: ${{ github.repository_owner }}
        run: |
          APP_NAME="${CONFIG_FILE%.json}"
          args=(
            --config-root "$CONFIG_ROOT"
            --config-file "$CONFIG_FILE"
            --artifact-repo "$ARTIFACT_REPO"
            --app-root "$LZCAT_APPS_ROOT/apps/$APP_NAME"
            --lzcat-apps-root "$LZCAT_APPS_ROOT"
          )
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/update-image.yml
git commit -m "feat(update-image): pass app-root and lzcat-apps-root, enable write permissions"
```

---

### Task 4: Update `trigger-build.yml`

**Files:**
- Modify: `lzcat-apps/.github/workflows/trigger-build.yml`

**What changes:**
- Update `target_repo` input description (now accepts app name, e.g. `paperclip`)
- Update concurrency group to use `matrix.app_name`

- [ ] **Step 1: Update `target_repo` description**

Find:
```yaml
      target_repo:
        description: "Target repository, e.g. CodeEagle/Airi (leave empty to process all enabled repos)"
```

Replace with:
```yaml
      target_repo:
        description: "Target app name, e.g. paperclip (leave empty to process all enabled apps)"
```

- [ ] **Step 2: Update concurrency group**

Find:
```yaml
    concurrency:
      group: build-${{ matrix.target_repo }}
```

Replace with:
```yaml
    concurrency:
      group: build-${{ matrix.app_name }}
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/trigger-build.yml
git commit -m "feat(trigger-build): update target_repo description and concurrency group for app_name"
```

---

### Task 5: Verify end-to-end before removing `repo` field

- [ ] **Step 1: Push lzcat-apps changes**

```bash
git push origin main
```

- [ ] **Step 2: Manually trigger lzcat-apps for paperclip**

In GitHub Actions UI on `CodeEagle/lzcat-trigger`, trigger `Trigger Build` workflow with:
- `target_repo`: `paperclip`
- `force_build`: `true`

- [ ] **Step 3: Verify the build succeeds**

Expected:
- Workflow completes successfully
- `lzcat-apps/apps/paperclip/lzc-manifest.yml` has updated `image:` lines and `version:`
- `lzcat-apps/apps/paperclip/.lazycat-build.json` is committed with `upstream_repo` field
- `.lpk` artifact appears in `lzcat-artifacts`
- No individual standalone repo was touched

---

### Task 6: Remove `repo` field from all registry JSON files in `lzcat-apps`

**Files:**
- Modify: `lzcat-apps/registry/repos/*.json` (all 18 files)

- [ ] **Step 1: Remove `repo` field from all JSON files using a script**

```bash
cd lzcat-apps
python3 - <<'EOF'
import json
from pathlib import Path

repos_dir = Path("registry/repos")
for path in sorted(repos_dir.glob("*.json")):
    if path.name == "index.json":
        continue
    data = json.loads(path.read_text())
    if "repo" in data:
        del data["repo"]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"Removed repo field from {path.name}")
    else:
        print(f"No repo field in {path.name} (skipped)")
EOF
```

Expected: 18 files updated, each printing "Removed repo field from X.json"

- [ ] **Step 2: Verify JSON files are valid**

```bash
python3 - <<'EOF'
import json
from pathlib import Path

for path in Path("registry/repos").glob("*.json"):
    json.loads(path.read_text())
    print(f"OK: {path.name}")
EOF
```

Expected: All files print `OK`

- [ ] **Step 3: Commit and push**

```bash
git add registry/repos/
git commit -m "chore: remove repo field from all registry JSON configs"
git push origin main
```

---

### Task 7: Final verification

- [ ] **Step 1: Run a scheduled-style build (all enabled apps)**

Manually trigger `Trigger Build` with all defaults (no `target_repo`, `force_build`: `false`). Verify that `collect_targets.py` correctly selects all enabled apps.

- [ ] **Step 2: Confirm no references to individual repos remain in lzcat-apps scripts**

```bash
cd lzcat-apps
grep -r "config\[.repo.\]" scripts/
```

Expected: No output

- [ ] **Step 3: Update the spec status**

Edit `lzcat-apps/docs/superpowers/specs/2026-03-17-lzcat-apps-consolidation-design.md`:

Change `**Status**: Draft` to `**Status**: Implemented`

- [ ] **Step 4: Commit spec update**

```bash
cd lzcat-apps
git add docs/superpowers/specs/2026-03-17-lzcat-apps-consolidation-design.md
git commit -m "docs: mark consolidation spec as implemented"
git push origin main
```

---

## Chunk 3: Migrate lzcat-trigger Workflows into lzcat-apps

### Task 8: Copy and simplify `trigger-build.yml`

**Files:**
- Create: `lzcat-apps/.github/workflows/trigger-build.yml`

**What changes from the lzcat-trigger version:**
- Remove `config_repo`, `config_ref` inputs and the "Resolve config source" + "Checkout config repository" steps in `prepare` job — workflows now live in the same repo, so `$GITHUB_WORKSPACE` IS the config root
- `CONFIG_ROOT` becomes `$GITHUB_WORKSPACE/registry`
- Remove `config_repo`/`config_ref` outputs from prepare job and inputs to build job
- `scripts/collect_targets.py` path stays the same (now at repo root `scripts/`)

- [ ] **Step 1: Create `lzcat-apps/.github/workflows/trigger-build.yml`**

```bash
mkdir -p lzcat-apps/.github/workflows
```

Write `lzcat-apps/.github/workflows/trigger-build.yml`:

```yaml
name: Trigger Build

on:
  workflow_dispatch:
    inputs:
      target_repo:
        description: "Target app name, e.g. paperclip (leave empty to process all enabled apps)"
        required: false
        default: ""
        type: string
      target_version:
        description: "Target upstream version to build. Leave empty for latest."
        required: false
        default: ""
        type: string
      force_build:
        description: "Force build regardless of current source version"
        required: false
        default: false
        type: boolean
      publish_to_store:
        description: "Publish generated package to LazyCat App Store"
        required: false
        default: false
        type: boolean
      check_only:
        description: "Only check whether an update is needed"
        required: false
        default: false
        type: boolean
      artifact_repo:
        description: "Central repository to store LPK artifacts and build reports"
        required: false
        default: "CodeEagle/lzcat-artifacts"
        type: string
  repository_dispatch:
    types:
      - lzcat-build
  schedule:
    - cron: "0 */12 * * *"

jobs:
  prepare:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.collect.outputs.matrix }}
      has_targets: ${{ steps.collect.outputs.has_targets }}
      artifact_repo: ${{ steps.resolve.outputs.artifact_repo }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Resolve artifact repo
        id: resolve
        run: |
          ARTIFACT_REPO="${{ inputs.artifact_repo }}"
          if [ -z "$ARTIFACT_REPO" ]; then
            ARTIFACT_REPO="CodeEagle/lzcat-artifacts"
          fi
          echo "artifact_repo=${ARTIFACT_REPO}" >> "$GITHUB_OUTPUT"

      - name: Collect targets
        id: collect
        env:
          CONFIG_ROOT: ${{ github.workspace }}/registry
          INPUT_TARGET_REPO: ${{ inputs.target_repo }}
          INPUT_TARGET_VERSION: ${{ inputs.target_version }}
          INPUT_FORCE_BUILD: ${{ inputs.force_build }}
          INPUT_PUBLISH_TO_STORE: ${{ inputs.publish_to_store }}
          INPUT_CHECK_ONLY: ${{ inputs.check_only }}
        run: |
          python3 scripts/collect_targets.py

  build:
    needs: prepare
    if: needs.prepare.outputs.has_targets == 'true'
    strategy:
      fail-fast: false
      max-parallel: 2
      matrix:
        include: ${{ fromJson(needs.prepare.outputs.matrix) }}
    concurrency:
      group: build-${{ matrix.app_name }}
      cancel-in-progress: false
    uses: ./.github/workflows/update-image.yml
    with:
      artifact_repo: ${{ needs.prepare.outputs.artifact_repo }}
      config_file: ${{ matrix.config_file }}
      target_version: ${{ matrix.target_version }}
      force_build: ${{ matrix.force_build }}
      publish_to_store: ${{ matrix.publish_to_store }}
      check_only: ${{ matrix.check_only }}
    secrets: inherit
```

- [ ] **Step 2: Commit**

```bash
cd lzcat-apps
git add .github/workflows/trigger-build.yml
git commit -m "feat: add trigger-build workflow (migrated from lzcat-trigger, simplified)"
```

---

### Task 9: Copy and simplify `update-image.yml`

**Files:**
- Create: `lzcat-apps/.github/workflows/update-image.yml`

**What changes from the lzcat-trigger version:**
- Remove `config_repo`, `config_ref` inputs
- Remove "Checkout config repository" step
- `CONFIG_ROOT` → `$GITHUB_WORKSPACE/registry`
- `LZCAT_APPS_ROOT` → `$GITHUB_WORKSPACE`
- `scripts/run_build.py` path stays the same

- [ ] **Step 1: Create `lzcat-apps/.github/workflows/update-image.yml`**

Write `lzcat-apps/.github/workflows/update-image.yml`:

```yaml
name: Update Image

on:
  workflow_call:
    inputs:
      artifact_repo:
        required: true
        type: string
      config_file:
        required: true
        type: string
      target_version:
        required: false
        type: string
        default: ""
      force_build:
        required: false
        type: boolean
        default: false
      publish_to_store:
        required: false
        type: boolean
        default: false
      check_only:
        required: false
        type: boolean
        default: false

jobs:
  update-image:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install lzc-cli
        run: npm install -g @lazycatcloud/lzc-cli

      - name: Run shared image update flow
        env:
          CONFIG_ROOT: ${{ github.workspace }}/registry
          LZCAT_APPS_ROOT: ${{ github.workspace }}
          CONFIG_FILE: ${{ inputs.config_file }}
          ARTIFACT_REPO: ${{ inputs.artifact_repo }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GHCR_TOKEN: ${{ secrets.GHCR_TOKEN }}
          GHCR_USERNAME: ${{ secrets.GHCR_USERNAME }}
          LZC_CLI_TOKEN: ${{ secrets.LZC_CLI_TOKEN }}
          GITHUB_REPOSITORY_OWNER: ${{ github.repository_owner }}
        run: |
          APP_NAME="${CONFIG_FILE%.json}"
          args=(
            --config-root "$CONFIG_ROOT"
            --config-file "$CONFIG_FILE"
            --artifact-repo "$ARTIFACT_REPO"
            --app-root "$LZCAT_APPS_ROOT/apps/$APP_NAME"
            --lzcat-apps-root "$LZCAT_APPS_ROOT"
          )

          if [ -n "${{ inputs.target_version }}" ]; then
            args+=(--target-version "${{ inputs.target_version }}")
          fi
          if [ "${{ inputs.force_build }}" = "true" ]; then
            args+=(--force-build)
          fi
          if [ "${{ inputs.publish_to_store }}" = "true" ]; then
            args+=(--publish-to-store)
          fi
          if [ "${{ inputs.check_only }}" = "true" ]; then
            args+=(--check-only)
          fi

          python3 scripts/run_build.py "${args[@]}"
```

- [ ] **Step 2: Commit and push**

```bash
cd lzcat-apps
git add .github/workflows/update-image.yml
git commit -m "feat: add update-image workflow (migrated from lzcat-trigger, simplified)"
git push origin main
```

---

### Task 10: Verify and archive lzcat-trigger

- [ ] **Step 1: Manually trigger the new workflow in lzcat-apps**

In GitHub Actions UI on `CodeEagle/lzcat-apps`, trigger `Trigger Build` with:
- `target_repo`: `paperclip`
- `force_build`: `true`

Confirm the build completes and `lzcat-apps/apps/paperclip/lzc-manifest.yml` is updated.

- [ ] **Step 2: After 48h soak — archive repos**

Archive the following on GitHub (Settings → Archive this repository):
- `CodeEagle/lzcat-trigger`
- `CodeEagle/lzcat-registry`
- All individual app repos (`CodeEagle/paperclip`, `CodeEagle/airflow`, etc.)

- [ ] **Step 3: Update spec status**

Edit `docs/superpowers/specs/2026-03-17-lzcat-apps-consolidation-design.md`:
Change `**Status**: Draft` to `**Status**: Implemented`

- [ ] **Step 4: Commit**

```bash
cd lzcat-apps
git add docs/superpowers/specs/2026-03-17-lzcat-apps-consolidation-design.md
git commit -m "docs: mark consolidation spec as implemented"
git push origin main
```
