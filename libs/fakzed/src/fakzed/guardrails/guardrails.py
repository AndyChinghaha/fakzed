"""Input and output guardrails for agent runs.

Input guardrails block a run before the model is called; output guardrails
inspect the model's answer and, when blocked, feed the rejection reason back
to the model so it can revise its answer (bounded by `retries`).
"""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: Guardrail check: receives the data and an optional context dict, returns
#: a GuardrailResult, a bool (True = allow), or a str (non-empty = reject).
GuardrailCheck = Callable[[str, dict[str, Any] | None], "GuardrailResult | bool | str | None"]


class GuardrailResult(BaseModel):
    """Outcome of a guardrail check."""

    allowed: bool = True
    message: str | None = None


class InputGuardrail(BaseModel):
    """Inspects the user message before a run starts; blocks by raising."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    check: GuardrailCheck


class OutputGuardrail(BaseModel):
    """Inspects the model answer; blocked answers trigger a model revision."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    check: GuardrailCheck
    #: How many times the model may revise a blocked output.
    retries: int = 2


class GuardrailError(Exception):
    """Raised when an input guardrail blocks a run."""


def run_guardrail(
    check: GuardrailCheck, data: str, context: dict[str, Any] | None = None
) -> GuardrailResult:
    """Normalize the many supported return shapes into a GuardrailResult."""
    result = check(data, context)
    if isinstance(result, GuardrailResult):
        return result
    if isinstance(result, bool):
        return GuardrailResult(allowed=result)
    if isinstance(result, str):
        return GuardrailResult(allowed=not result, message=result or None)
    return GuardrailResult(allowed=True)


class Guardrails(BaseModel):
    """Bundle of input and output guardrails attachable to an Agent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    input: list[InputGuardrail] = Field(default_factory=list)
    output: list[OutputGuardrail] = Field(default_factory=list)
