"""Tests for per-turn run statistics."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic_ai.usage import RunUsage

from friday.agent.stats import TurnStats, format_turn_summary, record_turn_result


class DummyResult:
    """Small stand-in for a pydantic-ai run result."""

    def __init__(
        self,
        usage: RunUsage,
        *,
        model_name: str = '',
        provider_name: str = '',
        provider_details: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._usage = usage
        self.response = SimpleNamespace(
            model_name=model_name,
            provider_name=provider_name,
            provider_details=provider_details,
        )
        self.metadata = metadata

    def usage(self) -> RunUsage:
        return self._usage


def test_turn_summary_aggregates_usage_and_keeps_requested_model_label() -> None:
    stats = TurnStats()

    record_turn_result(
        stats,
        DummyResult(
            RunUsage(input_tokens=10, output_tokens=4),
            model_name='claude-sonnet-4-20250514',
            provider_name='anthropic',
        ),
        'anthropic:claude-sonnet-4-20250514',
    )
    record_turn_result(
        stats,
        DummyResult(
            RunUsage(input_tokens=3, output_tokens=2),
            model_name='claude-sonnet-4-20250514',
            provider_name='anthropic',
        ),
        'anthropic:claude-sonnet-4-20250514',
    )

    summary = format_turn_summary(stats)

    assert summary.startswith('model: anthropic:claude-sonnet-4-20250514')
    assert 'tokens: 19 total, 13 in, 6 out' in summary
    assert 'cost: n/d' in summary


def test_turn_summary_handles_multiple_models_and_known_cost() -> None:
    stats = TurnStats()

    record_turn_result(
        stats,
        DummyResult(
            RunUsage(input_tokens=8, output_tokens=2),
            model_name='gpt-4.1',
            provider_name='openai',
            provider_details={'cost_usd': 0.0015},
        ),
        'openai:gpt-4.1',
    )
    record_turn_result(
        stats,
        DummyResult(
            RunUsage(input_tokens=5, output_tokens=1),
            model_name='claude-sonnet-4-20250514',
            provider_name='anthropic',
            metadata={'billing': {'total_cost_usd': 0.0025}},
        ),
        'anthropic:claude-sonnet-4-20250514',
    )

    summary = format_turn_summary(stats)

    assert summary.startswith('models: openai:gpt-4.1, anthropic:claude-sonnet-4-20250514')
    assert 'tokens: 16 total, 13 in, 3 out' in summary
    assert 'cost: $0.004000' in summary


def test_turn_summary_uses_delta_for_shared_run_usage() -> None:
    stats = TurnStats()
    shared_usage = RunUsage(input_tokens=4, output_tokens=1)

    record_turn_result(
        stats,
        DummyResult(
            shared_usage,
            model_name='gpt-4.1',
            provider_name='openai',
        ),
        'openai:gpt-4.1',
    )

    shared_usage.input_tokens = 9
    shared_usage.output_tokens = 3
    shared_usage.requests = 2

    record_turn_result(
        stats,
        DummyResult(
            shared_usage,
            model_name='gpt-4.1',
            provider_name='openai',
        ),
        'openai:gpt-4.1',
    )

    summary = format_turn_summary(stats)

    assert 'tokens: 12 total, 9 in, 3 out' in summary
