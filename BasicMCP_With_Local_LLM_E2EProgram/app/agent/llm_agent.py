import asyncio, json, logging, re
from logging.config import dictConfig
from typing import Any, Dict, List, Optional

import yaml
import ollama

from mcp import ClientSession
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tool_catalog import compact_tool_summaries, render_catalog_text
from app.mcp.mcp_client_utils import start_session, call_tool

log = logging.getLogger("agent")

# --------------------- Parsing & normalization helpers ------------------------

FENCE_RE = re.compile(r"^```(?:json)?|```$", re.IGNORECASE | re.MULTILINE)
_NUM_RE = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')

def _strip_fences_and_prose(s: str) -> str:
    s = s.strip()
    s = FENCE_RE.sub("", s).strip()
    first = s.find("{")
    if first > 0:
        s = s[first:]
    return s

def _extract_first_json_object(text: str) -> str:
    text = _strip_fences_and_prose(text)
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    return text[start : i + 1]
    raise ValueError("No complete JSON object found")

def parse_llm_json(s: str) -> Dict[str, Any]:
    obj = _extract_first_json_object(s)
    return json.loads(obj)

def _coerce_numbers(d: Dict[str, Any]) -> Dict[str, Any]:
    if "args" in d and isinstance(d["args"], dict):
        for k, v in list(d["args"].items()):
            if isinstance(v, str):
                try:
                    if any(c in v for c in ".eE"):
                        d["args"][k] = float(v)
                    else:
                        d["args"][k] = int(v)
                except Exception:
                    pass
    return d

def _normalize_decision(x: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(x, dict):
        raise ValueError("Top-level JSON must be an object")

    if "final" in x:
        if len(x.keys()) != 1 or not isinstance(x["final"], str):
            raise ValueError("Invalid final shape")
        return {"final": x["final"]}

    if "tool" in x:
        tool = x["tool"]
        args = x.get("args", {})
        if isinstance(args, list):
            merged = {}
            for item in args:
                if isinstance(item, dict):
                    merged.update(item)
            args = merged
        if not isinstance(tool, str) or not isinstance(args, dict):
            raise ValueError("Invalid tool shape")
        x = {"tool": tool, "args": args}
        x = _coerce_numbers(x)
        return x

    raise ValueError("Missing 'final' or 'tool'")

def _violations(decision_text: str) -> str:
    try:
        obj = parse_llm_json(decision_text)
    except Exception as e:
        return f"Your output was not a single JSON object. Error: {e}"
    notes = []
    if isinstance(obj, list):
        notes.append("Top-level must be an object, not an array.")
    if "final" in obj and "tool" in obj:
        notes.append("Do not include both 'final' and 'tool'.")
    if "tool" in obj and isinstance(obj.get("args"), list):
        notes.append("'args' must be an object, not an array.")
    return " ".join(notes) or "Output shape violated the rules."

def _extract_two_numbers(text: str):
    nums = _NUM_RE.findall(text or "")
    if len(nums) >= 2:
        try:
            return float(nums[0]), float(nums[1])
        except Exception:
            return None, None
    return None, None

def _canonicalize_args(tool: str, args: Dict[str, Any], user_input: str = "") -> Dict[str, Any]:
    if not isinstance(args, dict):
        args = {}

    lower = {str(k).lower(): v for k, v in args.items()}

    if tool == "add_numbers":
        a_keys = ["a", "x", "left", "lhs", "num1", "number1", "first", "value1"]
        b_keys = ["b", "y", "right", "rhs", "num2", "number2", "second", "value2"]

        def pick(keys):
            for k in keys:
                if k in lower:
                    return lower[k]
            return None

        a_val = pick(a_keys)
        b_val = pick(b_keys)

        # Backfill missing from the user's prompt
        if a_val is None or b_val is None:
            a_guess, b_guess = _extract_two_numbers(user_input)
            if a_val is None:
                a_val = a_guess
            if b_val is None:
                b_val = b_guess

        out = {}
        if a_val is not None:
            out["a"] = a_val
        if b_val is not None:
            out["b"] = b_val
        return out

    if tool == "say_hello":
        return {}

    return args

async def _repair_to_known_tool(
    user_input: str,
    model: str,
    timeout_ms: int,
    allowed_tools: List[str],
    decision_text: str,
) -> Dict[str, Any]:
    hint = (
        "Choose a tool ONLY from this exact list: "
        + ", ".join(f'"{n}"' for n in allowed_tools)
        + ". Return exactly one minified JSON object."
    )
    msgs = [
        {"role": "system", "content": "Return ONLY one JSON object."},
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": decision_text},
        {"role": "user", "content": hint},
    ]
    fixed = ollama.chat(
        model=model,
        messages=msgs,
        options={"timeout": timeout_ms, "format": "json"},
    )
    raw = fixed["message"]["content"].strip()
    return _normalize_decision(parse_llm_json(raw))

# ------------------------------ Main agent -----------------------------------

async def agent_run(user_input: str, cfg: Dict[str, Any]) -> str:
    async with (await start_session(cfg)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            summaries = compact_tool_summaries(tools)
            catalog = render_catalog_text(summaries)
            allowed_tool_names = [t["name"] for t in summaries]

            model = cfg["llm"]["model"]
            timeout = cfg["llm"].get("timeout_s", 30)
            timeout_ms = timeout * 1000

            sys_msg = SYSTEM_PROMPT + catalog + (
                "\n\nOnly use tool names that appear in the Tools list above. "
                "Never invent new tool names."
            )
            msgs = [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_input},
            ]

            try:
                first = ollama.chat(
                    model=model,
                    messages=msgs,
                    options={"timeout": timeout_ms, "format": "json"},
                )
                raw1 = first["message"]["content"].strip()
                decision_obj = _normalize_decision(parse_llm_json(raw1))
            except Exception as e:
                critique = _violations(raw1 if "raw1" in locals() else str(e))
                repair_msgs = msgs + [
                    {"role": "assistant", "content": raw1 if "raw1" in locals() else ""},
                    {"role": "user", "content": f"Your previous reply violated the format: {critique}\nReturn ONE corrected object now."},
                ]
                second = ollama.chat(
                    model=model,
                    messages=repair_msgs,
                    options={"timeout": timeout_ms, "format": "json"},
                )
                raw2 = second["message"]["content"].strip()
                decision_obj = _normalize_decision(parse_llm_json(raw2))

            max_steps = 5
            steps = 0
            observation: Optional[str] = None
            context_msgs = [
                {"role": "system", "content": "Return ONLY one minified JSON object each turn."},
                {"role": "user", "content": user_input},
            ]

            # Track final outputs we care about
            sum_value: Optional[float] = None
            greet_msg: Optional[str] = None

            must_greet = "say hello" in user_input.lower() or "say_hello" in user_input.lower()

            while steps < max_steps:
                # If the model tries to finalize but a greeting is required and not done, force say_hello.
                if "final" in decision_obj:
                    if must_greet and greet_msg is None:
                        decision_obj = {"tool": "say_hello", "args": {}}
                    else:
                        # Compose a final if we already gathered pieces
                        if sum_value is not None and greet_msg:
                            return f"The sum is {sum_value}. {greet_msg}"
                        if sum_value is not None:
                            return f"The sum is {sum_value}"
                        return decision_obj["final"]

                # Validate/repair tool name
                if decision_obj.get("tool") not in allowed_tool_names:
                    try:
                        decision_obj = await _repair_to_known_tool(
                            user_input=user_input,
                            model=model,
                            timeout_ms=timeout_ms,
                            allowed_tools=allowed_tool_names,
                            decision_text=json.dumps(decision_obj, ensure_ascii=False),
                        )
                    except Exception:
                        break  # fall through to compose from what we have
                    if "final" in decision_obj:
                        if must_greet and greet_msg is None:
                            decision_obj = {"tool": "say_hello", "args": {}}
                        else:
                            if sum_value is not None and greet_msg:
                                return f"The sum is {sum_value}. {greet_msg}"
                            if sum_value is not None:
                                return f"The sum is {sum_value}"
                            return decision_obj["final"]

                # Execute tool (with arg canonicalization)
                tool_name = decision_obj["tool"]
                tool_args = decision_obj.get("args", {})
                tool_args = _canonicalize_args(tool_name, tool_args, user_input)

                # Ensure add_numbers has both args; try a one-shot repair if needed
                if tool_name == "add_numbers" and ("a" not in tool_args or "b" not in tool_args):
                    fix_msgs = [
                        {"role": "system", "content": "Return ONLY one minified JSON object like {\"tool\":\"add_numbers\",\"args\":{\"a\":<float>,\"b\":<float>}}"},
                        {"role": "user", "content": f"From this instruction, extract the two numbers as 'a' and 'b' and return the tool call only: {user_input}"},
                    ]
                    fixed = ollama.chat(model=model, messages=fix_msgs, options={"timeout": timeout_ms, "format": "json"})
                    fixed_raw = fixed["message"]["content"].strip()
                    try:
                        fixed_obj = _normalize_decision(parse_llm_json(fixed_raw))
                        if fixed_obj.get("tool") == "add_numbers" and isinstance(fixed_obj.get("args"), dict):
                            tool_args = _canonicalize_args("add_numbers", fixed_obj["args"], user_input)
                    except Exception:
                        pass
                if tool_name == "add_numbers" and ("a" not in tool_args or "b" not in tool_args):
                    # Can't recover — stop and compose
                    break

                # Call the tool
                observation = await call_tool(session, tool_name, tool_args)

                # Capture results deterministically
                if tool_name == "add_numbers":
                    try:
                        sum_value = float(observation)
                    except Exception:
                        # sometimes API returns {"result": ...}; guard via str parsing
                        try:
                            sum_value = float(str(observation))
                        except Exception:
                            pass
                elif tool_name == "say_hello":
                    greet_msg = str(observation)

                # If greeting is required and not done yet, schedule it deterministically
                if must_greet and greet_msg is None:
                    decision_obj = {"tool": "say_hello", "args": {}}
                    steps += 1
                    continue

                # Otherwise ask the model what to do next (another tool or final)
                turn = [
                    {"role": "assistant", "content": json.dumps(decision_obj, ensure_ascii=False)},
                    {"role": "user", "content": f"Observation: {observation}\nReturn either the next tool JSON or the final JSON. Use only these tools: " + ", ".join(allowed_tool_names)},
                ]
                nxt = ollama.chat(
                    model=model,
                    messages=context_msgs + turn,
                    options={"timeout": timeout_ms, "format": "json"},
                )
                rawn = nxt["message"]["content"].strip()
                try:
                    decision_obj = _normalize_decision(parse_llm_json(rawn))
                except Exception:
                    break  # parse failed — compose from what we have

                steps += 1

            # ---- Compose a sensible final no matter how we exit ----
            if sum_value is not None and greet_msg:
                return f"The sum is {sum_value}. {greet_msg}"
            if sum_value is not None:
                return f"The sum is {sum_value}"
            if greet_msg:
                return greet_msg
            return "I couldn't complete the requested steps."
            

def main():
    with open("app/config/logging.yaml", "r") as f:
        dictConfig(yaml.safe_load(f))
    with open("app/config/settings.yaml", "r") as f:
        cfg = yaml.safe_load(f)

    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*", help="User prompt")
    args = ap.parse_args()
    question = " ".join(args.question) or "Please add 12.5 and 7.25, then say hello."

    out = asyncio.run(agent_run(question, cfg))
    print(out)

if __name__ == "__main__":
    main()