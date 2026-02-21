import hashlib
from typing import List


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
