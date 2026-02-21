
import sys
sys.path.insert(0, "cactus/python/src")
functiongemma_path = "cactus/weights/functiongemma-270m-it"

import json, os, time, re, atexit
from cactus import cactus_init, cactus_complete, cactus_destroy, cactus_reset
from google import genai
from google.genai import types

_DIAG = True


def _diag(*args):
    if _DIAG:
        print("    [diag]", *args, flush=True)


# ---------------------------------------------------------------------------
# Model caching – load once, reuse across all calls, destroy on exit
# ---------------------------------------------------------------------------

_cactus_model = None


def _get_cactus_model():
    global _cactus_model
    if _cactus_model is None:
        _cactus_model = cactus_init(functiongemma_path)
        atexit.register(_cleanup_cactus_model)
    return _cactus_model


def _cleanup_cactus_model():
    global _cactus_model
    if _cactus_model is not None:
        cactus_destroy(_cactus_model)
        _cactus_model = None


# ---------------------------------------------------------------------------
# JSON repair — salvage malformed cactus responses (model-agnostic)
# ---------------------------------------------------------------------------

def _repair_and_parse(raw_str):
    """Parse the cactus JSON response, repairing common model output quirks."""
    try:
        return json.loads(raw_str)
    except json.JSONDecodeError:
        pass

    s = raw_str
    s = s.replace('\uff1a', ':')
    s = re.sub(r'<escape>', '', s)
    s = re.sub(r'<start_function_\w+>', '', s)
    s = re.sub(r'<end_function_\w+>', '', s)
    s = re.sub(r':\s*([}\]])', r':""' + r'\1', s)
    s = re.sub(r',\s*([}\]])', r'\1', s)

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    calls = []
    for m in re.finditer(
        r'"name"\s*:\s*"(\w+)"\s*,\s*"arguments"\s*:\s*\{([^}]*)\}', s
    ):
        name, args_str = m.group(1), m.group(2)
        args = {}
        for am in re.finditer(r'"(\w+)"\s*:\s*(?:"([^"]*)"|([-\d.]+))', args_str):
            key = am.group(1)
            if am.group(2) is not None:
                args[key] = am.group(2)
            elif am.group(3) is not None:
                try:
                    v = am.group(3)
                    args[key] = int(v) if '.' not in v else float(v)
                except ValueError:
                    args[key] = v
        calls.append({"name": name, "arguments": args})

    if calls:
        time_m = re.search(r'"total_time_ms"\s*:\s*([\d.]+)', raw_str)
        conf_m = re.search(r'"confidence"\s*:\s*([\d.]+)', raw_str)
        return {
            "function_calls": calls,
            "total_time_ms": float(time_m.group(1)) if time_m else 0,
            "confidence": float(conf_m.group(1)) if conf_m else 0.5,
            "cloud_handoff": False,
            "success": True,
        }

    return None


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

def _coerce_argument_types(function_calls, tools):
    """Cast argument values to match the declared schema types."""
    tool_map = {t["name"]: t for t in tools}
    for call in function_calls:
        tool = tool_map.get(call.get("name"))
        if not tool:
            continue
        props = tool["parameters"].get("properties", {})
        args = call.get("arguments", {})
        for key, value in list(args.items()):
            schema = props.get(key)
            if not schema:
                continue

            if isinstance(value, dict) and key in value:
                value = value[key]
                args[key] = value

            expected = schema.get("type", "").lower()
            try:
                if expected == "integer":
                    if not isinstance(value, int):
                        args[key] = int(float(str(value)))
                    args[key] = abs(args[key])
                elif expected == "number" and not isinstance(value, (int, float)):
                    args[key] = float(str(value))
                elif expected == "boolean" and not isinstance(value, bool):
                    args[key] = str(value).lower() in ("true", "1", "yes")
                elif expected == "string" and not isinstance(value, str):
                    args[key] = str(value)
            except (ValueError, TypeError):
                pass


def _filter_valid_calls(function_calls, tools):
    """Keep only calls that reference real tools with all required args non-empty."""
    tool_map = {t["name"]: t for t in tools}
    valid = []
    for call in function_calls:
        name = call.get("name")
        if name not in tool_map:
            continue
        required = tool_map[name]["parameters"].get("required", [])
        args = call.get("arguments", {})
        ok = True
        for r in required:
            if r not in args:
                ok = False
                break
            val = args[r]
            if val is None or (isinstance(val, str) and val.strip() == ""):
                ok = False
                break
        if ok:
            valid.append(call)
    return valid


def _deduplicate_calls(function_calls):
    """Remove exact-duplicate function calls."""
    seen = set()
    unique = []
    for call in function_calls:
        key = (call["name"], json.dumps(call.get("arguments", {}), sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(call)
    return unique


# ---------------------------------------------------------------------------
# Argument-query overlap scoring — used to compare model vs schema results
# ---------------------------------------------------------------------------

def _arg_query_overlap(calls, user_text):
    """Score how well argument values align with the query text."""
    text_lower = user_text.lower()
    score = 0
    for call in calls:
        for val in call.get("arguments", {}).values():
            if isinstance(val, int):
                if val == 0:
                    continue
                score += 2 if str(val) in text_lower else -1
            elif isinstance(val, str) and len(val) > 1:
                val_lower = val.lower()
                if val_lower in text_lower:
                    score += 3
                else:
                    words = [w for w in val_lower.split() if len(w) >= 2]
                    hits = sum(1 for w in words if w in text_lower)
                    score += hits if hits > 0 else -1
    return score


# ---------------------------------------------------------------------------
# Schema-driven tool matching (general, works for any tool)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset([
    "a", "an", "the", "to", "for", "of", "in", "is", "and", "or",
    "my", "me", "i", "it", "be", "at", "on", "with", "from", "by",
    "do", "can", "you", "please", "some", "this", "that", "what", "how",
    "which", "these", "should", "about", "up", "him", "her",
])


def _tokenize(text):
    """Split text into cleaned lowercase tokens."""
    result = []
    for w in text.lower().split():
        cleaned = w.strip('.,!?;:\'"()[]{}')
        if cleaned and len(cleaned) >= 2:
            result.append(cleaned)
    return result


def _words_similar(a, b):
    """Prefix-based similarity: 'remind' matches 'reminder', etc."""
    if a == b:
        return True
    if len(a) >= 3 and len(b) >= 3:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if longer.startswith(shorter):
            return True
    return False


def _tool_relevance(tool, query_words):
    """Score how relevant a tool is to the query using its full schema."""
    tool_words = set()
    for part in tool["name"].split("_"):
        tool_words.add(part.lower())
    for word in _tokenize(tool.get("description", "")):
        tool_words.add(word)
    for pname, pschema in tool["parameters"].get("properties", {}).items():
        for part in pname.split("_"):
            tool_words.add(part.lower())
        for word in _tokenize(pschema.get("description", "")):
            tool_words.add(word)
    tool_words -= _STOP_WORDS
    query_clean = query_words - _STOP_WORDS

    matches = 0
    for qw in query_clean:
        for tw in tool_words:
            if _words_similar(qw, tw):
                matches += 1
                break

    return matches / max(len(tool_words), 1)


def _find_best_tool(user_text, tools):
    """Pick the most relevant tool for the query using bag-of-words scoring."""
    query_words = set(_tokenize(user_text))
    best_tool = None
    best_score = 0.0
    for tool in tools:
        score = _tool_relevance(tool, query_words)
        if score > best_score:
            best_score = score
            best_tool = tool
    return best_tool if best_score > 0.05 else None


def _identify_tool_from_text(text, tools):
    """Identify the intended tool from the model's natural-language response."""
    text_lower = text.lower()
    best_tool = None
    best_count = 0
    for tool in tools:
        parts = tool["name"].split("_")
        count = sum(1 for p in parts if p.lower() in text_lower)
        if count > best_count:
            best_count = count
            best_tool = tool
    return best_tool if best_count > 0 else None


# ---------------------------------------------------------------------------
# Schema-driven argument extraction
#
# Priority order (resolves ambiguity when descriptions overlap):
#   1. integer params  → numbers from text (including "8:15" → [8, 15])
#   2. time params     → time expressions after "at" (digits + AM/PM)
#   3. location params → text after "in"/"at" prepositions
#   4. name params     → proper nouns (capitalized words not at start)
#   5. content params  → text after "saying"/"that says"
#   6. title params    → text after "about"/"to" (for tasks/reminders)
#   7. remaining       → leftover text assigned to any unfilled params
# ---------------------------------------------------------------------------

def _build_strip_set(tool):
    """Build a set of words to strip, using prefix matching against tool schema words."""
    base = set(_STOP_WORDS)
    schema_words = set()
    for part in tool["name"].split("_"):
        schema_words.add(part.lower())
    for w in _tokenize(tool.get("description", "")):
        schema_words.add(w)
    for _pname, pschema in tool["parameters"].get("properties", {}).items():
        for w in _tokenize(pschema.get("description", "")):
            schema_words.add(w)
    base |= schema_words
    return base, schema_words


def _should_strip(word_lower, strip_set, schema_words):
    """Check if a word should be stripped — exact match OR prefix of a schema word."""
    if word_lower in strip_set:
        return True
    if len(word_lower) >= 3:
        for sw in schema_words:
            if _words_similar(word_lower, sw):
                return True
    return False


def _extract_from_schema(user_text, tool):
    """
    Extract arguments from the query using the tool's parameter schema.
    Uses general English patterns (proper nouns, prepositions) — not tool-specific.
    """
    props = tool["parameters"]["properties"]
    required = tool["parameters"].get("required", [])
    strip_set, schema_words = _build_strip_set(tool)

    words = user_text.split()
    lower_text = user_text.lower()
    args = {}

    # --- Phase 1: Extract integers ---
    numbers = []
    for w in words:
        cleaned = w.strip('.,!?;:')
        if cleaned.isdigit():
            numbers.append(int(cleaned))
    for w in words:
        cleaned = w.strip('.,!?;:')
        if ":" in cleaned:
            parts_c = cleaned.split(":")
            if len(parts_c) == 2 and parts_c[0].isdigit() and parts_c[1].isdigit():
                numbers.extend([int(parts_c[0]), int(parts_c[1])])

    int_params = [(k, v) for k, v in props.items() if v.get("type") == "integer"]
    for i, (pname, _pschema) in enumerate(int_params):
        args[pname] = abs(numbers[i]) if i < len(numbers) else 0

    # --- Phase 2: Extract proper nouns (capitalized words not at start) ---
    proper_nouns = []
    for i, w in enumerate(words):
        cleaned = w.strip('.,!?;:\'"()[]{}')
        if (cleaned and i > 0 and cleaned[0].isupper()
                and not _should_strip(cleaned.lower(), strip_set, schema_words)
                and not cleaned.isdigit()
                and cleaned.upper() not in ("AM", "PM")):
            proper_nouns.append(cleaned)

    pn_used = set()

    # --- Phase 3: Extract string params by description category ---
    str_params = [(k, v) for k, v in props.items() if v.get("type") == "string"]

    for pname, pschema in str_params:
        desc = (pschema.get("description", "") + " " + pname).lower()

        # 3a. TIME params: extract "3:00 PM"-style expressions
        if any(kw in desc for kw in ["time", "when", "schedule"]):
            for prep in [" at "]:
                idx = lower_text.find(prep)
                if idx >= 0:
                    after = user_text[idx + len(prep):]
                    time_parts = []
                    for tw in after.split():
                        tw_clean = tw.strip('.,!?;:')
                        if tw_clean and (tw_clean[0].isdigit() or tw_clean.upper() in ("AM", "PM")):
                            time_parts.append(tw_clean)
                        elif time_parts:
                            break
                    if time_parts:
                        args[pname] = " ".join(time_parts)
                        continue

        # 3b. LOCATION params (checked BEFORE name to avoid "City name" ambiguity)
        if any(kw in desc for kw in ["location", "city", "place"]):
            for prep in [" in ", " at "]:
                idx = lower_text.find(prep)
                if idx >= 0:
                    after = user_text[idx + len(prep):].strip()
                    for end_marker in [" and ", ", ", " saying "]:
                        end_idx = after.lower().find(end_marker)
                        if end_idx >= 0:
                            after = after[:end_idx]
                    cleaned_loc = after.strip('.,!?;:')
                    if cleaned_loc:
                        args[pname] = cleaned_loc
                        break
            if pname in args:
                continue

        # 3c. NAME/ENTITY params: use proper nouns
        if any(kw in desc for kw in ["name", "person", "contact", "recipient", "query"]):
            for pn in proper_nouns:
                if pn not in pn_used:
                    args[pname] = pn
                    pn_used.add(pn)
                    break
            if pname in args:
                continue

        # 3d. CONTENT/MESSAGE params: text after "saying" / "that says"
        if any(kw in desc for kw in ["content", "message", "text"]):
            for marker in [" saying ", " that says "]:
                idx = lower_text.find(marker)
                if idx >= 0:
                    after = user_text[idx + len(marker):].strip()
                    for end_marker in [" and ", ", and "]:
                        end_idx = after.lower().find(end_marker)
                        if end_idx >= 0:
                            after = after[:end_idx]
                    cleaned_msg = after.strip('.,!?;:')
                    if cleaned_msg:
                        args[pname] = cleaned_msg
                        break
            if pname in args:
                continue

        # 3e. TITLE params: text after "about" or "to" (for tasks/reminders)
        if any(kw in desc for kw in ["title", "subject", "topic"]):
            for marker in [" about ", " to "]:
                idx = lower_text.find(marker)
                if idx >= 0:
                    after = user_text[idx + len(marker):].strip()
                    for end_marker in [" at ", " and ", ", "]:
                        end_idx = after.lower().find(end_marker)
                        if end_idx >= 0:
                            after = after[:end_idx]
                    for article in ["the ", "a ", "an "]:
                        if after.lower().startswith(article):
                            after = after[len(article):]
                    cleaned_title = after.strip('.,!?;:')
                    if cleaned_title:
                        args[pname] = cleaned_title
                        break
            if pname in args:
                continue

    # --- Phase 4: Fill remaining unfilled string params with leftover text ---
    remaining = []
    for w in words:
        cleaned = w.strip('.,!?;:\'"()[]{}').lower()
        if (cleaned
                and not _should_strip(cleaned, strip_set, schema_words)
                and not cleaned.isdigit()
                and cleaned not in [pn.lower() for pn in pn_used]
                and cleaned.upper() not in ("AM", "PM")):
            raw = w.strip('.,!?;:')
            if ":" in raw and all(p.isdigit() for p in raw.split(":")):
                continue
            remaining.append(raw)

    remaining_text = " ".join(remaining).strip()
    for pname, _pschema in str_params:
        if pname not in args and remaining_text:
            args[pname] = remaining_text
            remaining_text = ""

    if all(r in args and args[r] for r in required):
        return {"name": tool["name"], "arguments": args}
    return None


def _maybe_prefer_schema(calls, user_text, tools):
    """
    For each model-returned call, also run schema extraction for the SAME tool
    and pick whichever has better argument-query overlap. Zero-cost (no model call).
    """
    improved = []
    for call in calls:
        tool = next((t for t in tools if t["name"] == call["name"]), None)
        if not tool:
            improved.append(call)
            continue
        schema_alt = _extract_from_schema(user_text, tool)
        if schema_alt:
            _coerce_argument_types([schema_alt], [tool])
            alt_valid = _filter_valid_calls([schema_alt], [tool])
            if alt_valid:
                m_score = _arg_query_overlap([call], user_text)
                s_score = _arg_query_overlap(alt_valid, user_text)
                if s_score > m_score:
                    _diag(f"schema-improve: {call['name']} model_score={m_score} schema_score={s_score}")
                    improved.append(alt_valid[0])
                    continue
        improved.append(call)
    return improved


# ---------------------------------------------------------------------------
# Cactus inference primitives
# ---------------------------------------------------------------------------

_SYS_PROMPT = (
    "You are a helpful assistant that can use tools. "
    "When the user asks for multiple things, call all the relevant tools."
)


def _cactus_attempt(model, messages, cactus_tools, **overrides):
    """Run one cactus_complete call with JSON repair."""
    raw_str = cactus_complete(
        model,
        messages,
        tools=cactus_tools,
        force_tools=True,
        max_tokens=overrides.get("max_tokens", 512),
        stop_sequences=["<|im_end|>", "<end_of_turn>"],
        tool_rag_top_k=overrides.get("tool_rag_top_k", 0),
        confidence_threshold=0.0,
        temperature=overrides.get("temperature"),
    )
    return _repair_and_parse(raw_str)


def _get_ms(raw):
    return (raw or {}).get("total_time_ms", 0) or 0


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_cactus(messages, tools):
    """
    On-device function calling with multi-strategy fallback:

    1. Standard function calling via cactus (fast path).
       → Compare model's args against schema extract; pick the better match.
    2. Schema-guided single-tool retry — if the model picked the wrong tool
       or failed entirely, retry with only the schema-selected tool.
    3. Schema-driven extraction — construct a function call from the query
       using tool parameter descriptions.
    """
    model = _get_cactus_model()
    cactus_tools = [{"type": "function", "function": t} for t in tools]
    user_text = " ".join(m["content"] for m in messages if m["role"] == "user")

    # ---- Attempt 1: Standard function calling ----
    cactus_reset(model)
    raw1 = _cactus_attempt(
        model,
        [{"role": "system", "content": _SYS_PROMPT}] + messages,
        cactus_tools,
    )
    total_ms = _get_ms(raw1)

    calls1 = []
    if raw1 and raw1.get("function_calls"):
        fc = list(raw1["function_calls"])
        _coerce_argument_types(fc, tools)
        calls1 = _filter_valid_calls(fc, tools)

    if calls1:
        _diag(f"attempt1 OK: {json.dumps(calls1, ensure_ascii=False)}")
    else:
        resp = (raw1 or {}).get("response", "")
        _diag(f"attempt1 FAIL: response={resp!r:.120}")

    # Schema validation: only override when model's tool has ZERO query relevance
    skip_model_calls = False
    if calls1 and len(tools) > 1:
        qwords = set(_tokenize(user_text))
        schema_tool = _find_best_tool(user_text, tools)
        if schema_tool and calls1[0]["name"] != schema_tool["name"]:
            model_t = next((t for t in tools if t["name"] == calls1[0]["name"]), None)
            m_rel = _tool_relevance(model_t, qwords) if model_t else 0
            s_rel = _tool_relevance(schema_tool, qwords)
            if m_rel < 0.01 and s_rel > 0.15:
                skip_model_calls = True
                _diag(f"schema OVERRIDE: model={calls1[0]['name']} schema={schema_tool['name']} (m_rel={m_rel:.2f} s_rel={s_rel:.2f})")

    if calls1 and not skip_model_calls:
        calls1 = _maybe_prefer_schema(calls1, user_text, tools)
        return {
            "function_calls": calls1,
            "total_time_ms": total_ms,
            "confidence": float(raw1.get("confidence", 0) or 0),
            "cloud_handoff": False,
        }

    # ---- Find the best target tool for retry ----
    target = _find_best_tool(user_text, tools)
    if not target:
        model_text = (raw1 or {}).get("response", "") or ""
        target = _identify_tool_from_text(model_text, tools)
    if not target and len(tools) == 1:
        target = tools[0]
    _diag(f"target tool for retry: {target['name'] if target else 'NONE'}")

    # ---- Attempt 2: Single-tool retry (schema-guided) ----
    if target:
        single = [{"type": "function", "function": target}]
        cactus_reset(model)
        raw2 = _cactus_attempt(model, messages, single, temperature=0)
        total_ms += _get_ms(raw2)

        if raw2 and raw2.get("function_calls"):
            fc = list(raw2["function_calls"])
            _coerce_argument_types(fc, [target])
            calls2 = _filter_valid_calls(fc, [target])
            if calls2:
                calls2 = _maybe_prefer_schema(calls2, user_text, [target])
                _diag(f"attempt2 OK: {json.dumps(calls2, ensure_ascii=False)}")
                return {
                    "function_calls": calls2,
                    "total_time_ms": total_ms,
                    "confidence": float(raw2.get("confidence", 0) or 0),
                    "cloud_handoff": False,
                }

        resp2 = (raw2 or {}).get("response", "")
        _diag(f"attempt2 FAIL: response={resp2!r:.120}")

    # ---- Attempt 3: Schema-driven extraction from query text ----
    if target:
        extracted = _extract_from_schema(user_text, target)
        if extracted:
            _coerce_argument_types([extracted], [target])
            valid = _filter_valid_calls([extracted], [target])
            if valid:
                _diag(f"attempt3 (schema-extract) OK: {json.dumps(valid, ensure_ascii=False)}")
                return {
                    "function_calls": valid,
                    "total_time_ms": total_ms,
                    "confidence": 0.5,
                    "cloud_handoff": False,
                }
        _diag("attempt3 (schema-extract) FAIL")

    _diag("ALL LOCAL ATTEMPTS FAILED")
    return {
        "function_calls": [],
        "total_time_ms": total_ms,
        "confidence": 0,
        "cloud_handoff": True,
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
        model="gemini-2.5-flash",
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


def generate_hybrid(messages, tools):
    """
    Smart heuristic router for edge-cloud inference.

    Pipeline:
        1. Run local model with multi-strategy fallback (generate_cactus).
        2. If the query has multiple intents (conjunctions) and the model
           returned fewer calls than expected, split and run each part
           through the full local pipeline, then MERGE results.
        3. Cloud fallback only when all local attempts produce nothing.
    """
    user_text = " ".join(m["content"] for m in messages if m["role"] == "user")
    local = generate_cactus(messages, tools)

    model_calls = _filter_valid_calls(local["function_calls"], tools)
    model_calls = _deduplicate_calls(model_calls)

    parts = re.split(r'\s+and\s+|,\s*and\s+|,\s+', user_text)
    parts = [p.strip() for p in parts if len(p.strip()) > 5]
    expected_count = max(1, len(parts))

    total_ms = local["total_time_ms"]

    if len(parts) > 1 and len(model_calls) < expected_count:
        _diag(f"SPLIT: {len(parts)} parts, model has {len(model_calls)}/{expected_count} calls")
        split_calls = []
        for part in parts:
            _diag(f"  split part: {part!r}")
            sub = generate_cactus([{"role": "user", "content": part}], tools)
            sub_calls = _filter_valid_calls(sub["function_calls"], tools)
            split_calls.extend(sub_calls)
            total_ms += sub["total_time_ms"]
        split_calls = _deduplicate_calls(split_calls)

        merged = list(model_calls)
        existing_tools = {c["name"] for c in merged}
        for sc in split_calls:
            if sc["name"] not in existing_tools:
                merged.append(sc)
                existing_tools.add(sc["name"])
        merged = _deduplicate_calls(merged)

        _diag(f"SPLIT result (merged): {json.dumps(merged, ensure_ascii=False)}")
        if len(merged) > len(model_calls):
            model_calls = merged

    if model_calls:
        return {
            "function_calls": model_calls,
            "total_time_ms": total_ms,
            "confidence": local.get("confidence", 0),
            "source": "on-device",
        }

    # --- Cloud fallback ---
    cloud = generate_cloud(messages, tools)
    cloud["source"] = "cloud (fallback)"
    cloud["local_confidence"] = local.get("confidence", 0)
    cloud["total_time_ms"] += total_ms
    return cloud


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
