# Print interpreter for sanity (should be your .venv python)
import sys
print("[mcp_server] sys.executable =", sys.executable, flush=True)

# IMPORTANT: set Windows loop policy early (before imports that use asyncio)
import asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiohttp
import yaml
from mcp.server.fastmcp import FastMCP  # <-- use FastMCP bundled with 'mcp' package

# Load REST host/port from config
with open("app/config/settings.yaml", "r") as f:
    cfg = yaml.safe_load(f)

REST_HOST = cfg["servers"]["rest_host"]
REST_PORT = cfg["servers"]["rest_port"]

mcp = FastMCP("math-api-server")

@mcp.tool()
async def add_numbers(a: float, b: float) -> float:
    """Add two numbers using the REST API."""
    async with aiohttp.ClientSession() as session:
        async with session.post(f"http://{REST_HOST}:{REST_PORT}/add", json={"a": a, "b": b}) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return float(data.get("result", 0.0))

@mcp.tool()
async def say_hello() -> str:
    """Say hello using the REST API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{REST_HOST}:{REST_PORT}/hello") as resp:
            resp.raise_for_status()
            data = await resp.json()
            return str(data.get("message", ""))

if __name__ == "__main__":
    mcp.run()