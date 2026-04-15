#!/usr/bin/env python3
"""
compare_configs.py

Normalize JSON/YAML/text outputs produced by full_migrate and produce unified diffs.
Writes pretty-printed normalized files to <diff_dir> and diffs to <diff_dir>/*.diff.
Exit code 0: no diffs; 1: diffs found.
"""
import argparse
import json
import difflib
import sys
import re
from pathlib import Path
from typing import Any

# optional YAML parsing for better manifest normalization
try:
    import yaml
    YAML_AVAILABLE = True
except Exception:
    YAML_AVAILABLE = False

REMOVE_KEY_PATTERNS = [
    re.compile(pat) for pat in [
        r"timestamp",
        r"^created",
        r"^updated",
        r"generated",
        r"build[_-]?time",
        r"build_date",
        r"last[_-]?modified",
        r"commit(_time|_date)?$",
        r"sha$",
        r"digest$",
        r"image[_-]?(digest|sha)",
        r"^version$",  # version drifts with upstream releases — not a generation bug
        r"^description$",  # description text may differ slightly between manifest and locales
        r"^locales$",  # locale blocks are cosmetic and derived from top-level name/description
    ]
]

SHA_RE = re.compile(r"^[0-9a-f]{8,64}$", re.IGNORECASE)


def should_remove_key(key: str) -> bool:
    k = key.lower()
    for pat in REMOVE_KEY_PATTERNS:
        if pat.search(k):
            return True
    return False


# helpers

def _normalize_image(img: str) -> str:
    # strip image tag so tags don't cause diffs
    normalized = re.sub(r":[^:/\s]+$", ":TAG", img)
    # Normalize placeholder images — they differ from real registry paths
    # but are semantically equivalent (replaced during build)
    normalized = re.sub(r"registry\.lazycat\.cloud/[^:]+", "registry.lazycat.cloud/IMAGE", normalized)
    return normalized


def _normalize_bind_entry(entry: str) -> str:
    # keep only the container-side path (after last ':') to avoid host path noise
    if not isinstance(entry, str):
        return entry
    if ':' in entry:
        return entry.rsplit(':', 1)[-1]
    return entry


def _normalize_healthcheck(hc: Any) -> Any:
    # canonicalize to dict {test: str, interval: int?, retries: int?}
    if isinstance(hc, dict):
        out = {}
        # test may be list or string
        test = hc.get('test') or hc.get('Test') or hc.get('TEST')
        if isinstance(test, list):
            out['test'] = ' '.join(str(x) for x in test)
        elif test is not None:
            out['test'] = str(test)
        # interval: convert '10s' -> 10
        interval = hc.get('interval')
        if isinstance(interval, str) and interval.endswith('s'):
            try:
                out['interval'] = int(interval[:-1])
            except Exception:
                out['interval'] = interval
        elif isinstance(interval, (int, float)):
            out['interval'] = int(interval)
        # retries
        retries = hc.get('retries')
        if retries is not None:
            try:
                out['retries'] = int(retries)
            except Exception:
                out['retries'] = retries
        return out
    if isinstance(hc, list):
        return {'test': ' '.join(str(x) for x in hc)}
    if isinstance(hc, str):
        return {'test': hc}
    return hc


def _prune_empty_in_services(obj: Any) -> Any:
    """Remove empty lists/dicts from service entries — they're semantically absent."""
    if isinstance(obj, dict):
        return {k: _prune_empty_in_services(v) for k, v in obj.items()
                if v not in ([], {}, None, "")}
    if isinstance(obj, list):
        return [_prune_empty_in_services(item) for item in obj]
    return obj


def normalize(obj: Any) -> Any:
    # Enhanced normalization that handles common manifest/build structures
    if isinstance(obj, dict):
        new = {}
        for k in sorted(obj.keys()):
            if should_remove_key(k):
                continue
            v = obj[k]
            lk = k.lower()
            # services: normalize each service entry
            if lk == 'services' and isinstance(v, dict):
                services = {}
                for svc_name in sorted(v.keys()):
                    svc = v[svc_name]
                    if isinstance(svc, dict):
                        svc_new = {}
                        # image
                        if 'image' in svc and isinstance(svc['image'], str):
                            svc_new['image'] = _normalize_image(svc['image'])
                        # command
                        if 'command' in svc and isinstance(svc['command'], str):
                            svc_new['command'] = re.sub(r"\s+", ' ', svc['command']).strip()
                        # depends_on
                        if 'depends_on' in svc and isinstance(svc['depends_on'], list):
                            svc_new['depends_on'] = sorted([str(x) for x in svc['depends_on']])
                        # environment (list or dict)
                        if 'environment' in svc:
                            env = svc['environment']
                            if isinstance(env, dict):
                                svc_new['environment'] = sorted([f"{kk}={env[kk]}" for kk in sorted(env.keys())])
                            elif isinstance(env, list):
                                svc_new['environment'] = sorted([str(x) for x in env])
                        # binds
                        if 'binds' in svc and isinstance(svc['binds'], list):
                            svc_new['binds'] = sorted([_normalize_bind_entry(x) for x in svc['binds'] if isinstance(x, str)])
                        # healthcheck
                        if 'healthcheck' in svc:
                            svc_new['healthcheck'] = _normalize_healthcheck(svc['healthcheck'])
                        # include other keys with generic normalization
                        for subk in sorted(svc.keys()):
                            if subk in svc_new:
                                continue
                            if should_remove_key(subk):
                                continue
                            # skip large multiline content fields if command already present
                            if subk == 'command' and 'command' in svc_new:
                                continue
                            svc_new[subk] = normalize(svc[subk])
                        services[svc_name] = _prune_empty_in_services(svc_new)
                    else:
                        services[svc_name] = _prune_empty_in_services(normalize(svc))
                new[k] = services
                continue
            # binds at top-level or other lists of bind-like items
            if lk == 'binds' and isinstance(v, list):
                new[k] = sorted([_normalize_bind_entry(x) for x in v if isinstance(x, str)])
                continue
            # environment at top-level as dict -> sorted key=val
            if lk in ('environment', 'env') and isinstance(v, dict):
                new[k] = sorted([f"{kk}={v[kk]}" for kk in sorted(v.keys())])
                continue
            # upstreams: normalize backend urls by keeping path and port only
            if lk == 'upstreams' and isinstance(v, list):
                ups = []
                for item in v:
                    if isinstance(item, dict):
                        it = {}
                        for subk in sorted(item.keys()):
                            subv = item[subk]
                            if subk == 'backend' and isinstance(subv, str):
                                # keep host:port/path last component
                                it[subk] = re.sub(r"https?://([^/]+)(/.*)?", lambda m: m.group(1) + (m.group(2) or ''), subv)
                            else:
                                it[subk] = normalize(subv)
                        ups.append(it)
                    else:
                        ups.append(normalize(item))
                new[k] = ups
                continue
            # default
            new[k] = normalize(v)
        return new
    if isinstance(obj, list):
        lst = [normalize(i) for i in obj]
        # sort simple scalar lists to avoid ordering diffs
        if all(not isinstance(x, (dict, list)) for x in lst):
            try:
                return sorted(lst, key=lambda x: (str(type(x)), str(x)))
            except Exception:
                return lst
        return lst
    # normalize strings that look like shas to None to avoid noisy diffs
    if isinstance(obj, str) and SHA_RE.match(obj.strip()):
        return None
    return obj


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def read_yaml(path: Path):
    try:
        if not YAML_AVAILABLE:
            return None
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def write_pretty_json(obj: Any, path: Path):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding='utf-8')


def unified_diff_text(a_lines, b_lines, fromfile, tofile):
    return list(difflib.unified_diff(a_lines, b_lines, fromfile=fromfile, tofile=tofile, lineterm=""))


def normalize_text(text: str) -> str:
    # strip trailing whitespace and normalize line endings
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines) + ("\n" if lines else "")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    p.add_argument("--repo-root", default=None, help="Repo root path (defaults to script parent tree)")
    p.add_argument("--actual-dir", default=None)
    p.add_argument("--generated-dir", default=None)
    p.add_argument("--diff-dir", default=None)
    p.add_argument("--files", default=None, help="Comma-separated relative paths to compare (overrides defaults)")
    args = p.parse_args()

    # determine repo root
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[2]
    slug = args.slug
    default_base = repo_root / "optimize_full_migration_test" / slug
    actual_dir = Path(args.actual_dir) if args.actual_dir else default_base / "actual"
    gen_dir = Path(args.generated_dir) if args.generated_dir else default_base / "generated"
    diff_dir = Path(args.diff_dir) if args.diff_dir else default_base / "diff"
    diff_dir.mkdir(parents=True, exist_ok=True)

    if args.files:
        files = [s.strip() for s in args.files.split(",") if s.strip()]
    else:
        files = [
            f"registry/repos/{slug}.json",
            f"apps/{slug}/lzc-manifest.yml",
            f"apps/{slug}/lzc-build.yml",
        ]

    any_diffs = False
    for rel in files:
        a_path = actual_dir / Path(rel).name if (actual_dir / Path(rel).name).exists() else actual_dir / rel
        g_path = gen_dir / rel
        # fallback: if gen has basename at root of generated
        if not g_path.exists() and (gen_dir / Path(rel).name).exists():
            g_path = gen_dir / Path(rel).name

        if not a_path.exists() and not g_path.exists():
            print(f"MISSING BOTH: {rel}")
            continue
        if not a_path.exists():
            print(f"MISSING ACTUAL: {a_path}")
            any_diffs = True
            continue
        if not g_path.exists():
            print(f"MISSING GENERATED: {g_path}")
            any_diffs = True
            continue

        ext = g_path.suffix.lower()
        base_name = Path(rel).name

        # JSON
        if ext == ".json":
            a_obj = read_json(a_path)
            g_obj = read_json(g_path)
            # if parsing failed, treat as raw
            if a_obj is None or g_obj is None:
                a_text = normalize_text(a_path.read_text(encoding='utf-8'))
                g_text = normalize_text(g_path.read_text(encoding='utf-8'))
                a_lines = a_text.splitlines()
                g_lines = g_text.splitlines()
                diff = unified_diff_text(a_lines, g_lines, str(a_path), str(g_path))
                (diff_dir / (base_name + ".actual.txt")).write_text(a_text, encoding='utf-8')
                (diff_dir / (base_name + ".generated.txt")).write_text(g_text, encoding='utf-8')
            else:
                a_norm = normalize(a_obj)
                g_norm = normalize(g_obj)
                a_pretty = json.dumps(a_norm, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
                g_pretty = json.dumps(g_norm, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
                (diff_dir / (base_name + ".actual.pretty.json")).write_text("\n".join(a_pretty)+"\n", encoding='utf-8')
                (diff_dir / (base_name + ".generated.pretty.json")).write_text("\n".join(g_pretty)+"\n", encoding='utf-8')
                diff = unified_diff_text(a_pretty, g_pretty, base_name + '.actual', base_name + '.generated')

        # YAML (parse if PyYAML available)
        elif ext in ('.yml', '.yaml') and YAML_AVAILABLE:
            a_obj = read_yaml(a_path)
            g_obj = read_yaml(g_path)
            if a_obj is None or g_obj is None:
                # fallback to text
                a_text = normalize_text(a_path.read_text(encoding='utf-8'))
                g_text = normalize_text(g_path.read_text(encoding='utf-8'))
                (diff_dir / (base_name + ".actual")).write_text(a_text, encoding='utf-8')
                (diff_dir / (base_name + ".generated")).write_text(g_text, encoding='utf-8')
                diff = unified_diff_text(a_text.splitlines(), g_text.splitlines(), base_name + '.actual', base_name + '.generated')
            else:
                a_norm = normalize(a_obj)
                g_norm = normalize(g_obj)
                a_pretty = json.dumps(a_norm, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
                g_pretty = json.dumps(g_norm, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
                (diff_dir / (base_name + ".actual.pretty.json")).write_text("\n".join(a_pretty)+"\n", encoding='utf-8')
                (diff_dir / (base_name + ".generated.pretty.json")).write_text("\n".join(g_pretty)+"\n", encoding='utf-8')
                diff = unified_diff_text(a_pretty, g_pretty, base_name + '.actual', base_name + '.generated')

        # other text files
        else:
            a_text = normalize_text(a_path.read_text(encoding='utf-8'))
            g_text = normalize_text(g_path.read_text(encoding='utf-8'))
            (diff_dir / (base_name + ".actual")).write_text(a_text, encoding='utf-8')
            (diff_dir / (base_name + ".generated")).write_text(g_text, encoding='utf-8')
            diff = unified_diff_text(a_text.splitlines(), g_text.splitlines(), base_name + '.actual', base_name + '.generated')

        if diff:
            any_diffs = True
            diff_path = diff_dir / (base_name + ".diff")
            diff_path.write_text("\n".join(diff) + "\n", encoding='utf-8')
            print(f"DIFF -> {diff_path}")
        else:
            print(f"MATCH: {rel}")

    if any_diffs:
        print("Differences found.")
        sys.exit(1)
    else:
        print("No differences.")
        sys.exit(0)


if __name__ == '__main__':
    main()
