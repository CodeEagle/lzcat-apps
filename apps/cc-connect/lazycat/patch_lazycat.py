#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    patch_terminal_web(root)


def patch_terminal_web(root: Path) -> None:
    package_json = root / "web" / "package.json"
    package = json.loads(package_json.read_text(encoding="utf-8"))
    package.setdefault("dependencies", {})["@xterm/xterm"] = "^5.5.0"
    package_json.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    terminal_dir = root / "web" / "src" / "pages" / "Terminal"
    terminal_dir.mkdir(parents=True, exist_ok=True)
    (terminal_dir / "Terminal.tsx").write_text(TERMINAL_TSX, encoding="utf-8")

    app = root / "web" / "src" / "App.tsx"
    text = app.read_text(encoding="utf-8")
    text = text.replace(
        "import SkillList from '@/pages/Skills/SkillList';\n",
        "import SkillList from '@/pages/Skills/SkillList';\nimport TerminalPage from '@/pages/Terminal/Terminal';\n",
    )
    text = text.replace(
        '        <Route path="system" element={<SystemConfig />} />\n',
        '        <Route path="terminal" element={<TerminalPage />} />\n        <Route path="system" element={<SystemConfig />} />\n',
    )
    app.write_text(text, encoding="utf-8")

    sidebar = root / "web" / "src" / "components" / "Layout" / "Sidebar.tsx"
    text = sidebar.read_text(encoding="utf-8")
    text = text.replace(
        "  Puzzle,\n} from 'lucide-react';",
        "  Puzzle,\n  Terminal,\n} from 'lucide-react';",
    )
    text = text.replace(
        "  { key: 'cron', path: '/cron', icon: Clock },\n  { key: 'system', path: '/system', icon: Settings },",
        "  { key: 'cron', path: '/cron', icon: Clock },\n  { key: 'terminal', path: '/terminal', icon: Terminal },\n  { key: 'system', path: '/system', icon: Settings },",
    )
    sidebar.write_text(text, encoding="utf-8")

    labels = {
        "en": "Terminal",
        "zh": "终端",
        "zh-TW": "終端",
        "ja": "ターミナル",
        "es": "Terminal",
    }
    for locale, label in labels.items():
        path = root / "web" / "src" / "i18n" / "locales" / f"{locale}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.setdefault("nav", {})["terminal"] = label
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    patch_feishu_project_creation_result(root)
    patch_management_platform_fail_open(root)
    patch_terminal_server(root)


def patch_feishu_project_creation_result(root: Path) -> None:
    config_go = root / "config" / "config.go"
    text = config_go.read_text(encoding="utf-8")
    old = """\treturn &EnsureProjectWithFeishuResult{
\t\tCreated:          true,
\t\tAddedPlatform:    false,
\t\tProjectIndex:     len(cfg.Projects) - 1,
\t\tPlatformAbsIndex: len(cfg.Projects[len(cfg.Projects)-1].Platforms) - 1,
\t\tPlatformType:     platformType,
\t}, nil
"""
    new = """\treturn &EnsureProjectWithFeishuResult{
\t\tCreated:          true,
\t\tAddedPlatform:    false,
\t\tProjectIndex:     len(cfg.Projects),
\t\tPlatformAbsIndex: 0,
\t\tPlatformType:     platformType,
\t}, nil
"""
    if old not in text:
        raise SystemExit(f"feishu project creation result patch target not found: {config_go}")
    config_go.write_text(text.replace(old, new), encoding="utf-8")


def patch_management_platform_fail_open(root: Path) -> None:
    main_go = root / "cmd" / "cc-connect" / "main.go"
    text = main_go.read_text(encoding="utf-8")
    old = """\t\t\tp, err := core.CreatePlatform(pc.Type, opts)
\t\t\tif err != nil {
\t\t\t\tslog.Error("failed to create platform", "project", proj.Name, "type", pc.Type, "error", err)
\t\t\t\tos.Exit(1)
\t\t\t}
\t\t\tplatforms = append(platforms, p)
"""
    new = """\t\t\tp, err := core.CreatePlatform(pc.Type, opts)
\t\t\tif err != nil {
\t\t\t\tif cfg.Management.Enabled != nil && *cfg.Management.Enabled {
\t\t\t\t\tslog.Warn("skipping platform with invalid configuration", "project", proj.Name, "type", pc.Type, "error", err)
\t\t\t\t\tcontinue
\t\t\t\t}
\t\t\t\tslog.Error("failed to create platform", "project", proj.Name, "type", pc.Type, "error", err)
\t\t\t\tos.Exit(1)
\t\t\t}
\t\t\tplatforms = append(platforms, p)
"""
    if old not in text:
        raise SystemExit(f"management platform fail-open patch target not found: {main_go}")
    main_go.write_text(text.replace(old, new), encoding="utf-8")


def patch_terminal_server(root: Path) -> None:
    terminal_go = root / "core" / "terminal_lazycat.go"
    terminal_go.write_text(TERMINAL_GO, encoding="utf-8")

    management_go = root / "core" / "management.go"
    text = management_go.read_text(encoding="utf-8")
    old = """\t// Bridge
\tmux.HandleFunc(prefix+\"/bridge/adapters\", m.wrap(m.handleBridgeAdapters))
"""
    new = """\t// Terminal
\tmux.HandleFunc(prefix+\"/terminal/ws\", m.wrap(m.handleTerminalWS))

\t// Bridge
\tmux.HandleFunc(prefix+\"/bridge/adapters\", m.wrap(m.handleBridgeAdapters))
"""
    if old not in text:
        raise SystemExit(f"terminal route patch target not found: {management_go}")
    management_go.write_text(text.replace(old, new), encoding="utf-8")


TERMINAL_GO = r'''package core

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"github.com/creack/pty"
	"github.com/gorilla/websocket"
)

type terminalWSMessage struct {
	Type string `json:"type"`
	Data string `json:"data,omitempty"`
	Cols uint16 `json:"cols,omitempty"`
	Rows uint16 `json:"rows,omitempty"`
}

var terminalWSUpgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool { return true },
}

func (m *ManagementServer) handleTerminalWS(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		mgmtError(w, http.StatusMethodNotAllowed, "GET only")
		return
	}

	conn, err := terminalWSUpgrader.Upgrade(w, r, nil)
	if err != nil {
		slog.Warn("terminal: websocket upgrade failed", "error", err)
		return
	}
	defer conn.Close()

	cwd := strings.TrimSpace(r.URL.Query().Get("cwd"))
	if cwd == "" {
		cwd = "/data/workspaces"
	}
	if info, err := os.Stat(cwd); err != nil || !info.IsDir() {
		cwd = "/"
	}

	shell := strings.TrimSpace(os.Getenv("SHELL"))
	if shell == "" {
		shell = "/bin/bash"
	}
	if _, err := os.Stat(shell); err != nil {
		shell = "/bin/sh"
	}

	cols := parseTerminalSize(r.URL.Query().Get("cols"), 120, 20, 400)
	rows := parseTerminalSize(r.URL.Query().Get("rows"), 32, 8, 120)

	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()

	cmd := exec.CommandContext(ctx, shell, "-l")
	cmd.Dir = cwd
	cmd.Env = append(os.Environ(),
		"TERM=xterm-256color",
		"COLORTERM=truecolor",
	)

	ptmx, err := pty.StartWithSize(cmd, &pty.Winsize{Rows: rows, Cols: cols})
	if err != nil {
		_ = conn.WriteJSON(terminalWSMessage{Type: "error", Data: err.Error()})
		return
	}
	defer ptmx.Close()

	done := make(chan struct{})
	go func() {
		defer close(done)
		buf := make([]byte, 8192)
		for {
			n, err := ptmx.Read(buf)
			if n > 0 {
				_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
				if writeErr := conn.WriteJSON(terminalWSMessage{Type: "output", Data: string(buf[:n])}); writeErr != nil {
					return
				}
			}
			if err != nil {
				return
			}
		}
	}()

	for {
		var msg terminalWSMessage
		if err := conn.ReadJSON(&msg); err != nil {
			break
		}
		switch msg.Type {
		case "input":
			if msg.Data != "" {
				_, _ = ptmx.Write([]byte(msg.Data))
			}
		case "resize":
			cols := clampTerminalSize(msg.Cols, 20, 400)
			rows := clampTerminalSize(msg.Rows, 8, 120)
			if cols > 0 && rows > 0 {
				_ = pty.Setsize(ptmx, &pty.Winsize{Rows: rows, Cols: cols})
			}
		}
	}

	cancel()
	if cmd.Process != nil {
		_ = cmd.Process.Signal(os.Interrupt)
		select {
		case <-done:
		case <-time.After(750 * time.Millisecond):
			_ = cmd.Process.Kill()
		}
	}
	_ = cmd.Wait()
}

func parseTerminalSize(raw string, fallback, min, max uint16) uint16 {
	value, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil {
		return fallback
	}
	return clampTerminalSize(uint16(value), min, max)
}

func clampTerminalSize(value, min, max uint16) uint16 {
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}
'''


TERMINAL_TSX = r'''import { useCallback, useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { Play, PlugZap, RotateCcw, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui';
import api from '@/api/client';
import { cn } from '@/lib/utils';

const loginCommands = [
  { label: 'Claude Code', command: 'claude login' },
  { label: 'Codex', command: 'codex login' },
  { label: 'Gemini', command: 'gemini' },
  { label: 'iFlow', command: 'iflow login' },
  { label: 'OpenCode', command: 'opencode auth login' },
  { label: 'Kimi', command: 'kimi login' },
  { label: 'Qoder', command: 'qodercli login' },
];

function terminalUrl(cols: number, rows: number) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const params = new URLSearchParams({
    cols: String(cols),
    rows: String(rows),
  });
  const token = api.getToken();
  if (token) params.set('token', token);
  return `${protocol}//${window.location.host}/api/v1/terminal/ws?${params.toString()}`;
}

export default function TerminalPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<XTerm | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState('Disconnected');

  const resizeTerminal = useCallback(() => {
    const term = termRef.current;
    const container = containerRef.current;
    if (!term || !container) return { cols: 120, rows: 32 };

    const rect = container.getBoundingClientRect();
    const cols = Math.max(40, Math.floor(rect.width / 9));
    const rows = Math.max(12, Math.floor(rect.height / 18));
    term.resize(cols, rows);

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'resize', cols, rows }));
    }
    return { cols, rows };
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
    setStatus('Disconnected');
  }, []);

  const connect = useCallback(() => {
    const term = termRef.current;
    if (!term) return;

    disconnect();
    term.clear();
    const size = resizeTerminal();
    const ws = new WebSocket(terminalUrl(size.cols, size.rows));
    wsRef.current = ws;
    setStatus('Connecting...');

    ws.onopen = () => {
      setConnected(true);
      setStatus('Connected');
      term.focus();
    };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'output') term.write(payload.data || '');
        if (payload.type === 'error') term.writeln(`\r\n[terminal error] ${payload.data || 'unknown error'}`);
      } catch {
        term.write(String(event.data));
      }
    };
    ws.onclose = () => {
      setConnected(false);
      setStatus('Disconnected');
    };
    ws.onerror = () => {
      setConnected(false);
      setStatus('Connection error');
    };
  }, [disconnect, resizeTerminal]);

  useEffect(() => {
    const term = new XTerm({
      cursorBlink: true,
      convertEol: true,
      fontFamily: 'JetBrains Mono, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      lineHeight: 1.25,
      theme: {
        background: '#05070a',
        foreground: '#d8dee9',
        cursor: '#42ff9c',
        selectionBackground: '#284b3c',
      },
    });
    termRef.current = term;
    if (containerRef.current) term.open(containerRef.current);

    const dataDisposable = term.onData((data) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'input', data }));
      }
    });

    const resizeObserver = new ResizeObserver(() => resizeTerminal());
    if (containerRef.current) resizeObserver.observe(containerRef.current);

    connect();

    return () => {
      dataDisposable.dispose();
      resizeObserver.disconnect();
      wsRef.current?.close();
      term.dispose();
      termRef.current = null;
    };
  }, [connect, resizeTerminal]);

  const sendCommand = (command: string) => {
    const term = termRef.current;
    const ws = wsRef.current;
    if (!term || ws?.readyState !== WebSocket.OPEN) return;
    const text = `${command}\r`;
    ws.send(JSON.stringify({ type: 'input', data: text }));
    term.focus();
  };

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col overflow-hidden bg-gray-50 dark:bg-black">
      <div
        className={cn(
          'flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b',
          'border-gray-200/80 dark:border-white/[0.08] bg-white/80 dark:bg-black/80',
        )}
      >
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-gray-950 dark:text-white">Terminal</h1>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Full shell inside the cc-connect container · {status}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={connect}>
            <PlugZap size={14} />
            Connect
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => termRef.current?.clear()}>
            <Trash2 size={14} />
            Clear
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={disconnect}>
            <RotateCcw size={14} />
            Disconnect
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 px-4 py-3 border-b border-gray-200/80 dark:border-white/[0.08] bg-white/65 dark:bg-black/70">
        {loginCommands.map((item) => (
          <Button
            key={item.label}
            type="button"
            variant={connected ? 'secondary' : 'ghost'}
            size="sm"
            disabled={!connected}
            onClick={() => sendCommand(item.command)}
          >
            <Play size={13} />
            {item.label}
          </Button>
        ))}
      </div>

      <div className="flex-1 min-h-0 p-3">
        <div
          ref={containerRef}
          className={cn(
            'h-full w-full overflow-hidden rounded-lg border p-2',
            'bg-[#05070a] border-gray-200/80 dark:border-white/[0.08]',
          )}
        />
      </div>
    </div>
  );
}
'''


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
