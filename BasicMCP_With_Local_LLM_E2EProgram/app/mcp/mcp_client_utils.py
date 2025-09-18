import sys, os, json, logging
from typing import Any, Dict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

log = logging.getLogger(__name__)

def _params_from_cfg(cfg: Dict[str, Any]) -> StdioServerParameters:
    """
    Build spawn parameters for the MCP server (STDIO).
    - Always use the SAME interpreter as the running agent (sys.executable),
      so we don't accidentally launch system Python.
    - Inherit the parent environment (env=None). Passing {} on Windows
      can break Winsock because critical vars like SystemRoot get wiped.
    - Make the script path absolute to avoid CWD surprises.
    """
    mcp_cfg = cfg.get("mcp", {})

    # Force the venv's interpreter (the one running the agent)
    command = sys.executable

    args = mcp_cfg.get("args", ["app/mcp/mcp_server.py"])
    if args and not os.path.isabs(args[0]):
        args[0] = os.path.abspath(args[0])

    # Inherit parent env; do NOT pass an empty dict on Windows
    env = mcp_cfg.get("env", None) or None

    log.info("Spawning MCP server: %s %s", command, " ".join(args))
    return StdioServerParameters(command=command, args=args, env=env)

async def start_session(cfg: Dict[str, Any]):
    """
    Create the stdio client context with the spawn parameters.
    Usage:
        async with (await start_session(cfg)) as (read, write):
            ...
    """
    params = _params_from_cfg(cfg)
    return stdio_client(params)

async def call_tool(session: ClientSession, name: str, args: Dict[str, Any]) -> str:
    """Call a tool by name and return the first text-ish content."""
    log.info("Calling tool %s with args=%s", name, json.dumps(args))
    result = await session.call_tool(name, args)
    if not result or not result.content:
        return ""
    item = result.content[0]
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)
    return str(getattr(item, "value", ""))