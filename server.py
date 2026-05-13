import os
import re
import math
import datetime
import httpx
import uvicorn
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
API_KEY = os.getenv("API_KEY", "")

mcp = FastMCP("ollama-local")


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
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


if __name__ == "__main__":
    import sys

    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if transport == "http":
        port = int(os.getenv("PORT", "8000"))
        app = mcp.streamable_http_app()
        app.add_middleware(APIKeyMiddleware)
        print(f"Starting MCP HTTP server on port {port}")
        if API_KEY:
            print(f"API key auth enabled")
        else:
            print("WARNING: No API_KEY set — server is open to anyone!")
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
