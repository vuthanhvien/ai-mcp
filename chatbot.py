"""
Chatbot agent kết nối với MCP server và dùng Ollama để gọi tools.

Chạy:
    python chatbot.py                        # dùng model mặc định
    python chatbot.py llama3.2               # chỉ định model
    python chatbot.py qwen3-coder:30b

Thêm tools: định nghĩa @mcp.tool() trong server.py, chatbot tự nhận.
"""

import asyncio
import json
import os
import re
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("CHAT_MODEL", "qwen3-coder:30b")

_DIR = os.path.dirname(os.path.abspath(__file__))
_PYTHON = os.path.join(_DIR, ".venv", "Scripts", "python.exe")
_SERVER = os.path.join(_DIR, "server.py")


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks that qwen3/deepseek emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _mcp_to_tool(tool) -> dict:
    raw = dict(tool.inputSchema)
    # Normalize: keep only fields Ollama understands; strip internal MCP fields like "title"
    schema = {
        "type": raw.get("type", "object"),
        "properties": raw.get("properties", {}),
        "required": raw.get("required", []),
    }
    if raw.get("definitions"):
        schema["definitions"] = raw["definitions"]
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "parameters": schema,
        },
    }


async def _call_llm(messages: list, tools: list, model: str) -> dict:
    payload = {"model": model, "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(f"{OLLAMA_BASE_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


async def run(model: str):
    server_params = StdioServerParameters(
        command=_PYTHON,
        args=[_SERVER],
        env={**os.environ, "OLLAMA_HOST": OLLAMA_BASE_URL},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_list = await session.list_tools()
            ollama_tools = [_mcp_to_tool(t) for t in tools_list.tools]

            print(f"\n[Chatbot] Model  : {model}")
            print(f"[Chatbot] Tools  : {', '.join(t.name for t in tools_list.tools)}")
            print("[Chatbot] Gõ 'quit' để thoát.\n")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant. "
                        "Use the available tools whenever they help answer the user accurately. "
                        "Respond in the same language the user uses."
                    ),
                }
            ]

            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nBye!")
                    break

                if not user_input or user_input.lower() in ("quit", "exit", "thoat"):
                    print("Bye!")
                    break

                messages.append({"role": "user", "content": user_input})

                # Agent loop: gọi LLM → nếu có tool_calls thì execute → lặp lại
                while True:
                    msg = await _call_llm(messages, ollama_tools, model)
                    tool_calls = msg.get("tool_calls") or []

                    if not tool_calls:
                        answer = _strip_think(msg.get("content") or "")
                        print(f"\nBot: {answer}\n")
                        messages.append({"role": "assistant", "content": answer})
                        break

                    # Có tool call — thực thi rồi trả kết quả về LLM
                    messages.append(msg)
                    for tc in tool_calls:
                        fn = tc["function"]
                        name = fn["name"]
                        raw_args = fn.get("arguments", "{}")
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                        print(f"  >> tool: {name}({args})")
                        try:
                            result = await session.call_tool(name, args)
                            output = result.content[0].text if result.content else "(no output)"
                        except Exception as ex:
                            output = f"Error calling tool: {ex}"

                        print(f"  << {output[:200]}{'...' if len(output) > 200 else ''}")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id", name),
                                "content": output,
                            }
                        )


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    asyncio.run(run(model))
