"""Agent primitive: model + instructions + tools + run loop."""

import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, TypeAdapter

from fakzed.context import ContextProvider
from fakzed.guardrails import (
    GuardrailError,
    InputGuardrail,
    OutputGuardrail,
    run_guardrail,
)
from fakzed.hooks import Hooks
from fakzed.hooks import fire as fire_hooks
from fakzed.knowledge import KnowledgeBase
from fakzed.memory import AgenticMemory
from fakzed.model import (
    Message,
    Model,
    ModelResponse,
    ToolCall,
    ToolResult,
    Usage,
    create_model,
    parse_model_id,
)
from fakzed.model.base import ResponseFormat
from fakzed.model.pricing import estimate_cost, merge_usage
from fakzed.model.tool import Tool as ModelTool
from fakzed.observability import RunEvent, RunMetrics, RunObserver, TraceSpan
from fakzed.session import Session
from fakzed.skills import Skill
from fakzed.storage import Storage
from fakzed.tools import Tool, ToolKit, tool


class RunResponse(BaseModel):
    """Result of an agent run; streamed runs also emit incremental events."""

    content: str = ""
    reasoning_content: str | None = None
    parsed: Any = None
    messages: list[Message] = Field(default_factory=list)
    usage: Usage | None = None
    tool_call: ToolCall | None = None
    tool_call_result: str | None = None
    event: str = "complete"


class AgentMaxIterationsError(Exception):
    """Raised when the run loop hits `max_iterations` without a final answer."""


class Agent(BaseModel):
    """The core Agent primitive.

    Combines a model, instructions, and tools behind a single `run` loop that
    automatically executes tool calls until the model produces a final answer.

    Example:
        agent = Agent(
            name="web researcher",
            model="deepseek:deepseek-chat",
            instructions="Always cite your sources.",
            tools=[web_search],
        )
        agent.print_response("Latest news on fusion energy", stream=True)
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str | None = None
    description: str | None = None
    instructions: str | list[str] | None = None
    model: Model | str | None = None
    tools: list[Tool] | None = None
    toolkits: list[ToolKit] | None = None
    skills: list[Skill] | None = None
    team: list["Agent"] | None = None
    markdown: bool = False
    add_history_to_context: bool = False
    num_history_runs: int = 3
    max_iterations: int = 5

    # session & memory
    session_id: str | None = None
    user_id: str | None = None
    session: Session | None = None
    storage: Storage | None = None
    memory: AgenticMemory | None = None
    add_session_history_to_context: bool = True
    add_memory_to_context: bool = True

    # session summarization (context compression)
    summarize: bool = False
    summarize_threshold: int = 20
    summarize_keep: int = 6

    # state, knowledge, and dynamic context
    agent_state: dict[str, Any] = Field(default_factory=dict)
    add_state_tools: bool = True
    knowledge: KnowledgeBase | None = None
    add_knowledge_to_context: bool = True
    context_providers: list[ContextProvider] | None = None

    # tool governance
    tool_permission_handler: Callable[[Tool, dict[str, Any]], bool] | None = None

    # control & safety (phase 7)
    input_guardrails: list[InputGuardrail] | None = None
    output_guardrails: list[OutputGuardrail] | None = None
    hooks: Hooks | None = None

    # observability (phase 8)
    observer: RunObserver | None = None

    #: Paused-run state used by `stop_after_tool_call` + `resume`.
    _paused_state: dict[str, Any] | None = PrivateAttr(default=None)

    #: Per-run observability state.
    _run_id: str | None = PrivateAttr(default=None)
    _tool_call_count: int = PrivateAttr(default=0)
    _iterations_count: int = PrivateAttr(default=0)
    _current_span: TraceSpan | None = PrivateAttr(default=None)
    _current_metrics: RunMetrics | None = PrivateAttr(default=None)
    _state_tools_cache: list[Tool] | None = PrivateAttr(default=None)

    #: Cumulative token usage across all runs of this agent instance.
    _total_usage: Usage | None = PrivateAttr(default=None)

    #: Messages accumulated across runs; fed back when add_history_to_context.
    session_messages: list[Message] = Field(default_factory=list, exclude=True)

    # -- resolution ----------------------------------------------------------

    def get_model(self) -> Model:
        """Resolve the agent's model from an instance or a provider string."""
        if isinstance(self.model, Model):
            return self.model
        if isinstance(self.model, str):
            return create_model(self.model)
        raise ValueError("Agent.model must be a Model instance or a 'provider:model' string")

    @property
    def total_usage(self) -> Usage:
        """Cumulative token usage across all runs of this agent instance."""
        return self._total_usage or Usage()

    @property
    def total_cost(self) -> float:
        """Estimated cumulative cost in USD, from `MODEL_PRICING`.

        Models without a pricing entry contribute 0.0.
        """
        return self._estimate_cost(self._total_usage)

    def reset_usage(self) -> None:
        """Reset the cumulative usage and cost counters."""
        self._total_usage = None

    def _model_id_for_pricing(self) -> str | None:
        """Resolve the bare model id for pricing lookup; None when unavailable."""
        if self.model is None:
            return None
        try:
            if isinstance(self.model, str):
                return parse_model_id(self.model)[1]
            return self.model.id
        except ValueError:
            return None

    def _estimate_cost(self, usage: Usage | None) -> float:
        if usage is None:
            return 0.0
        model_id = self._model_id_for_pricing()
        if model_id is None:
            return 0.0
        return estimate_cost(model_id, usage) or 0.0

    def _tool_map(self) -> dict[str, Tool]:
        return {tool.name: tool for tool in self._all_tools()}

    def _all_tools(self) -> list[Tool]:
        """Own tools, skill tools, toolkit tools, transfer tools, memory tools, state tools."""
        tools = [*(self.tools or [])]
        for skill in self.skills or []:
            tools.extend(skill.tools)
        for toolkit in self.toolkits or []:
            tools.extend(toolkit.get_tools())
        tools.extend(self.get_transfer_tools() or [])
        if self.memory is not None:
            tools.extend(self.memory.get_tools())
        if self.add_state_tools:
            tools.extend(self.get_state_tools())
        return tools

    def get_state_tools(self) -> list[Tool]:
        """Tools letting the model read and write the agent state.

        Built lazily and cached: the closures reference `self` (not copied
        values), so the cache stays valid for the agent's lifetime.
        """
        if self._state_tools_cache is None:

            @tool
            def get_agent_state() -> str:
                """Get the current agent state as JSON."""
                return json.dumps(self.agent_state, ensure_ascii=False, default=str)

            @tool
            def update_agent_state(state: dict[str, Any]) -> str:
                """Merge the given key-values into the agent state."""
                self.agent_state.update(state)
                return "Agent state updated."

            self._state_tools_cache = [get_agent_state, update_agent_state]
        return self._state_tools_cache

    def update_state(self, **kwargs: Any) -> None:
        """Merge key-values into the agent state (persisted with the session)."""
        self.agent_state.update(kwargs)
        self._persist_session()

    def get_transfer_tools(self) -> list[Tool] | None:
        """Build a `transfer_to_<member>` tool for each team member.

        Invoked by the run loop like any other tool; the entrypoint runs the
        member agent on the delegated task and returns its answer. Formal
        team orchestration (parallelism, routing, depth limits) lands with
        the Team primitive in phase 5.
        """
        if not self.team:
            return None
        tools: list[Tool] = []
        for member in self.team:
            member_name = member.name or "member"
            slug = re.sub(r"[^a-z0-9_]+", "_", member_name.lower()).strip("_") or "member"

            def make_transfer(target: Agent) -> Callable[[str], str]:
                def transfer(task: str) -> str:
                    return self._execute_member(target, task)

                return transfer

            entrypoint = make_transfer(member)
            tools.append(
                Tool(
                    name=f"transfer_to_{slug}",
                    description=(
                        f"Delegate a task to the '{member_name}' team member and return its answer."
                    ),
                    parameters=TypeAdapter(entrypoint).json_schema(),
                    entrypoint=entrypoint,
                )
            )
        return tools

    def _execute_member(self, member: "Agent", task: str) -> str:
        """Run a team member on a delegated task and return its answer.

        `Team` overrides this hook to record the interaction.
        """
        return member.run(task).content

    async def _aexecute_member(self, member: "Agent", task: str) -> str:
        """Async variant of `_execute_member`; `Team` overrides to record."""
        response = await member.arun(task)
        return response.content

    def _model_tools(self) -> list[ModelTool] | None:
        all_tools = self._all_tools()
        if not all_tools:
            return None
        return [tool.to_model_tool() for tool in all_tools]

    # -- prompt & history ----------------------------------------------------

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> str | None:
        """Assemble the system prompt from name, description, and instructions.

        `{{variable}}` placeholders in the instructions are rendered from
        `context` (runtime dependency injection).
        """
        parts: list[str] = []
        if self.name or self.description:
            identity = f"You are {self.name or 'an agent'}"
            if self.description:
                identity += f": {self.description}"
            parts.append(identity)
        if self.instructions:
            instructions = (
                self.instructions
                if isinstance(self.instructions, str)
                else "\n".join(self.instructions)
            )
            parts.append(self._render_template(instructions, context))
        if self.tools or self.team or self.toolkits or any(s.tools for s in self.skills or []):
            parts.append("You have access to tools. Use them when they help complete the task.")
        if self.team:
            roster = "\n".join(
                f"- {member.name or 'member'}"
                + (f": {member.description}" if member.description else "")
                for member in self.team
            )
            parts.append(
                "You are part of a team. Delegate tasks to members with the "
                "transfer_to_* tools. Members:\n" + roster
            )
        if self.skills:
            skill_blocks = []
            for skill in self.skills:
                block = f"## {skill.name}"
                if skill.description:
                    block += f"\n{skill.description}"
                block += f"\n{skill.instructions}"
                skill_blocks.append(block)
            parts.append("\n\n".join(skill_blocks))
        if self.toolkits:
            toolkit_blocks = [
                f"## Toolkit: {kit.name}\n{kit.instructions}"
                for kit in self.toolkits
                if kit.get_instructions()
            ]
            if toolkit_blocks:
                parts.append("\n\n".join(toolkit_blocks))
        if self.memory and self.add_memory_to_context:
            memory_block = self.memory.get_memories_for_context()
            if memory_block:
                parts.append(memory_block)
        return "\n\n".join(parts) or None

    @staticmethod
    def _render_template(text: str, context: dict[str, Any] | None) -> str:
        """Replace `{{key}}` placeholders with runtime context values."""
        if not context:
            return text
        for key, value in context.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    def _build_messages(
        self, user_message: Message, context: dict[str, Any] | None = None
    ) -> list[Message]:
        """Assemble system prompt + (optional) history + the user message."""
        messages: list[Message] = []
        system_prompt = self.get_system_prompt(context)
        if system_prompt:
            messages.append(Message(role="system", content=system_prompt))
        provider_context = self._get_provider_context()
        if provider_context:
            messages.append(Message(role="system", content=provider_context))
        knowledge_context = self._get_knowledge_context(user_message)
        if knowledge_context:
            messages.append(Message(role="system", content=knowledge_context))
        messages.extend(self._get_history())
        messages.append(user_message)
        return messages

    def _get_provider_context(self) -> str | None:
        """Collect dynamic context from all attached context providers."""
        if not self.context_providers:
            return None
        blocks = []
        for provider in self.context_providers:
            text = provider.get_context()
            if text:
                blocks.append(text)
        return "\n".join(blocks) or None

    def _get_knowledge_context(self, user_message: Message) -> str | None:
        """Retrieve relevant document chunks for the user message."""
        if self.knowledge is None or not self.add_knowledge_to_context:
            return None
        return self.knowledge.get_context_for_query(user_message.get_content()) or None

    def _get_history(self) -> list[Message]:
        """Recent messages to feed back, from the session or in-memory fallback."""
        if self.session is not None and self.add_session_history_to_context:
            history = [m for m in self.session.messages if m.role != "system"]
            result: list[Message] = []
            if self.session.summary:
                result.append(
                    Message(
                        role="system",
                        content=f"Conversation summary so far:\n{self.session.summary}",
                    )
                )
            result.extend(history[-self.num_history_runs :] if self.num_history_runs > 0 else [])
            return result
        if self.add_history_to_context and self.num_history_runs > 0 and self.session_messages:
            history = [m for m in self.session_messages if m.role != "system"]
            return history[-self.num_history_runs :]
        return []

    def _load_session(self) -> None:
        """Load the session from storage (or create an in-memory one)."""
        if self.session_id is None or self.session is not None:
            return
        if self.storage is None:
            self.session = Session(session_id=self.session_id, user_id=self.user_id)
            return
        row = self.storage.read_session(self.session_id)
        if row is not None:
            self.session = Session.from_row(row)
            stored_state = self.session.session_data.get("agent_state")
            if isinstance(stored_state, dict):
                self.agent_state.update(stored_state)
        else:
            self.session = Session(session_id=self.session_id, user_id=self.user_id)
            self.storage.create_session(self.session.to_row())

    def _record_session(self, messages: list[Message]) -> None:
        """Accumulate only the non-system messages newly produced by this run.

        History injected into the context and per-run system prompts are not
        re-recorded, so the session never stores duplicates.
        """
        existing_ids = {id(m) for m in self.session_messages}
        new_messages = [m for m in messages if id(m) not in existing_ids and m.role != "system"]
        self.session_messages.extend(new_messages)
        if self.session is not None:
            session_ids = {id(m) for m in self.session.messages}
            for message in new_messages:
                if id(message) not in session_ids:
                    self.session.add_message(message)

    def _persist_session(self) -> None:
        if self.storage is not None and self.session is not None:
            self.session.session_data["agent_state"] = self.agent_state
            self.storage.upsert_session(self.session.to_row())

    def _maybe_summarize(self) -> None:
        """Compress long sessions: summarize old messages and trim history."""
        if not self.summarize or self.session is None:
            return
        if len(self.session.messages) <= self.summarize_threshold:
            return
        if self.session.messages[-1].role != "assistant":
            return
        history = self.session.messages[: -self.summarize_keep]
        if not history:
            return
        history_text = "\n".join(f"{m.role}: {m.get_content()}" for m in history)
        prompt = (
            "Summarize the conversation below in a few bullet points, capturing"
            " user preferences, decisions, and important facts:\n\n" + history_text
        )
        try:
            response = self.get_model().response(messages=[Message(role="user", content=prompt)])
            new_summary = response.content.strip()
        except Exception:  # noqa: BLE001
            return  # summarization failure should never break the run
        if new_summary:
            self.session.summary = (
                f"{self.session.summary}\n{new_summary}" if self.session.summary else new_summary
            )
        self.session.messages = self.session.messages[-self.summarize_keep :]
        self.session_messages = [m for m in self.session.messages]

    def _finalize(
        self, messages: list[Message], response: ModelResponse, usage: Usage | None
    ) -> RunResponse:
        """Record the final answer, persist the session, and build the response."""
        self._total_usage = merge_usage([self._total_usage, usage])
        messages.append(
            Message(
                role="assistant",
                content=response.content,
                reasoning_content=response.reasoning_content,
            )
        )
        self._record_session(messages)
        self._maybe_summarize()
        self._persist_session()
        run_response = RunResponse(
            content=response.content,
            reasoning_content=response.reasoning_content,
            parsed=response.parsed,
            messages=messages,
            usage=usage,
            event="complete",
        )
        if self.hooks is not None:
            fire_hooks(self.hooks.on_run_end, run_response)
        self._end_observation(run_response)
        return run_response

    # -- tool execution ------------------------------------------------------

    def _execute_tool(self, call: ToolCall) -> str:
        tool = self._tool_map().get(call.name)
        if tool is None:
            return f"Error: unknown tool '{call.name}'"
        if not self._approve_tool(tool, call.arguments):
            return f"Error: tool '{call.name}' was rejected by the permission policy"
        self._tool_call_count += 1
        self._publish_tool_event("tool_call", call)
        self._fire_hooks_tool_call(call)
        try:
            result = tool.call(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return f"Error: tool '{call.name}' raised {type(exc).__name__}: {exc}"
        result = self._stringify_result(result)
        self._publish_tool_event("tool_result", call, result)
        self._fire_hooks_tool_result(call, result)
        return result

    async def _execute_tool_async(self, call: ToolCall) -> str:
        """Async variant that awaits async entrypoints in-place."""
        tool = self._tool_map().get(call.name)
        if tool is None:
            return f"Error: unknown tool '{call.name}'"
        if not self._approve_tool(tool, call.arguments):
            return f"Error: tool '{call.name}' was rejected by the permission policy"
        self._tool_call_count += 1
        self._publish_tool_event("tool_call", call)
        self._fire_hooks_tool_call(call)
        try:
            result = await tool.acall(call.arguments)
        except Exception as exc:  # noqa: BLE001
            return f"Error: tool '{call.name}' raised {type(exc).__name__}: {exc}"
        result = self._stringify_result(result)
        self._publish_tool_event("tool_result", call, result)
        self._fire_hooks_tool_result(call, result)
        return result

    def _approve_tool(self, tool: Tool, arguments: dict[str, Any]) -> bool:
        """Run the permission policy; no handler means allow everything."""
        if self.tool_permission_handler is None:
            return True
        try:
            return self.tool_permission_handler(tool, arguments)
        except Exception:  # noqa: BLE001
            return False  # policy errors deny by default

    # -- guardrails & hooks (phase 7) -----------------------------------------

    def _check_input_guardrails(self, text: str) -> str | None:
        """Return the first blocking message, or None when all pass."""
        for guardrail in self.input_guardrails or []:
            result = run_guardrail(guardrail.check, text)
            if not result.allowed:
                return (
                    f"Input blocked by guardrail '{guardrail.name}': {result.message or 'rejected'}"
                )
        return None

    def _check_output_guardrails(self, content: str) -> str | None:
        """Return the first blocking feedback, or None when all pass."""
        for guardrail in self.output_guardrails or []:
            result = run_guardrail(guardrail.check, content)
            if not result.allowed:
                return (
                    f"Your answer was blocked by guardrail '{guardrail.name}': "
                    f"{result.message or 'rejected'}. Please revise your answer."
                )
        return None

    def _max_output_guardrail_retries(self) -> int:
        return max((g.retries for g in self.output_guardrails or []), default=0)

    def _fire_hooks_start(self, message: str) -> None:
        if self.hooks is not None:
            fire_hooks(self.hooks.on_run_start, message)

    def _fire_hooks_tool_call(self, call: ToolCall) -> None:
        if self.hooks is not None:
            fire_hooks(self.hooks.on_tool_call, call)

    def _fire_hooks_tool_result(self, call: ToolCall, result: str) -> None:
        if self.hooks is not None:
            fire_hooks(self.hooks.on_tool_result, call, result)

    # -- observability (phase 8) ------------------------------------------------

    def _begin_observation(self, phase: str) -> None:
        """Start the per-run trace span, metrics, and event reporting."""
        self._run_id = uuid.uuid4().hex[:12]
        self._tool_call_count = 0
        self._iterations_count = 0
        observer = self.observer
        if observer is None:
            self._current_span = None
            self._current_metrics = None
            return
        observer.event_bus.publish(
            RunEvent(
                event_type="agent_run_start",
                agent_id=self.name,
                run_id=self._run_id,
                data={"phase": phase},
            )
        )
        self._current_span = observer.tracer.start_span(
            f"agent.{phase}", {"agent": self.name or "", "run_id": self._run_id}
        )
        self._current_metrics = (
            RunMetrics(run_id=self._run_id, agent_name=self.name)
            if observer.metrics is not None
            else None
        )

    def _end_observation(self, response: RunResponse) -> None:
        """Close the span and record metrics for the finished run."""
        observer = self.observer
        if observer is None:
            return
        observer.event_bus.publish(
            RunEvent(
                event_type="agent_run_end",
                agent_id=self.name,
                run_id=self._run_id,
                data={"content": response.content, "event": response.event},
            )
        )
        if self._current_span is not None:
            observer.tracer.end_span(self._current_span)
            self._current_span = None
        if self._current_metrics is not None and observer.metrics is not None:
            self._current_metrics.ended_at = time.time()
            self._current_metrics.absorb_usage(response.usage)
            self._current_metrics.cost_usd = self._estimate_cost(response.usage)
            self._current_metrics.tool_calls = self._tool_call_count
            self._current_metrics.iterations = self._iterations_count
            observer.metrics.record(self._current_metrics)
            self._current_metrics = None

    def _publish_tool_event(
        self, event_type: str, call: ToolCall, result: str | None = None
    ) -> None:
        observer = self.observer
        if observer is None:
            return
        data: dict[str, Any] = {"tool": call.name, "arguments": call.arguments}
        if result is not None:
            data["result"] = result
        observer.event_bus.publish(
            RunEvent(
                event_type=event_type,
                agent_id=self.name,
                run_id=self._run_id,
                data=data,
            )
        )

    def _publish_pause_event(self) -> None:
        observer = self.observer
        if observer is None:
            return
        observer.event_bus.publish(
            RunEvent(
                event_type="run_paused",
                agent_id=self.name,
                run_id=self._run_id,
            )
        )

    # -- human-in-the-loop (phase 7) ------------------------------------------

    @staticmethod
    def _stringify_result(result: Any) -> str:
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)

    def _append_tool_messages(self, messages: list[Message], response: ModelResponse) -> None:
        """Append the assistant tool-call message and each tool result."""
        messages.append(
            Message(role="assistant", content=response.content, tool_calls=response.tool_calls)
        )
        for call in response.tool_calls or []:
            result = self._execute_tool(call)
            messages.append(
                Message(
                    role="tool",
                    content=result,
                    tool_results=[ToolResult(tool_call_id=call.id, content=result)],
                )
            )

    async def _append_tool_messages_async(
        self, messages: list[Message], response: ModelResponse
    ) -> None:
        """Async variant of `_append_tool_messages`."""
        messages.append(
            Message(role="assistant", content=response.content, tool_calls=response.tool_calls)
        )
        for call in response.tool_calls or []:
            result = await self._execute_tool_async(call)
            messages.append(
                Message(
                    role="tool",
                    content=result,
                    tool_results=[ToolResult(tool_call_id=call.id, content=result)],
                )
            )

    @staticmethod
    def _as_user_message(message: str | Message) -> Message:
        return message if isinstance(message, Message) else Message(role="user", content=message)

    # -- run -----------------------------------------------------------------

    def run(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        """Run the agent, executing tool calls until a final answer.

        `context` renders `{{variable}}` placeholders in the instructions.
        `stop_after_tool_call` pauses after the first tool batch so a human
        can review the result before calling `resume()`.
        """
        self._load_session()
        user_message = self._as_user_message(message)
        blocked = self._check_input_guardrails(user_message.get_content())
        if blocked:
            raise GuardrailError(blocked)
        self._begin_observation("run")
        self._fire_hooks_start(user_message.get_content())
        messages = self._build_messages(user_message, context)
        model_tools = self._model_tools()
        return self._run_loop_sync(
            messages,
            model_tools,
            response_format,
            usage=None,
            start=0,
            stop_after_tool_call=stop_after_tool_call,
        )

    def _run_loop_sync(
        self,
        messages: list[Message],
        model_tools: list[ModelTool] | None,
        response_format: ResponseFormat | None,
        usage: Usage | None,
        start: int,
        stop_after_tool_call: bool,
    ) -> RunResponse:
        """Shared run loop; also used by `resume` to continue a paused run."""
        model = self.get_model()
        output_retries = 0
        max_output_retries = self._max_output_guardrail_retries()
        for iteration in range(start, self.max_iterations):
            self._iterations_count = iteration + 1
            response = model.response(messages, tools=model_tools, response_format=response_format)
            usage = merge_usage([usage, response.usage])
            if not response.tool_calls:
                feedback = self._check_output_guardrails(response.content)
                if feedback is not None and output_retries < max_output_retries:
                    output_retries += 1
                    messages.append(Message(role="user", content=feedback))
                    continue
                return self._finalize(messages, response, usage)
            self._append_tool_messages(messages, response)
            if stop_after_tool_call:
                self._publish_pause_event()
                self._paused_state = {
                    "messages": messages,
                    "model_tools": model_tools,
                    "usage": usage,
                    "iterations": iteration + 1,
                    "async": False,
                }
                return RunResponse(
                    content=response.content,
                    tool_call=response.tool_calls[0],
                    tool_call_result=messages[-1].content,
                    messages=messages,
                    usage=usage,
                    event="paused",
                )
        raise AgentMaxIterationsError(
            f"Agent '{self.name or 'unnamed'}' exceeded max_iterations={self.max_iterations}"
        )

    def resume(self) -> RunResponse:
        """Continue a run paused with `stop_after_tool_call=True`."""
        state = self._paused_state
        if state is None:
            raise ValueError("No paused run; call run(..., stop_after_tool_call=True) first")
        self._paused_state = None
        return self._run_loop_sync(
            messages=state["messages"],
            model_tools=state["model_tools"],
            response_format=None,
            usage=state.get("usage"),
            start=state["iterations"],
            stop_after_tool_call=False,
        )

    def run_stream(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
    ) -> Iterator[RunResponse]:
        """Streamed variant of `run`.

        Yields `chunk` events with incremental content, `tool_call_completed`
        events, and a final `complete` event.
        """
        self._load_session()
        user_message = self._as_user_message(message)
        blocked = self._check_input_guardrails(user_message.get_content())
        if blocked:
            raise GuardrailError(blocked)
        self._begin_observation("run_stream")
        self._fire_hooks_start(user_message.get_content())
        messages = self._build_messages(user_message, context)
        model = self.get_model()
        model_tools = self._model_tools()
        usage: Usage | None = None
        output_retries = 0
        max_output_retries = self._max_output_guardrail_retries()

        for _ in range(self.max_iterations):
            final: ModelResponse | None = None
            for event in model.response_stream(
                messages, tools=model_tools, response_format=response_format
            ):
                if event.event == "complete":
                    final = event
                else:
                    yield RunResponse(
                        content=event.content,
                        reasoning_content=event.reasoning_content,
                        event="chunk",
                    )
            if final is None:
                return
            usage = merge_usage([usage, final.usage])
            if not final.tool_calls:
                feedback = self._check_output_guardrails(final.content)
                if feedback is not None and output_retries < max_output_retries:
                    output_retries += 1
                    messages.append(Message(role="user", content=feedback))
                    continue
                yield self._finalize(messages, final, usage)
                return
            messages.append(
                Message(role="assistant", content=final.content, tool_calls=final.tool_calls)
            )
            for call in final.tool_calls:
                result = self._execute_tool(call)
                yield RunResponse(
                    content="",
                    tool_call=call,
                    tool_call_result=result,
                    event="tool_call_completed",
                )
                messages.append(
                    Message(
                        role="tool",
                        content=result,
                        tool_results=[ToolResult(tool_call_id=call.id, content=result)],
                    )
                )
        raise AgentMaxIterationsError(
            f"Agent '{self.name or 'unnamed'}' exceeded max_iterations={self.max_iterations}"
        )

    # -- async run -----------------------------------------------------------

    async def arun(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        """Async variant of `run`."""
        self._load_session()
        user_message = self._as_user_message(message)
        blocked = self._check_input_guardrails(user_message.get_content())
        if blocked:
            raise GuardrailError(blocked)
        self._begin_observation("arun")
        self._fire_hooks_start(user_message.get_content())
        messages = self._build_messages(user_message, context)
        model_tools = self._model_tools()
        return await self._run_loop_async(
            messages,
            model_tools,
            response_format,
            usage=None,
            start=0,
            stop_after_tool_call=stop_after_tool_call,
        )

    async def _run_loop_async(
        self,
        messages: list[Message],
        model_tools: list[ModelTool] | None,
        response_format: ResponseFormat | None,
        usage: Usage | None,
        start: int,
        stop_after_tool_call: bool,
    ) -> RunResponse:
        """Shared async run loop; also used by `aresume`."""
        model = self.get_model()
        output_retries = 0
        max_output_retries = self._max_output_guardrail_retries()
        for iteration in range(start, self.max_iterations):
            self._iterations_count = iteration + 1
            response = await model.aresponse(
                messages, tools=model_tools, response_format=response_format
            )
            if usage is None:
                usage = response.usage
            if not response.tool_calls:
                feedback = self._check_output_guardrails(response.content)
                if feedback is not None and output_retries < max_output_retries:
                    output_retries += 1
                    messages.append(Message(role="user", content=feedback))
                    continue
                return self._finalize(messages, response, usage)
            await self._append_tool_messages_async(messages, response)
            if stop_after_tool_call:
                self._publish_pause_event()
                self._paused_state = {
                    "messages": messages,
                    "model_tools": model_tools,
                    "usage": usage,
                    "iterations": iteration + 1,
                    "async": True,
                }
                return RunResponse(
                    content=response.content,
                    tool_call=response.tool_calls[0],
                    tool_call_result=messages[-1].content,
                    messages=messages,
                    usage=usage,
                    event="paused",
                )
        raise AgentMaxIterationsError(
            f"Agent '{self.name or 'unnamed'}' exceeded max_iterations={self.max_iterations}"
        )

    async def aresume(self) -> RunResponse:
        """Async variant of `resume`."""
        state = self._paused_state
        if state is None:
            raise ValueError("No paused run; call arun(..., stop_after_tool_call=True) first")
        self._paused_state = None
        return await self._run_loop_async(
            messages=state["messages"],
            model_tools=state["model_tools"],
            response_format=None,
            usage=state.get("usage"),
            start=state["iterations"],
            stop_after_tool_call=False,
        )

    async def arun_stream(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
    ) -> AsyncIterator[RunResponse]:
        """Async variant of `run_stream`."""
        self._load_session()
        user_message = self._as_user_message(message)
        blocked = self._check_input_guardrails(user_message.get_content())
        if blocked:
            raise GuardrailError(blocked)
        self._begin_observation("arun_stream")
        self._fire_hooks_start(user_message.get_content())
        messages = self._build_messages(user_message, context)
        model = self.get_model()
        model_tools = self._model_tools()
        usage: Usage | None = None
        output_retries = 0
        max_output_retries = self._max_output_guardrail_retries()

        for _ in range(self.max_iterations):
            final: ModelResponse | None = None
            async for event in model.aresponse_stream(
                messages, tools=model_tools, response_format=response_format
            ):
                if event.event == "complete":
                    final = event
                else:
                    yield RunResponse(
                        content=event.content,
                        reasoning_content=event.reasoning_content,
                        event="chunk",
                    )
            if final is None:
                return
            usage = merge_usage([usage, final.usage])
            if not final.tool_calls:
                feedback = self._check_output_guardrails(final.content)
                if feedback is not None and output_retries < max_output_retries:
                    output_retries += 1
                    messages.append(Message(role="user", content=feedback))
                    continue
                yield self._finalize(messages, final, usage)
                return
            messages.append(
                Message(role="assistant", content=final.content, tool_calls=final.tool_calls)
            )
            for call in final.tool_calls:
                result = await self._execute_tool_async(call)
                yield RunResponse(
                    content="",
                    tool_call=call,
                    tool_call_result=result,
                    event="tool_call_completed",
                )
                messages.append(
                    Message(
                        role="tool",
                        content=result,
                        tool_results=[ToolResult(tool_call_id=call.id, content=result)],
                    )
                )
        raise AgentMaxIterationsError(
            f"Agent '{self.name or 'unnamed'}' exceeded max_iterations={self.max_iterations}"
        )

    # -- printing ------------------------------------------------------------

    def print_response(
        self,
        message: str | Message,
        *,
        stream: bool = False,
        show_message: bool = True,
        **kwargs: Any,
    ) -> None:
        """Run the agent and print the response (rendered markdown if enabled)."""
        if show_message:
            text = message if isinstance(message, str) else message.get_content()
            print(f"> {text}\n")

        if stream:
            for event in self.run_stream(message, **kwargs):
                if event.event == "chunk" and event.content:
                    print(event.content, end="", flush=True)
            print()
            return

        response = self.run(message, **kwargs)
        self._print_content(response.content)

    def _print_content(self, content: str) -> None:
        if self.markdown:
            try:
                from rich.console import Console
                from rich.markdown import Markdown

                Console().print(Markdown(content))
                return
            except ImportError:
                pass
        print(content)
