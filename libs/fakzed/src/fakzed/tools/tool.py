"""Executable tools: model-facing schema plus an entrypoint the agent runs."""

import asyncio
import inspect
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast, overload

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter, create_model

from fakzed.model.tool import Tool as ModelTool

F = TypeVar("F", bound=Callable[..., Any])


def _build_params_validator(fn: Callable[..., Any]) -> Any:
    """Build a pydantic model that validates the callable's arguments only.

    `TypeAdapter(fn).validate_python` would *invoke* the function — not
    acceptable for tools with side effects — so we model just the parameters
    from the signature and validate the arguments dict against it.
    """
    sig = inspect.signature(fn)
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = param.annotation if param.annotation is not inspect.Parameter.empty else Any
        if param.default is inspect.Parameter.empty:
            fields[name] = (annotation, ...)
        else:
            fields[name] = (annotation, param.default)
    return create_model(f"{fn.__name__}Params", **fields)


class Tool(BaseModel):
    """An executable tool.

    `parameters` is a JSON Schema dict shared with the model; `entrypoint` is
    the Python callable the agent invokes when the model requests this tool.
    Arguments are validated against the function signature on every call.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    entrypoint: Callable[..., Any] | None = None
    is_async: bool = False
    dangerous: bool = False
    permissions: list[str] | None = None
    _adapter: Any = PrivateAttr(default=None)
    _params_model: Any = PrivateAttr(default=None)

    def model_post_init(self, __context: Any) -> None:
        if self.entrypoint is not None:
            self._adapter = TypeAdapter(self.entrypoint)
            self._params_model = _build_params_validator(self.entrypoint)

    def to_model_tool(self) -> ModelTool:
        """Convert to the schema-only tool handed to model adapters."""
        return ModelTool(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    def call(self, arguments: dict[str, Any]) -> Any:
        """Invoke the entrypoint with the model-supplied arguments.

        Safe on the sync path: async entrypoints are bridged with
        `asyncio.run` (use `acall` inside a running event loop instead).
        """
        result = self._invoke(arguments)
        if inspect.isawaitable(result):
            result = asyncio.run(cast(Coroutine[Any, Any, Any], result))
        return result

    async def acall(self, arguments: dict[str, Any]) -> Any:
        """Async variant of `call`; awaits async entrypoints directly."""
        result = self._invoke(arguments)
        if inspect.isawaitable(result):
            result = await result
        return result

    def _invoke(self, arguments: dict[str, Any]) -> Any:
        if self.entrypoint is None:
            raise ValueError(f"Tool '{self.name}' has no entrypoint")
        return self.entrypoint(**self._validate(arguments))

    def _validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments against the function signature.

        Only the parameters are checked — the entrypoint is never invoked
        here, so side-effectful tools stay safe.
        """
        if self._params_model is None:
            return arguments
        if not self._params_model.model_fields:
            # entrypoint is pure **kwargs — nothing to validate against
            return arguments
        return self._params_model.model_validate(arguments).model_dump()


@overload
def tool(func: F, /) -> Tool: ...


@overload
def tool(
    *,
    name: str | None = None,
    description: str | None = None,
    dangerous: bool = False,
) -> Callable[[F], Tool]: ...


def tool(
    func: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    dangerous: bool = False,
) -> F | Tool:
    """Turn a function into a `Tool` (usable as `@tool` or `@tool(name=...)`).

    The parameters schema is derived from the function signature and type
    annotations via pydantic. `dangerous=True` marks tools that need approval
    through the agent's `tool_permission_handler` (Shell, file writes, ...).
    """

    def decorator(fn: F) -> Tool:
        doc = inspect.getdoc(fn)
        return Tool(
            name=name or fn.__name__,
            description=description or doc or "",
            parameters=TypeAdapter(fn).json_schema(),
            entrypoint=fn,
            is_async=inspect.iscoroutinefunction(fn),
            dangerous=dangerous,
        )

    if func is None:
        return cast(F, decorator)
    return decorator(func)
