# Web App Integration Guide

This server exposes two public surfaces:

- MCP endpoint: `/mcp`
- Simple chatbot REST API for web apps: `/api/chat`

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
const MCP_BASE_URL = process.env.MCP_BASE_URL;
const MCP_API_KEY = process.env.MCP_API_KEY;

export async function askDataEntryBot(message, history = []) {
  const res = await fetch(`${MCP_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": MCP_API_KEY,
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

  return res.json();
}
```

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

Start quick tunnel again:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
```
