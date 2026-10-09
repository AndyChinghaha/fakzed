"""Evals: judge agent outputs against expected answers."""

from collections.abc import Callable

from pydantic import BaseModel, Field

from fakzed.agent.agent import Agent

#: Judge: (output, expected) -> bool (pass) or float (0..1 score).
Judge = Callable[[str, str | None], bool | float]


class EvalCase(BaseModel):
    """One evaluation case."""

    name: str
    input: str
    expected: str | None = None


class EvalResult(BaseModel):
    """Outcome of a single eval case."""

    case_name: str
    passed: bool = False
    score: float = 0.0
    output: str = ""
    expected: str | None = None


class EvalReport(BaseModel):
    """Aggregated eval results."""

    results: list[EvalResult] = Field(default_factory=list)
    passed: int = 0
    total: int = 0
    accuracy: float = 0.0
    avg_score: float = 0.0


def contains_judge(output: str, expected: str | None) -> bool:
    """Default judge: pass when the expected text appears in the output."""
    if expected is None:
        return True
    return expected in output


def eval_agent(
    agent: Agent,
    cases: list[EvalCase],
    judge: Judge | None = None,
) -> EvalReport:
    """Run the agent on every case and score the outputs.

    `judge` receives (output, expected) and returns bool or float; defaults
    to substring matching via `contains_judge`.
    """
    judge = judge or contains_judge
    results: list[EvalResult] = []
    for case in cases:
        output = agent.run(case.input).content
        verdict = judge(output, case.expected)
        verdict_passed = bool(verdict) if isinstance(verdict, bool) else verdict >= 0.5
        score = 1.0 if verdict is True else (0.0 if verdict is False else float(verdict))
        results.append(
            EvalResult(
                case_name=case.name,
                passed=verdict_passed,
                score=score,
                output=output,
                expected=case.expected,
            )
        )
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    return EvalReport(
        results=results,
        passed=passed,
        total=total,
        accuracy=round(passed / total, 4) if total else 0.0,
        avg_score=round(sum(r.score for r in results) / total, 4) if total else 0.0,
    )
