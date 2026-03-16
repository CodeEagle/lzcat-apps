#!/usr/bin/env python3

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request


DEFAULT_ENDPOINT = "http://127.0.0.1:3001/mcp"
DEFAULT_URI = "data:text/plain;base64,SGVsbG8sIE1DUCE="


def post_json(url: str, payload: dict, *, timeout: int, insecure: bool) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
        },
    )

    context = None
    if insecure and url.startswith("https://"):
        context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc}") from exc


def assert_ok(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test a local or remote MarkItDown MCP endpoint")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="MCP endpoint URL")
    parser.add_argument("--uri", default=DEFAULT_URI, help="URI passed to convert_to_markdown")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout in seconds")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification for HTTPS endpoints",
    )
    args = parser.parse_args()

    try:
        initialize_result = post_json(
            args.endpoint,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test_mcp_local.py", "version": "1.0"},
                },
            },
            timeout=args.timeout,
            insecure=args.insecure,
        )
        server_info = initialize_result.get("result", {}).get("serverInfo", {})
        assert_ok(bool(server_info.get("name")), "initialize succeeded but serverInfo.name is missing")
        print(f"PASS initialize: {server_info.get('name')} {server_info.get('version', '')}".strip())

        tools_result = post_json(
            args.endpoint,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            timeout=args.timeout,
            insecure=args.insecure,
        )
        tools = tools_result.get("result", {}).get("tools", [])
        tool_names = [tool.get("name") for tool in tools]
        assert_ok("convert_to_markdown" in tool_names, "convert_to_markdown is missing from tools/list")
        print(f"PASS tools/list: {', '.join(tool_names)}")

        call_result = post_json(
            args.endpoint,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "convert_to_markdown",
                    "arguments": {"uri": args.uri},
                },
            },
            timeout=args.timeout,
            insecure=args.insecure,
        )
        content = call_result.get("result", {}).get("content", [])
        first_text = content[0].get("text", "") if content else ""
        is_error = call_result.get("result", {}).get("isError", False)
        assert_ok(not is_error, f"tools/call returned isError=true: {json.dumps(call_result, ensure_ascii=False)}")
        assert_ok(bool(first_text), f"tools/call returned empty content: {json.dumps(call_result, ensure_ascii=False)}")
        preview = first_text.replace("\n", " ")[:120]
        print(f"PASS tools/call: {preview}")
        print("OK MCP test completed")
        return 0
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
