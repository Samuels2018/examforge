from __future__ import annotations

import hashlib

from app.services.parsing import normalize_text


def exercise_signature(question: str, options: list[dict] | list[str]) -> str:
    """Firma estable para deduplicar ejercicios dentro de un workspace."""
    option_texts: list[str] = []
    for option in options:
        if isinstance(option, dict):
            option_texts.append(str(option.get("text", "")))
        else:
            option_texts.append(str(option))
    option_key = "|".join(sorted(option_texts))
    normalized = f"{_normalize_key(question)}::{_normalize_key(option_key)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_key(value: str) -> str:
    return " ".join(normalize_text(value).casefold().split())
