#!/usr/bin/env python3
"""
run_all.py — Automated full_migrate.py reproducibility checker.

For each migrated app:
1. Shallow-clone the repo to a temp dir
2. Run full_migrate.py <upstream> --force --no-build in the clone
3. Copy generated configs out
4. Compare generated vs actual (repo HEAD) using compare_configs.py logic
5. Produce per-app diffs and an overall summary.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
SCRIPTS_DIR = REPO_ROOT / "scripts"
WORKSPACE = REPO_ROOT / "optimize_full_migration"

# Config files to compare
CONFIG_FILES = [
    lambda slug: f"registry/repos/{slug}.json",
    lambda slug: f"apps/{slug}/lzc-manifest.yml",
    lambda slug: f"apps/{slug}/lzc-build.yml",
]


def discover_migrated_apps() -> list[tuple[str, str]]:
    """Return [(slug, upstream_repo)] for all migrated apps."""
    apps = []
    registry_dir = REPO_ROOT / "registry" / "repos"
    for f in sorted(registry_dir.glob("*.json")):
        if f.name == "index.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("migration_status") == "migrated":
                slug = f.stem
                upstream = data.get("upstream_repo", "")
                if upstream:
                    apps.append((slug, upstream))
        except Exception:
            continue
    return apps


def clone_repo(dest: Path) -> bool:
    """Shallow-clone the current repo to dest."""
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", str(REPO_ROOT), str(dest)],
            capture_output=True, timeout=120, check=True,
        )
        return True
    except Exception as e:
        print(f"  Clone failed: {e}")
        return False


def overlay_scripts(clone_dir: Path) -> None:
    """Copy current working tree scripts and app profiles over clone for testing fixes."""
    # Copy scripts
    src = REPO_ROOT / "scripts"
    dst = clone_dir / "scripts"
    for py_file in src.glob("*.py"):
        shutil.copy2(py_file, dst / py_file.name)
    # Copy .app-profile.json files from all apps
    apps_src = REPO_ROOT / "apps"
    apps_dst = clone_dir / "apps"
    for profile in apps_src.glob("*/.app-profile.json"):
        slug = profile.parent.name
        target_dir = apps_dst / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile, target_dir / ".app-profile.json")


def run_full_migrate(clone_dir: Path, upstream: str, log_path: Path) -> bool:
    """Run full_migrate.py --force --no-build in the cloned repo."""
    # Overlay current scripts so we test latest fixes
    overlay_scripts(clone_dir)
    cmd = [
        PYTHON,
        str(clone_dir / "scripts" / "full_migrate.py"),
        upstream,
        "--repo-root", str(clone_dir),
        "--force",
        "--no-build",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(clone_dir / "scripts"),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== STDOUT ===\n{result.stdout}\n")
            f.write(f"=== STDERR ===\n{result.stderr}\n")
            f.write(f"=== EXIT CODE: {result.returncode} ===\n")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        log_path.write_text("TIMEOUT after 300s\n", encoding="utf-8")
        return False
    except Exception as e:
        log_path.write_text(f"ERROR: {e}\n", encoding="utf-8")
        return False


def collect_generated(clone_dir: Path, slug: str, out_dir: Path):
    """Copy generated config files from clone to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn_gen in CONFIG_FILES:
        relpath = fn_gen(slug)
        src = clone_dir / relpath
        dst = out_dir / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)


def collect_actual(slug: str, out_dir: Path):
    """Copy actual config files from repo HEAD to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for fn_gen in CONFIG_FILES:
        relpath = fn_gen(slug)
        src = REPO_ROOT / relpath
        dst = out_dir / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)


def run_compare(slug: str, actual_dir: Path, generated_dir: Path, diff_dir: Path) -> tuple[bool, list[str]]:
    """Run compare_configs.py and return (passed, diff_files)."""
    diff_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        PYTHON,
        str(SCRIPTS_DIR / "optimize_full_migration" / "compare_configs.py"),
        slug,
        "--actual-dir", str(actual_dir),
        "--generated-dir", str(generated_dir),
        "--diff-dir", str(diff_dir),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        diff_files = []
        for line in result.stdout.splitlines():
            if line.startswith("DIFF ->"):
                diff_files.append(line.split("->", 1)[1].strip())
            elif line.startswith("MISSING"):
                diff_files.append(line)
        passed = result.returncode == 0
        return passed, diff_files
    except Exception as e:
        return False, [f"compare error: {e}"]


def process_app(slug: str, upstream: str) -> dict:
    """Process a single app: clone, migrate, compare, cleanup."""
    app_workspace = WORKSPACE / slug
    log_path = app_workspace / "logs" / "full_migrate.log"
    actual_dir = app_workspace / "actual"
    generated_dir = app_workspace / "generated"
    diff_dir = app_workspace / "diff"

    # Clean previous run
    for d in [actual_dir, generated_dir, diff_dir]:
        if d.exists():
            shutil.rmtree(d)

    result = {
        "slug": slug,
        "upstream": upstream,
        "status": "unknown",
        "diff_count": 0,
        "diff_files": [],
        "error": None,
    }

    # Collect actual files from repo
    collect_actual(slug, actual_dir)

    # Clone to temp
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"lzcat-opt-{slug}-"))
    try:
        print(f"  Cloning repo...")
        if not clone_repo(tmp_dir):
            result["status"] = "clone_failed"
            result["error"] = "git clone failed"
            return result

        print(f"  Running full_migrate.py --force --no-build...")
        success = run_full_migrate(tmp_dir, upstream, log_path)
        if not success:
            # Still try to compare — partial generation may exist
            print(f"  full_migrate.py exited non-zero, comparing anyway...")

        # Collect generated files
        collect_generated(tmp_dir, slug, generated_dir)

        # Compare
        print(f"  Comparing configs...")
        passed, diff_files = run_compare(slug, actual_dir, generated_dir, diff_dir)
        result["status"] = "pass" if passed else "diff"
        result["diff_count"] = len(diff_files)
        result["diff_files"] = diff_files
        if not success:
            result["error"] = "full_migrate non-zero exit"

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


def main() -> int:
    apps = discover_migrated_apps()
    print(f"Found {len(apps)} migrated apps\n")

    # Filter by CLI args if provided (ignore flags starting with --)
    slug_args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if slug_args:
        filter_slugs = set(slug_args)
        apps = [(s, u) for s, u in apps if s in filter_slugs]
        print(f"Filtered to {len(apps)} apps: {[s for s,_ in apps]}\n")

    WORKSPACE.mkdir(parents=True, exist_ok=True)

    results = []
    counts = {"total": 0, "pass": 0, "diff": 0, "error": 0}
    start_time = time.time()

    for i, (slug, upstream) in enumerate(apps, 1):
        print(f"\n[{i}/{len(apps)}] {slug} ({upstream})")
        counts["total"] += 1

        result = process_app(slug, upstream)
        results.append(result)

        if result["status"] == "pass":
            counts["pass"] += 1
            print(f"  ✓ PASS")
        elif result["status"] == "diff":
            counts["diff"] += 1
            print(f"  ✗ DIFF ({result['diff_count']} files)")
        else:
            counts["error"] += 1
            print(f"  ✗ ERROR: {result.get('error', 'unknown')}")

    elapsed = time.time() - start_time

    # Write summary
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": round(elapsed, 1),
        "counts": counts,
        "results": results,
    }
    summary_path = WORKSPACE / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\n{'='*60}")
    print(f"SUMMARY: {counts['pass']} pass, {counts['diff']} diff, {counts['error']} error / {counts['total']} total")
    print(f"Time: {elapsed:.1f}s")
    print(f"Details: {summary_path}")

    return 0 if counts["diff"] == 0 and counts["error"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
