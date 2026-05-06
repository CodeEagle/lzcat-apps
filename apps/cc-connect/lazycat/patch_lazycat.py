#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def patch_web(root: Path) -> None:
    login = root / "web" / "src" / "pages" / "Login.tsx"
    text = login.read_text(encoding="utf-8")
    old = """  useEffect(() => {
    if (autoLoginAttempted.current) return;
    const qToken = searchParams.get('token');
    if (!qToken) return;
    autoLoginAttempted.current = true;

    (async () => {
      setLoading(true);
      try {
        api.setToken(qToken);
        await getStatus();
        loginStore(qToken);
        navigate('/', { replace: true });
      } catch {
        setToken(qToken);
        setError(t('login.invalidToken'));
        api.setToken('');
      } finally {
        setLoading(false);
      }
    })();
  }, [searchParams, loginStore, navigate, t]);"""
    new = """  useEffect(() => {
    if (autoLoginAttempted.current) return;
    const qToken = searchParams.get('token') || '';
    autoLoginAttempted.current = true;

    (async () => {
      setLoading(true);
      try {
        api.setToken(qToken);
        await getStatus();
        loginStore(qToken);
        navigate('/', { replace: true });
      } catch {
        if (qToken) {
          setToken(qToken);
          setError(t('login.invalidToken'));
        }
        api.setToken('');
      } finally {
        setLoading(false);
      }
    })();
  }, [searchParams, loginStore, navigate, t]);"""
    if old not in text:
        raise SystemExit(f"Login tokenless patch target not found: {login}")
    login.write_text(text.replace(old, new), encoding="utf-8")


def patch_server(root: Path) -> None:
    config_go = root / "config" / "config.go"
    text = config_go.read_text(encoding="utf-8")
    old = """\tif len(c.Projects) == 0 {
\t\treturn fmt.Errorf("config: at least one [[projects]] entry is required")
\t}
"""
    new = """\tif len(c.Projects) == 0 {
\t\tif c.Management.Enabled != nil && *c.Management.Enabled {
\t\t\treturn nil
\t\t}
\t\treturn fmt.Errorf("config: at least one [[projects]] entry is required")
\t}
"""
    if old not in text:
        raise SystemExit(f"management-only config patch target not found: {config_go}")
    config_go.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--server-only", action="store_true")
    args = parser.parse_args()

    if not args.server_only:
        patch_web(args.root)
    if not args.web_only:
        patch_server(args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
