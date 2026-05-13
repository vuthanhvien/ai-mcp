# Web App Integration Guide

This server exposes two public surfaces:

- MCP endpoint: `/mcp`
- Simple chatbot REST API for web apps: `/api/chat`

## Local Agent Direction

The main flow is:

```text
Your web app/chat UI
  -> this Local Agent API (/api/chat/stream)
  -> local Ollama model
  -> local tool functions in server.py
  -> your business APIs, database, files, etc.
```

This means your chatbot app does not need to call Claude/OpenAI for tool use.
Claude/Codex/MCP clients are optional. The cheap/default path is your app calling
this server, while Ollama local decides when to call tools.

## Current Public URL

Quick Cloudflare Tunnel:

```text
https://saving-alphabetical-accessed-substitute.trycloudflare.com
```

This URL is temporary. It changes when the quick tunnel restarts.

Open the chatbot UI directly at the same URL:

```text
https://saving-alphabetical-accessed-substitute.trycloudflare.com/
```

The UI is public, but `/api/*` and `/mcp` still require `X-API-Key`.

## Auth

Every public request must include the API key from `.env`:

```http
X-API-Key: your-api-key
```

For production, do not put this key in browser JavaScript. Put it in your web app backend and let the frontend call your backend.

## Chat API

Request:

```http
POST /api/chat
Content-Type: application/json
X-API-Key: your-api-key
```

Body:

```json
{
  "message": "Tao don hang cho Nguyen Van A, so luong 12",
  "system": "You are a Vietnamese data-entry assistant. Ask for missing required fields before finalizing."
}
```

Response:

```json
{
  "answer": "Bot reply",
  "model": "qwen3-coder:30b",
  "tool_calls": []
}
```

## Streaming Chat API

The UI uses the streaming endpoint:

```http
POST /api/chat/stream
Content-Type: application/json
X-API-Key: your-api-key
```

It returns newline-delimited JSON events:

```json
{"type":"status","message":"thinking"}
{"type":"tool_call","name":"calculator","arguments":{"expression":"8*7"}}
{"type":"tool_result","name":"calculator","arguments":{"expression":"8*7"},"output":"56"}
{"type":"delta","text":"8"}
{"type":"delta","text":" x 7 = 56"}
{"type":"done","answer":"8 x 7 = 56","model":"qwen3-coder:30b"}
```

For conversation history, send `messages` instead of `message`:

```json
{
  "messages": [
    { "role": "user", "content": "Tao phieu nhap kho" },
    { "role": "assistant", "content": "Ban nhap mat hang nao?" },
    { "role": "user", "content": "Ban phim co 50 cai" }
  ]
}
```

## JavaScript Backend Example

```js
const LOCAL_AGENT_BASE_URL = process.env.LOCAL_AGENT_BASE_URL;
const LOCAL_AGENT_API_KEY = process.env.LOCAL_AGENT_API_KEY;

export async function askDataEntryBot(message, history = []) {
  const res = await fetch(`${LOCAL_AGENT_BASE_URL}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": LOCAL_AGENT_API_KEY,
    },
    body: JSON.stringify({
      messages: [...history, { role: "user", content: message }],
      system:
        "You are a Vietnamese data-entry assistant. Extract structured data, ask for missing fields, and use tools when useful.",
    }),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  return res.body;
}
```

## Add Your Own Tool Example

### Option A: Send Dynamic Tools Per Request

Your other chatbot can send a tool list directly to this Local Agent. The agent
will expose those tools to Ollama, let Ollama choose, then call the configured
HTTP API.

```json
{
  "messages": [
    { "role": "user", "content": "Tao email voi title la Title" }
  ],
  "system": "Neu user muon tao email, hay dung create_mail.",
  "dynamic_tools": [
    {
      "name": "create_mail",
      "description": "Create an email draft in my app.",
      "method": "POST",
      "url": "https://your-app.example.com/mails",
      "headers": {
        "Authorization": "Bearer YOUR_APP_API_KEY"
      },
      "parameters": {
        "type": "object",
        "properties": {
          "title": { "type": "string", "description": "Email title" },
          "body": { "type": "string", "description": "Email body" },
          "to": { "type": "string", "description": "Recipient email" }
        },
        "required": ["title"]
      }
    }
  ]
}
```

Dynamic tool behavior:

- `POST`, `PUT`, `PATCH`: tool arguments are sent as JSON body.
- `GET`, `DELETE`: tool arguments are sent as query params.
- The request still requires `X-API-Key` for this Local Agent.
- Only send dynamic tools from trusted backends, because the agent will call the URLs you provide.

### Option B: Hardcode A Stable Tool

Example goal:

```text
User: Tao email voi title la Title
```

You add a local tool in `server.py`. Ollama will decide to call it, and the tool
will call your own API:

```python
@mcp.tool()
async def create_mail(title: str, body: str = "", to: str = "") -> str:
    """Create an email draft in my app."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://your-app.example.com/mails",
            headers={"Authorization": "Bearer YOUR_APP_API_KEY"},
            json={"title": title, "body": body, "to": to},
        )
        resp.raise_for_status()
        return resp.text
```

Then register it in two places:

```python
TOOL_FUNCTIONS["create_mail"] = create_mail
```

and add an `OLLAMA_TOOL_SPECS` entry:

```python
{
    "type": "function",
    "function": {
        "name": "create_mail",
        "description": "Create an email draft in the user's mail app.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "to": {"type": "string"}
            },
            "required": ["title"]
        }
    }
}
```

After restart, `/api/tools` will show `create_mail`, and `/api/chat/stream`
can call it automatically.

## Frontend Example

Call your own backend, not the tunnel directly:

```js
const res = await fetch("/api/assistant", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ message: inputText, history }),
});

const data = await res.json();
console.log(data.answer);
```

## Available Tool List

```http
GET /api/tools
X-API-Key: your-api-key
```

The current REST tool set includes:

- `get_time`
- `calculator`
- `read_file`
- `write_file`

The MCP endpoint still exposes the fuller MCP tool list.

## Run And Stop

Server process currently running on port `8000`.

Stop local server:

```powershell
Stop-Process -Id 17728
```

Stop latest quick tunnel:

```powershell
Stop-Process -Id 24904
```

Start server again:

```powershell
.\.venv\Scripts\python.exe server.py http
```

Or use the Bash/Git Bash helper:

```bash
./start_http.sh
```

Start quick tunnel again:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
```
