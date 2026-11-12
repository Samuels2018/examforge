from __future__ import annotations

from app.schemas.usage import TokenUsage


def estimate_tokens(text: str) -> int:
    """Estimación conservadora para modelos locales (≈4 caracteres/token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_generation_usage(
    *,
    context: str,
    output_text: str,
    model: str | None = None,
) -> TokenUsage:
    prompt = estimate_tokens(context)
    completion = estimate_tokens(output_text)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        estimated=True,
        model=model,
    )
