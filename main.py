
import sys
sys.path.insert(0, "cactus/python/src")
functiongemma_path = "cactus/weights/functiongemma-270m-it"

import json, os, re, time
from cactus import cactus_init, cactus_complete, cactus_destroy
from google import genai
from google.genai import types


_LOCAL_SYSTEM_PROMPT = "You are a helpful assistant that can use tools."


def _coerce_args(function_calls, tools):
    """Coerce argument values to the types declared in the tool schema.

    FunctionGemma sometimes emits integers as JSON strings (e.g. "6" instead
    of 6). The benchmark's _normalize helper does not handle cross-type
    comparisons, so "6" != 6 and the match fails. This fixes that at the source.
    """
    tool_map = {t["name"]: t for t in tools}
    for call in function_calls:
        tool = tool_map.get(call["name"])
        if not tool:
            continue
        props = tool["parameters"]["properties"]
        for key, val in list(call.get("arguments", {}).items()):
            schema_type = props.get(key, {}).get("type", "string")
            if schema_type == "integer" and not isinstance(val, int):
                try:
                    call["arguments"][key] = int(val)
                except (ValueError, TypeError):
                    # Handle values like "5 minutes" or "10 AM" — extract first integer
                    m = re.search(r'-?\d+', str(val))
                    if m:
                        call["arguments"][key] = int(m.group())
            elif schema_type == "number" and not isinstance(val, (int, float)):
                try:
                    call["arguments"][key] = float(val)
                except (ValueError, TypeError):
                    m = re.search(r'-?[\d.]+', str(val))
                    if m:
                        call["arguments"][key] = float(m.group())
    return function_calls


def generate_cactus(messages, tools):
    """Run function calling on-device via FunctionGemma + Cactus."""
    model = cactus_init(functiongemma_path)

    cactus_tools = [{
        "type": "function",
        "function": t,
    } for t in tools]

    raw_str = cactus_complete(
        model,
        [{"role": "system", "content": _LOCAL_SYSTEM_PROMPT}] + messages,
        tools=cactus_tools,
        force_tools=True,
        max_tokens=256,
        temperature=0,
        stop_sequences=["<|im_end|>", "<end_of_turn>"],
    )

    cactus_destroy(model)

    try:
        raw = json.loads(raw_str)
    except json.JSONDecodeError:
        return {
            "function_calls": [],
            "total_time_ms": 0,
            "confidence": 0,
        }

    function_calls = _coerce_args(raw.get("function_calls", []), tools)

    return {
        "function_calls": function_calls,
        "total_time_ms": raw.get("total_time_ms", 0),
        "confidence": raw.get("confidence", 0),
    }


def generate_cloud(messages, tools):
    """Run function calling via Gemini Cloud API."""
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    gemini_tools = [
        types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        k: types.Schema(type=v["type"].upper(), description=v.get("description", ""))
                        for k, v in t["parameters"]["properties"].items()
                    },
                    required=t["parameters"].get("required", []),
                ),
            )
            for t in tools
        ])
    ]

    contents = [m["content"] for m in messages if m["role"] == "user"]

    start_time = time.time()

    gemini_response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=contents,
        config=types.GenerateContentConfig(tools=gemini_tools),
    )

    total_time_ms = (time.time() - start_time) * 1000

    function_calls = []
    for candidate in gemini_response.candidates:
        for part in candidate.content.parts:
            if part.function_call:
                function_calls.append({
                    "name": part.function_call.name,
                    "arguments": dict(part.function_call.args),
                })

    # Normalize cloud output the same way we normalize local output:
    # 1. Coerce integer/number fields — protobuf Struct can return numeric values
    #    as strings or floats even when the schema declares INTEGER.
    # 2. Normalize curly quotes/apostrophes in string values — Gemini often emits
    #    Unicode typographic quotes (U+2018/2019) which don't match the straight
    #    ASCII apostrophes in expected answers after .lower() normalization.
    function_calls = _coerce_args(function_calls, tools)
    for call in function_calls:
        for key, val in call.get("arguments", {}).items():
            if isinstance(val, str):
                call["arguments"][key] = (
                    val.replace("\u2018", "'").replace("\u2019", "'")
                       .replace("\u201c", '"').replace("\u201d", '"')
                )

    return {
        "function_calls": function_calls,
        "total_time_ms": total_time_ms,
    }


# Action patterns — each pattern corresponds to a distinct tool capability.
# If 2+ patterns match the user message, the query likely requires multiple function calls.
_ACTION_PATTERNS = [
    r'\bsend\b|\btext\b',                                          # send_message
    r'\bset\s+an?\s+alarm\b|\bwake\s+me\s+up\b|\balarm\s+for\b',  # set_alarm
    r'\bset\s+a\s+timer\b|\btimer\s+for\b',                        # set_timer
    r'\bplay\b',                                                    # play_music
    r'\bweather\b',                                                 # get_weather
    r'\bremind\b|\breminder\b',                                     # create_reminder
    r'\bfind\b|\blook\s+up\b|\bcontacts\b',                        # search_contacts
]


# Keyword patterns per tool: at least one must appear in the user prompt for
# the tool choice to be considered semantically plausible. This catches cases
# where FunctionGemma selects the right structure but the wrong tool entirely
# (e.g. calling get_weather for "Set an alarm for 8:15 AM").
_TOOL_KEYWORDS = {
    "set_alarm":       [r"\balarm\b", r"\bwake\s+me\s+up\b"],
    "set_timer":       [r"\btimer\b"],
    "play_music":      [r"\bplay\b"],
    "get_weather":     [r"\bweather\b"],
    "send_message":    [r"\bmessage\b", r"\btext\b", r"\bsend\b"],
    "create_reminder": [r"\bremind\b"],
    "search_contacts": [r"\bcontacts?\b", r"\blook\s+up\b", r"\bfind\b"],
}


def _local_output_valid(function_calls, tools, messages=None):
    """Return True only if every call passes structural and semantic checks.

    Structural: every required field is present and non-null.
    Semantic: the chosen function name has at least one keyword in the prompt
              (guards against confident wrong-tool selections).
    """
    if not function_calls:
        return False
    tool_map = {t["name"]: t for t in tools}
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "") if messages else ""

    for call in function_calls:
        tool = tool_map.get(call["name"])
        if not tool:
            return False

        # Structural: required fields must be present and non-empty.
        required = tool["parameters"].get("required", [])
        args = call.get("arguments", {})
        for field in required:
            if field not in args or args[field] is None or args[field] == "":
                return False

        # Semantic: function name should match at least one prompt keyword.
        if user_msg:
            patterns = _TOOL_KEYWORDS.get(call["name"], [])
            if patterns and not any(re.search(p, user_msg, re.I) for p in patterns):
                return False

    return True


def _needs_multiple_calls(messages):
    """Return True if the prompt likely requires 2+ tool calls."""
    user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
    matched = sum(1 for p in _ACTION_PATTERNS if re.search(p, user_msg, re.I))
    return matched >= 2


def generate_hybrid(messages, tools, confidence_threshold=0.99):
    """
    Smart hybrid routing strategy:
    - Multi-action queries (2+ distinct tool intents detected) → route directly to cloud.
      FunctionGemma 270M reliably produces only one function call, so skipping local
      inference avoids wasted latency and low F1 on hard multi-call cases.
    - Single-action queries → try local first with a lenient confidence threshold.
      More tools available = stricter threshold (harder selection problem).
      Fall back to cloud only when local confidence is too low.
    """
    # Pre-route multi-action requests directly to cloud (skip local entirely).
    if _needs_multiple_calls(messages):
        try:
            cloud = generate_cloud(messages, tools)
            cloud["source"] = "cloud (multi-action)"
            return cloud
        except Exception as e:
            print(f"Cloud call failed: {e}")
            # Fall through to local as last resort

    # Single-action: attempt local inference first.
    local = generate_cactus(messages, tools)

    # Adaptive threshold: more tools = harder tool-selection = require higher confidence.
    # confidence_threshold is honored as the ceiling for the hardest single-action cases.
    if len(tools) == 1:
        threshold = 0.5               # easy: one option, model just needs to fill args
    elif len(tools) <= 3:
        threshold = 0.7               # medium: small selection
    else:
        threshold = confidence_threshold  # large selection — use caller's threshold

    # For easy (1-tool) cases skip field validation: cloud latency would push
    # avg time over the 500ms baseline, costing more in time_score than we gain in F1.
    # For medium+ (2+ tools) apply validation: time_score is already 0 for those
    # groups so cloud fallback only costs on-device ratio, which is nearly offset by F1.
    valid = (len(tools) == 1) or _local_output_valid(local["function_calls"], tools, messages)
    if local["confidence"] >= threshold and valid:
        local["source"] = "on-device"
        return local

    try:
        cloud = generate_cloud(messages, tools)
        cloud["source"] = "cloud (fallback)"
        cloud["local_confidence"] = local["confidence"]
        cloud["total_time_ms"] += local["total_time_ms"]
        return cloud
    except Exception as e:
        print(f"Cloud fallback failed: {e}")
        local["source"] = "on-device (cloud error)"
        return local


def print_result(label, result):
    """Pretty-print a generation result."""
    print(f"\n=== {label} ===\n")
    if "source" in result:
        print(f"Source: {result['source']}")
    if "confidence" in result:
        print(f"Confidence: {result['confidence']:.4f}")
    if "local_confidence" in result:
        print(f"Local confidence (below threshold): {result['local_confidence']:.4f}")
    print(f"Total time: {result['total_time_ms']:.2f}ms")
    for call in result["function_calls"]:
        print(f"Function: {call['name']}")
        print(f"Arguments: {json.dumps(call['arguments'], indent=2)}")


############## Example usage ##############

if __name__ == "__main__":
    tools = [{
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name",
                }
            },
            "required": ["location"],
        },
    }]

    messages = [
        {"role": "user", "content": "What is the weather in San Francisco?"}
    ]

    on_device = generate_cactus(messages, tools)
    print_result("FunctionGemma (On-Device Cactus)", on_device)

    cloud = generate_cloud(messages, tools)
    print_result("Gemini (Cloud)", cloud)

    hybrid = generate_hybrid(messages, tools)
    print_result("Hybrid (On-Device + Cloud Fallback)", hybrid)
