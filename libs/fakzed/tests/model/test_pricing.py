"""Tests for token cost estimation and usage merging."""

import pytest

from fakzed.model.pricing import MODEL_PRICING, estimate_cost, find_price, merge_usage
from fakzed.model.response import Usage


class TestFindPrice:
    def test_exact_match(self) -> None:
        assert find_price("gpt-4o") == (2.50, 10.00)

    def test_prefix_family_match(self) -> None:
        assert find_price("gpt-4o-mini-2024-07-18") == (0.15, 0.60)

    def test_longest_prefix_wins(self) -> None:
        table = {"gpt-4": (1.0, 2.0), "gpt-4o": (3.0, 4.0)}
        assert find_price("gpt-4o-mini", pricing=table) == (3.0, 4.0)

    def test_case_and_whitespace_insensitive(self) -> None:
        assert find_price("  GPT-4O  ") == (2.50, 10.00)

    def test_unknown_model(self) -> None:
        assert find_price("some-unknown-model") is None

    def test_custom_table(self) -> None:
        assert find_price("my-model", pricing={"my-model": (7.0, 8.0)}) == (7.0, 8.0)

    def test_default_table_untouched_by_custom(self) -> None:
        assert MODEL_PRICING["deepseek-chat"] == (0.27, 1.10)


class TestEstimateCost:
    def test_full_million_tokens(self) -> None:
        usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
        assert estimate_cost("deepseek-chat", usage) == pytest.approx(0.27 + 1.10)

    def test_partial_usage(self) -> None:
        usage = Usage(input_tokens=1000, output_tokens=500)
        assert estimate_cost("gpt-4o-mini", usage) == pytest.approx(
            (1000 * 0.15 + 500 * 0.60) / 1_000_000
        )

    def test_none_usage(self) -> None:
        assert estimate_cost("gpt-4o", None) is None

    def test_unknown_model(self) -> None:
        assert estimate_cost("unknown-model", Usage(input_tokens=100)) is None

    def test_local_model_free(self) -> None:
        usage = Usage(input_tokens=10_000, output_tokens=10_000)
        assert estimate_cost("ollama", usage) == 0.0

    def test_reasoning_fallback_when_output_missing(self) -> None:
        usage = Usage(input_tokens=0, reasoning_tokens=1000)
        assert estimate_cost("deepseek-reasoner", usage) == pytest.approx(1000 * 2.19 / 1_000_000)

    def test_output_preferred_over_reasoning(self) -> None:
        usage = Usage(output_tokens=1000, reasoning_tokens=9000)
        assert estimate_cost("deepseek-reasoner", usage) == pytest.approx(1000 * 2.19 / 1_000_000)

    def test_custom_pricing(self) -> None:
        usage = Usage(input_tokens=100, output_tokens=200)
        assert estimate_cost("x", usage, pricing={"x": (10.0, 20.0)}) == pytest.approx(
            (100 * 10.0 + 200 * 20.0) / 1_000_000
        )


class TestMergeUsage:
    def test_empty(self) -> None:
        merged = merge_usage([])
        assert merged == Usage()

    def test_skips_none(self) -> None:
        merged = merge_usage([None, Usage(input_tokens=1)])
        assert merged == Usage(input_tokens=1)

    def test_sums_fields(self) -> None:
        merged = merge_usage(
            [
                Usage(input_tokens=10, output_tokens=20, total_tokens=30, reasoning_tokens=5),
                Usage(input_tokens=1, output_tokens=2, total_tokens=3, reasoning_tokens=1),
            ]
        )
        assert merged == Usage(
            input_tokens=11, output_tokens=22, total_tokens=33, reasoning_tokens=6
        )

    def test_none_fields_safe(self) -> None:
        merged = merge_usage([Usage(), Usage(input_tokens=7)])
        assert merged.input_tokens == 7
        assert merged.output_tokens is None
