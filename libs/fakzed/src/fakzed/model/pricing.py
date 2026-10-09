"""Token cost estimation for common providers.

Prices are USD per 1M tokens, taken from public provider pricing pages.
They are reference values: pass your own table to `find_price` / `estimate_cost`
to override them.
"""

from collections.abc import Iterable

from fakzed.model.response import Usage

#: Reference pricing table: model id (or family prefix) -> (input, output) USD per 1M tokens.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # deepseek: https://api-docs.deepseek.com/quick_start/pricing
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    # openai: https://openai.com/api/pricing
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "o3": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # anthropic: https://www.anthropic.com/pricing
    "claude-opus-4": (15.00, 75.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-haiku": (0.25, 1.25),
    # local models served by ollama: free
    "ollama": (0.0, 0.0),
}


def find_price(
    model_id: str, pricing: dict[str, tuple[float, float]] | None = None
) -> tuple[float, float] | None:
    """Look up (input, output) USD per 1M tokens for a model id.

    Exact match first, then longest-prefix family match, so
    "gpt-4o-mini-2024-07-18" resolves via "gpt-4o-mini". Returns None for
    unknown models.
    """
    table = MODEL_PRICING if pricing is None else pricing
    normalized = model_id.lower().strip()
    if normalized in table:
        return table[normalized]
    for family in sorted(table, key=len, reverse=True):
        if normalized.startswith(family):
            return table[family]
    return None


def estimate_cost(
    model_id: str,
    usage: Usage | None,
    pricing: dict[str, tuple[float, float]] | None = None,
) -> float | None:
    """Estimate the USD cost of `usage` for `model_id`; None when unknown.

    `output_tokens` usually already includes reasoning tokens for most
    providers; when it is missing, `reasoning_tokens` is used as fallback.
    """
    if usage is None:
        return None
    price = find_price(model_id, pricing)
    if price is None:
        return None
    input_price, output_price = price
    input_tokens = usage.input_tokens or 0
    output_tokens = usage.output_tokens
    if output_tokens is None:
        output_tokens = usage.reasoning_tokens or 0
    return round((input_tokens * input_price + output_tokens * output_price) / 1_000_000, 8)


def merge_usage(usages: Iterable[Usage | None]) -> Usage:
    """Sum token counts across usages into a single Usage (None-safe).

    Fields absent from every usage stay None (unknown), matching the
    semantics of `Usage`.
    """
    merged = Usage()
    for usage in usages:
        if usage is None:
            continue
        for field in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens"):
            value = getattr(usage, field)
            if value is None:
                continue
            setattr(merged, field, (getattr(merged, field) or 0) + value)
    return merged
