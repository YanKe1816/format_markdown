#!/usr/bin/env python3
"""Minimal MCP-compatible Markdown formatting task app."""

import json
import os
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

APP_NAME = "markdown-formatter-app"
APP_VERSION = "1.0.0"
SUPPORT_EMAIL = "sidcraigau@gmail.com"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

PRIVACY_POLICY_TEXT = """Privacy Policy (Effective Date: 2026-03-11, Version: 1.0.1)

This app processes user-submitted text in real time only to format it into clean Markdown.

Data Handling
- Input and output text are processed transiently during the request-response cycle.
- The app does not store user input, output, or conversation content after the response is returned.
- The app does not collect or store personal data.

Tracking and Analytics
- No usage tracking, profiling, cookies, or analytics are used by this app.

Data Sharing
- No user data is shared with third parties.
- No third-party data processors are used for user content.

User Rights and Data Control
- Because data is not stored, there is no retained data to access, export, correct, or delete.
- If you have questions, contact support at sidcraigau@gmail.com.
"""

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "format_markdown",
        "description": "Convert plain text into clean Markdown format.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Plain text to convert into Markdown.",
                }
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
    }
]


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _is_obvious_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(("#", "-", "*", ">")):
        return False
    if stripped.endswith(":") and len(stripped) <= 80:
        return True
    if stripped.isupper() and any(c.isalpha() for c in stripped) and len(stripped) <= 60:
        return True
    return False


def format_markdown_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+$", "", line) for line in normalized.split("\n")]

    collapsed: List[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank:
            if not previous_blank:
                collapsed.append("")
            previous_blank = True
        else:
            collapsed.append(re.sub(r"[ \t]+", " ", line.strip()))
            previous_blank = False

    while collapsed and collapsed[0] == "":
        collapsed.pop(0)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()

    result_lines: List[str] = []
    for line in collapsed:
        if not line:
            result_lines.append("")
            continue
        if _is_obvious_heading(line):
            heading = line.rstrip(":").strip()
            result_lines.append(f"## {heading}")
        else:
            result_lines.append(line)

    return "\n".join(result_lines)


class AppState:
    initialized = False


class Handler(BaseHTTPRequestHandler):
    server_version = "MarkdownFormatterApp/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _read_json(self) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            return None, "Invalid Content-Length"

        payload = self.rfile.read(max(0, length)) if length > 0 else b""
        try:
            obj = json.loads(payload.decode("utf-8") if payload else "{}")
        except json.JSONDecodeError:
            return None, "Invalid JSON"

        if not isinstance(obj, dict):
            return None, "JSON body must be an object"
        return obj, None

    def do_GET(self) -> None:
        if self.path == "/health":
            _json_response(self, 200, {"status": "ok"})
            return
        if self.path == "/privacy":
            _text_response(self, 200, PRIVACY_POLICY_TEXT)
            return
        if self.path == "/terms":
            _text_response(self, 200, "Terms: provided as-is for formatting plain text into Markdown.")
            return
        if self.path == "/support":
            _text_response(self, 200, f"Support: {SUPPORT_EMAIL}")
            return
        if self.path == "/.well-known/openai-apps-challenge":
            token = os.environ.get("OPENAI_APPS_CHALLENGE", "IGizQCjOv5DUxm959jRx3m2IzZJtjoTkFULoCAaqLYI")
            _text_response(self, 200, token, content_type="text/plain")
            return
        if self.path == "/mcp":
            _json_response(
                self,
                200,
                {
                    "name": APP_NAME,
                    "version": APP_VERSION,
                    "tools": TOOL_DEFINITIONS,
                },
            )
            return

        _json_response(self, 404, {"error": "not_found"})

    def _jsonrpc_error(self, request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _jsonrpc_result(self, request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def do_POST(self) -> None:
        if self.path != "/mcp":
            _json_response(self, 404, {"error": "not_found"})
            return

        body, err = self._read_json()
        if err:
            _json_response(self, 400, self._jsonrpc_error(None, -32700, err))
            return

        request_id = body.get("id")
        method = body.get("method")
        params = body.get("params", {})

        if body.get("jsonrpc") != "2.0" or not isinstance(method, str):
            _json_response(self, 400, self._jsonrpc_error(request_id, -32600, "Invalid Request"))
            return

        response: Optional[Dict[str, Any]] = None

        if method == "initialize":
            if not isinstance(params, dict):
                response = self._jsonrpc_error(request_id, -32602, "Invalid params")
            else:
                protocol_version = params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION
                response = self._jsonrpc_result(
                    request_id,
                    {
                        "protocolVersion": protocol_version,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": APP_NAME, "version": APP_VERSION},
                    },
                )
        elif method == "notifications/initialized":
            AppState.initialized = True
            if request_id is not None:
                response = self._jsonrpc_result(request_id, {})
        elif method == "tools/list":
            if not AppState.initialized:
                response = self._jsonrpc_error(request_id, -32000, "Server not initialized")
            else:
                response = self._jsonrpc_result(request_id, {"tools": TOOL_DEFINITIONS})
        elif method == "tools/call":
            if not AppState.initialized:
                response = self._jsonrpc_error(request_id, -32000, "Server not initialized")
            elif not isinstance(params, dict):
                response = self._jsonrpc_error(request_id, -32602, "Invalid params")
            else:
                name = params.get("name")
                arguments = params.get("arguments", {})
                if name != "format_markdown":
                    response = self._jsonrpc_error(request_id, -32601, "Tool not found")
                elif not isinstance(arguments, dict):
                    response = self._jsonrpc_error(request_id, -32602, "Invalid arguments")
                elif set(arguments.keys()) != {"text"} or not isinstance(arguments.get("text"), str):
                    response = self._jsonrpc_error(request_id, -32602, "arguments must contain only string field 'text'")
                else:
                    markdown_text = format_markdown_text(arguments["text"])
                    response = self._jsonrpc_result(
                        request_id,
                        {
                            "content": [{"type": "text", "text": "Markdown formatting completed."}],
                            "structuredContent": {"markdown_text": markdown_text},
                        },
                    )
        else:
            response = self._jsonrpc_error(request_id, -32601, "Method not found")

        if response is None:
            self.send_response(204)
            self.end_headers()
        else:
            _json_response(self, 200, response)


def run_server(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    listen_port = int(os.environ.get("PORT", "8000")) if port is None else int(port)
    httpd = ThreadingHTTPServer((host, listen_port), Handler)
    print(f"Serving on {host}:{listen_port}")
    httpd.serve_forever()


def _post_json(url: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw else {})


def run_self_test() -> None:
    AppState.initialized = False
    test_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = test_server.server_address[1]
    thread = threading.Thread(target=test_server.serve_forever, daemon=True)
    thread.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            assert resp.status == 200 and health == {"status": "ok"}, "Health check failed"

        status, init_resp = _post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "self-test", "version": "1.0"},
                },
            },
        )
        result = init_resp.get("result", {})
        assert status == 200, "Initialize status failed"
        assert isinstance(result.get("protocolVersion"), str), "protocolVersion missing"
        assert result.get("serverInfo", {}).get("name"), "serverInfo.name missing"
        assert result.get("serverInfo", {}).get("version"), "serverInfo.version missing"

        _post_json(
            f"http://127.0.0.1:{port}/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        )

        _, tools_list_resp = _post_json(
            f"http://127.0.0.1:{port}/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tools = tools_list_resp.get("result", {}).get("tools", [])
        assert len(tools) == 1 and tools[0].get("name") == "format_markdown", "tools/list failed"

        _, call_resp = _post_json(
            f"http://127.0.0.1:{port}/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "format_markdown",
                    "arguments": {"text": "TITLE:\n\nthis   is   text."},
                },
            },
        )
        call_result = call_resp.get("result", {})
        assert isinstance(call_result.get("content"), list), "content array missing"
        assert isinstance(call_result.get("structuredContent", {}).get("markdown_text"), str), (
            "structuredContent.markdown_text missing"
        )

        with open(__file__, "r", encoding="utf-8") as f:
            source = f.read()
        assert "0.0.0.0" in source, "Source missing 0.0.0.0"
        assert 'os.environ.get("PORT"' in source, "Source missing PORT env usage"

        print("SELF-TEST PASS")
    finally:
        test_server.shutdown()
        test_server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_test()
    else:
        run_server()
