import asyncio, inspect
import aiohttp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn, yaml

# Windows selector loop (compat)
import sys, asyncio as _asyncio
if sys.platform.startswith("win"):
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

with open("app/config/settings.yaml", "r") as f:
    cfg = yaml.safe_load(f)

REST_HOST = cfg["servers"]["rest_host"]
REST_PORT = cfg["servers"]["rest_port"]
HTTP_HOST = cfg["servers"]["mcp_http_host"]
HTTP_PORT = cfg["servers"]["mcp_http_port"]

# Minimal tool registry for HTTP exposure
registered_tools = {}

def register_tool(func):
    registered_tools[func.__name__] = func
    return func

@register_tool
async def add_numbers(a: float, b: float) -> float:
    async with aiohttp.ClientSession() as session:
        async with session.post(f"http://{REST_HOST}:{REST_PORT}/add", json={"a": a, "b": b}) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return float(data["result"])

@register_tool
async def say_hello() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://{REST_HOST}:{REST_PORT}/hello") as resp:
            resp.raise_for_status()
            data = await resp.json()
            return str(data.get("message", ""))

app = FastAPI(title="MCP HTTP wrapper (calls REST API)")

class ToolCallRequest(BaseModel):
    name: str
    args: dict = {}

@app.get("/tools")
async def list_tools():
    return {"tools": list(registered_tools.keys())}

@app.post("/call_tool")
async def call_tool(req: ToolCallRequest):
    func = registered_tools.get(req.name)
    if not func:
        raise HTTPException(status_code=404, detail="Tool not found")
    try:
        if inspect.iscoroutinefunction(func):
            result = await func(**req.args)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: func(**req.args))
        return {"result": result}
    except aiohttp.ClientResponseError as cre:
        raise HTTPException(status_code=cre.status, detail=str(cre))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT, log_level="info")