# markdown-formatter-app

Minimal OpenAI MCP-compatible task app that converts plain text into clean Markdown format.

## Deploy on Render

- **Runtime**: Python 3
- **Build Command**: *(empty / no-op)*
- **Start Command**: `python server.py`

The server binds to `0.0.0.0` and listens on `PORT` (default `8000`).

## Health Check

```bash
curl -sS http://localhost:8000/health
```

## Public Routes

- `GET /health` -> `{"status":"ok"}`
- `GET /privacy`
- `GET /terms`
- `GET /support`
- `GET /.well-known/openai-apps-challenge` -> `IGizQCjOv5DUxm959jRx3m2lzZJtjofTkFULoCAaqLYI`

## MCP Endpoint

All JSON-RPC MCP traffic is on `POST /mcp`.

### initialize

```bash
curl -sS -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"initialize",
    "params":{
      "protocolVersion":"2024-11-05",
      "capabilities":{},
      "clientInfo":{"name":"curl","version":"1.0"}
    }
  }'
```

### notifications/initialized

```bash
curl -sS -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
```

### tools/list

```bash
curl -sS -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### tools/call

```bash
curl -sS -X POST http://localhost:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{
      "name":"format_markdown",
      "arguments":{"text":"TITLE:\n\nthis   is    text."}
    }
  }'
```

## Local Self-Test

```bash
python server.py --self-test
```

This runs built-in gates for health, initialize, tools/list, tools/call, and static source assertions.
