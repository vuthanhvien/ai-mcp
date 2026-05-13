import os
import re
import math
import datetime
import inspect
import json
import httpx
import uvicorn
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP


def load_env_file(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs without requiring python-dotenv."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
API_KEY = os.getenv("API_KEY", "")
DEFAULT_MODEL = os.getenv("CHAT_MODEL", "qwen3-coder:30b")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

mcp = FastMCP("ollama-local")


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        if not API_KEY:
            return await call_next(request)
        provided = request.headers.get("X-API-Key") or request.headers.get(
            "Authorization", ""
        ).removeprefix("Bearer ")
        if provided != API_KEY:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


@mcp.tool()
async def list_models() -> list[str]:
    """List all Ollama models installed on this machine."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]


@mcp.tool()
async def chat(model: str, prompt: str, system: str = "") -> str:
    """
    Send a chat message to a local Ollama model and get a response.

    Args:
        model: Model name, e.g. 'llama3.2', 'mistral', 'qwen2.5-coder'
        prompt: The user message / question
        system: Optional system prompt to set model behavior
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["message"]["content"]


@mcp.tool()
async def generate(model: str, prompt: str) -> str:
    """
    Run a raw text generation prompt against a local Ollama model.

    Args:
        model: Model name, e.g. 'llama3.2', 'codellama'
        prompt: The raw prompt text
    """
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["response"]


@mcp.tool()
async def pull_model(model: str) -> str:
    """
    Download / pull an Ollama model from the registry.

    Args:
        model: Model name to pull, e.g. 'llama3.2', 'phi4-mini'
    """
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/pull",
            json={"model": model, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status", "done")


# ---------------------------------------------------------------------------
# Custom tools — thêm tools của bạn ở đây
# ---------------------------------------------------------------------------

@mcp.tool()
def get_time() -> str:
    """Return the current local date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def calculator(expression: str) -> str:
    """
    Evaluate a safe math expression and return the result.

    Args:
        expression: Math expression, e.g. '2 + 2', 'sqrt(16)', '10 * (3 + 4)'
    """
    allowed = re.compile(r"^[\d\s\+\-\*\/\(\)\.\,\%\^]+$")
    safe_expr = expression.replace("^", "**")
    if not allowed.match(safe_expr.replace("sqrt", "").replace("pi", "").replace("e", "")):
        return "Error: expression contains disallowed characters"
    try:
        result = eval(safe_expr, {"__builtins__": {}}, {"sqrt": math.sqrt, "pi": math.pi, "e": math.e})
        return str(result)
    except Exception as ex:
        return f"Error: {ex}"


@mcp.tool()
def read_file(path: str) -> str:
    """
    Read the contents of a local text file.

    Args:
        path: Absolute or relative file path
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as ex:
        return f"Error: {ex}"


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Write text content to a local file (creates or overwrites).

    Args:
        path: Absolute or relative file path
        content: Text content to write
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}"
    except Exception as ex:
        return f"Error: {ex}"


TOOL_FUNCTIONS = {
    "list_models": list_models,
    "chat": chat,
    "generate": generate,
    "pull_model": pull_model,
    "get_time": get_time,
    "calculator": calculator,
    "read_file": read_file,
    "write_file": write_file,
}

OLLAMA_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Return the current local date and time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a safe math expression and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '2 + 2' or 'sqrt(16)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a local text file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a local file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
]


async def invoke_tool(name: str, args: dict) -> str:
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return f"Error: unknown tool '{name}'"
    try:
        result = func(**args)
        if inspect.isawaitable(result):
            result = await result
        return str(result)
    except Exception as ex:
        return f"Error: {ex}"


async def ollama_chat(messages: list[dict], model: str, tools: list[dict]) -> dict:
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


async def api_tools(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "tools": [spec["function"] for spec in OLLAMA_TOOL_SPECS],
            "mcp_tools": list(TOOL_FUNCTIONS.keys()),
        }
    )


async def api_chat(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    model = body.get("model") or DEFAULT_MODEL
    message = body.get("message")
    messages = body.get("messages")
    system = body.get(
        "system",
        (
            "You are a helpful data-entry assistant. "
            "Ask concise follow-up questions when required fields are missing. "
            "Use tools when they help. Reply in the user's language."
        ),
    )
    max_tool_rounds = int(body.get("max_tool_rounds", 4))
    enable_tools = body.get("tools", True)

    if messages is None:
        if not message:
            return JSONResponse(
                {"error": "Provide either 'message' or 'messages'."}, status_code=400
            )
        messages = [{"role": "user", "content": str(message)}]

    conversation = [{"role": "system", "content": system}, *messages]
    available_tools = OLLAMA_TOOL_SPECS if enable_tools else []
    tool_trace = []

    try:
        for _ in range(max_tool_rounds + 1):
            msg = await ollama_chat(conversation, model, available_tools)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return JSONResponse(
                    {
                        "answer": msg.get("content") or "",
                        "model": model,
                        "tool_calls": tool_trace,
                    }
                )

            conversation.append(msg)
            for call in tool_calls:
                fn = call["function"]
                raw_args = fn.get("arguments", "{}")
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                output = await invoke_tool(fn["name"], args or {})
                tool_trace.append({"name": fn["name"], "arguments": args, "output": output})
                conversation.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", fn["name"]),
                        "content": output,
                    }
                )
        return JSONResponse({"error": "Too many tool rounds"}, status_code=400)
    except httpx.HTTPStatusError as ex:
        return JSONResponse(
            {"error": "Ollama request failed", "detail": ex.response.text},
            status_code=502,
        )
    except Exception as ex:
        return JSONResponse({"error": str(ex)}, status_code=500)


if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "http":
        port = int(os.getenv("PORT", "8000"))
        app = mcp.streamable_http_app()
        app.add_route("/api/tools", api_tools, methods=["GET", "OPTIONS"])
        app.add_route("/api/chat", api_chat, methods=["POST", "OPTIONS"])
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        )
        app.add_middleware(APIKeyMiddleware)
        print(f"Starting MCP HTTP server on port {port}")
        if API_KEY:
            print(f"API key auth enabled")
        else:
            print("WARNING: No API_KEY set — server is open to anyone!")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
