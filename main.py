
import sys
sys.path.insert(0, "cactus/python/src")
functiongemma_path = "cactus/weights/functiongemma-270m-it"

import json, os, re, time
from cactus import cactus_init, cactus_complete, cactus_destroy
from google import genai
from google.genai import types


def generate_cactus(messages, tools):
    """Run function calling on-device via FunctionGemma + Cactus."""
    model = cactus_init(functiongemma_path)

    cactus_tools = [{
        "type": "function",
        "function": t,
    } for t in tools]

    raw_str = cactus_complete(
        model,
        [{"role": "system", "content": "You are a helpful assistant that can use tools."}] + messages,
        tools=cactus_tools,
        force_tools=True,
        max_tokens=256,
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

    return {
        "function_calls": raw.get("function_calls", []),
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

    if local["confidence"] >= threshold:
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
