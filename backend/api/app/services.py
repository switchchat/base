import hashlib
import uuid
from typing import List
from datetime import datetime, timezone


_session_state = {
    "active": False,
    "session_id": None,
    "started_at": None,
    "called_functions": [],
}


def predict(text: str) -> str:
    # Placeholder prediction function. Replace with model inference.
    return f"echo: {text}"


def list_models() -> List[str]:
    # Placeholder model listing. Replace with dynamic discovery.
    return ["functiongemma-270m-it", "dummy-model"]


def embed(text: str, dim: int = 64) -> List[float]:
    # Deterministic pseudo-embedding based on SHA256; placeholder for real model.
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec: List[float] = []
    # Map bytes to [-1,1]
    for i in range(dim):
        b = h[i % len(h)]
        vec.append((b - 128) / 128.0)
    return vec


def predict_default() -> str:
    # Default action for button-triggered prediction. Can be configured via env var.
    import os
    default_text = os.getenv("DEFAULT_PROMPT", "button-press")
    return predict(default_text)


def embed_default(dim: int = 64) -> List[float]:
    import os
    default_text = os.getenv("DEFAULT_EMBED_TEXT", "button-press")
    return embed(default_text, dim=dim)


def start_session() -> dict:
    if _session_state["active"]:
        return {
            "message": "Session is already active.",
            "session_id": _session_state["session_id"],
            "active": True,
        }

    session_id = str(uuid.uuid4())
    _session_state["active"] = True
    _session_state["session_id"] = session_id
    _session_state["started_at"] = datetime.now(timezone.utc).isoformat()
    _session_state["called_functions"] = ["/session/start"]

    return {
        "message": "Session started.",
        "session_id": session_id,
        "active": True,
    }


def end_session() -> dict:
    if not _session_state["active"]:
        return {
            "message": "Session is already inactive.",
            "session_id": None,
            "active": False,
            "called_functions": [],
        }

    _session_state["called_functions"].append("/session/end")

    result = {
        "message": "Session ended.",
        "session_id": _session_state["session_id"],
        "active": False,
        "called_functions": list(_session_state["called_functions"]),
    }

    _session_state["active"] = False
    _session_state["session_id"] = None
    _session_state["started_at"] = None
    _session_state["called_functions"] = []

    return result


def is_session_active() -> bool:
    return bool(_session_state["active"])


def record_function_call(function_name: str) -> None:
    if _session_state["active"]:
        _session_state["called_functions"].append(function_name)


def get_session_status() -> dict:
    return {
        "session_id": _session_state["session_id"],
        "active": bool(_session_state["active"]),
        "called_functions": list(_session_state["called_functions"]),
    }
