
from typing import List, Dict, Any

def compact_tool_summaries(tools) -> List[Dict[str, Any]]:
    summaries = []
    for t in tools.tools:
        name = t.name
        desc = (t.description or "").strip()
        if name == "add_numbers":
            signature = "add_numbers(a: float, b: float) -> float"
        elif name == "say_hello":
            signature = "say_hello() -> str"
        else:
            signature = name
        summaries.append({"name": name, "description": desc, "signature": signature})
    return summaries

def render_catalog_text(summaries: List[Dict[str, Any]]) -> str:
    lines = ["\nTools:\n"]
    for t in summaries:
        lines.append(f"- {t['name']}: {t['signature']} — {t['description']}")
    return "\n".join(lines)
