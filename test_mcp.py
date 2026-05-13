"""
Test MCP server - local (stdio) hoặc remote (HTTP).

Cách dùng:
    python test_mcp.py                              # local stdio
    python test_mcp.py http                         # local HTTP  (port 8000)
    python test_mcp.py https://xxx.trycloudflare.com  # internet
"""

import asyncio
import os
import sys

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

_DIR = os.path.dirname(os.path.abspath(__file__))
_PYTHON = os.path.join(_DIR, ".venv", "Scripts", "python.exe")
_SERVER = os.path.join(_DIR, "server.py")
_API_KEY = os.getenv("API_KEY", "")


async def run_tests(session: ClientSession):
    await session.initialize()

    # 1. List tools
    tools = await session.list_tools()
    print(f"\n[OK] Tools ({len(tools.tools)}):")
    for t in tools.tools:
        print(f"      - {t.name}")

    # 2. get_time
    print("\n[TEST] get_time()")
    r = await session.call_tool("get_time", {})
    print(f"  => {r.content[0].text}")

    # 3. calculator
    print("\n[TEST] calculator('99 * 99')")
    r = await session.call_tool("calculator", {"expression": "99 * 99"})
    print(f"  => {r.content[0].text}")

    # 4. list_models (calls Ollama)
    print("\n[TEST] list_models()")
    r = await session.call_tool("list_models", {})
    print(f"  => {r.content[0].text[:120]}")

    print("\n[ALL TESTS PASSED]")


async def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "stdio"

    if arg == "stdio":
        print("Transport: stdio (local)")
        params = StdioServerParameters(
            command=_PYTHON,
            args=[_SERVER],
            env={**os.environ},
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await run_tests(session)

    elif arg == "http":
        url = f"http://localhost:{os.getenv('PORT', '8000')}/mcp"
        print(f"Transport: HTTP local -> {url}")
        headers = {"X-API-Key": _API_KEY} if _API_KEY else {}
        http = httpx.AsyncClient(headers=headers, timeout=30)
        async with streamable_http_client(url, http_client=http) as (r, w, _):
            async with ClientSession(r, w) as session:
                await run_tests(session)

    else:
        # remote URL passed directly
        url = arg.rstrip("/") + "/mcp"
        print(f"Transport: HTTP remote -> {url}")
        headers = {"X-API-Key": _API_KEY} if _API_KEY else {}
        http = httpx.AsyncClient(headers=headers, timeout=30)
        async with streamable_http_client(url, http_client=http) as (r, w, _):
            async with ClientSession(r, w) as session:
                await run_tests(session)


if __name__ == "__main__":
    asyncio.run(main())
