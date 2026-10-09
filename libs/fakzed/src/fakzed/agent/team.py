"""Team primitive: coordinated, routed, or collaborative multi-agent runs."""

import json
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from fakzed.agent.agent import Agent, RunResponse
from fakzed.model import Message, ModelResponse, Usage
from fakzed.model.base import ResponseFormat


class MemberInteraction(BaseModel):
    """One delegation: the task sent to a member and the answer it returned."""

    member_name: str
    task: str
    response: str = ""
    usage: Usage | None = None


class TeamRoute(BaseModel):
    """Structured routing decision produced by the team leader."""

    member: str
    task: str
    reasoning: str | None = None


class Team(Agent):
    """A team of agents: the team itself acts as the leader Agent.

    Members are ordinary Agents (or nested Teams). `mode` picks the
    coordination strategy:

    - coordinate: the leader answers directly, delegating work through
      `transfer_to_*` tools.
    - route: the leader emits a structured route and exactly one member
      handles the task.
    - collaborate: every member works on the task, then the leader
      synthesizes a single final answer.

    Because a Team is an Agent, teams nest: a team can be a member of
    another team.

    Example:
        team = Team(
            name="research team",
            model="deepseek:deepseek-chat",
            mode="route",
            members=[
                Agent(name="researcher", instructions="Find facts."),
                Agent(name="writer", instructions="Write clearly."),
            ],
        )
        team.print_response("Summarize the latest fusion energy news")
    """

    members: list[Agent] = Field(default_factory=list)
    mode: Literal["coordinate", "route", "collaborate"] = "coordinate"

    #: Delegation history (task -> member -> answer), for audit or replay.
    member_interactions: list[MemberInteraction] = Field(default_factory=list, exclude=True)

    #: Give members the team's model when they have none of their own.
    share_model: bool = True
    #: Share the team's storage/user_id with members that have none.
    share_context: bool = True

    def model_post_init(self, __context: Any) -> None:
        """Mirror `members` into `team` (or vice versa) so the Agent base
        class sees the roster for transfer tools and the system prompt."""
        super().model_post_init(__context)
        if self.members and not self.team:
            self.team = self.members
        elif self.team and not self.members:
            self.members = self.team

    # -- members ------------------------------------------------------------

    def get_member(self, name: str) -> Agent | None:
        """Find a member by name (case-insensitive)."""
        lowered = name.strip().lower()
        for member in self.members:
            if (member.name or "").lower() == lowered:
                return member
        return None

    def _prepare_members(self) -> None:
        """Give members the team's model and persistence context when absent."""
        for member in self.members:
            if self.share_model and member.model is None and self.model is not None:
                member.model = self.model
            if not self.share_context:
                continue
            if member.storage is None and self.storage is not None:
                member.storage = self.storage
            if member.user_id is None and self.user_id is not None:
                member.user_id = self.user_id
            if member.session_id is None and self.session_id is not None:
                member.session_id = f"{self.session_id}:{self._member_slug(member)}"

    @staticmethod
    def _member_slug(member: Agent) -> str:
        name = member.name or "member"
        return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "member"

    def _execute_member(self, member: Agent, task: str) -> str:
        """Run a member on a delegated task and record the interaction."""
        response = member.run(task)
        self._record_interaction(member, task, response.content, response.usage)
        return response.content

    async def _aexecute_member(self, member: Agent, task: str) -> str:
        """Async variant of `_execute_member`."""
        response = await member.arun(task)
        self._record_interaction(member, task, response.content, response.usage)
        return response.content

    def _record_interaction(
        self, member: Agent, task: str, response: str, usage: Usage | None
    ) -> None:
        self.member_interactions.append(
            MemberInteraction(
                member_name=member.name or "member",
                task=task,
                response=response,
                usage=usage,
            )
        )

    # -- run: dispatch by mode -----------------------------------------------

    def run(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        """Run the team using the configured coordination mode."""
        self._prepare_members()
        if self.mode == "coordinate":
            return super().run(
                message,
                context=context,
                response_format=response_format,
                stop_after_tool_call=stop_after_tool_call,
            )
        self._load_session()
        user_message = self._as_user_message(message)
        if self.mode == "route":
            return self._run_route(user_message, context)
        return self._run_collaborate(user_message, context)

    async def arun(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
        stop_after_tool_call: bool = False,
    ) -> RunResponse:
        """Async variant of `run`."""
        self._prepare_members()
        if self.mode == "coordinate":
            return await super().arun(
                message,
                context=context,
                response_format=response_format,
                stop_after_tool_call=stop_after_tool_call,
            )
        self._load_session()
        user_message = self._as_user_message(message)
        if self.mode == "route":
            return await self._arun_route(user_message, context)
        return await self._arun_collaborate(user_message, context)

    def run_stream(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
    ) -> Iterator[RunResponse]:
        """Streamed variant; only the coordinate mode streams events."""
        self._prepare_members()
        if self.mode == "coordinate":
            yield from super().run_stream(message, context=context, response_format=response_format)
            return
        yield self.run(message, context=context, response_format=response_format)

    async def arun_stream(
        self,
        message: str | Message,
        *,
        context: dict[str, Any] | None = None,
        response_format: ResponseFormat | None = None,
    ) -> AsyncIterator[RunResponse]:
        """Async variant of `run_stream`."""
        self._prepare_members()
        if self.mode == "coordinate":
            async for event in super().arun_stream(
                message, context=context, response_format=response_format
            ):
                yield event
            return
        yield await self.arun(message, context=context, response_format=response_format)

    # -- route mode -----------------------------------------------------------

    def _run_route(self, user_message: Message, context: dict[str, Any] | None) -> RunResponse:
        """Ask the leader for a structured route, then delegate to one member."""
        messages = self._build_messages(user_message, context)
        model = self.get_model()
        response = model.response(messages, response_format=TeamRoute)
        route = self._resolve_route(response)
        if route is None:
            return self._route_failure(messages, response, "the leader did not select a member")
        member = self.get_member(route.member)
        if member is None:
            return self._route_failure(messages, response, f"unknown member '{route.member}'")
        result = self._execute_member(member, route.task)
        self._record_session(messages)
        self._persist_session()
        return RunResponse(content=result, messages=messages, usage=response.usage)

    async def _arun_route(
        self, user_message: Message, context: dict[str, Any] | None
    ) -> RunResponse:
        """Async variant of `_run_route`."""
        messages = self._build_messages(user_message, context)
        model = self.get_model()
        response = await model.aresponse(messages, response_format=TeamRoute)
        route = self._resolve_route(response)
        if route is None:
            return self._route_failure(messages, response, "the leader did not select a member")
        member = self.get_member(route.member)
        if member is None:
            return self._route_failure(messages, response, f"unknown member '{route.member}'")
        result = await self._aexecute_member(member, route.task)
        self._record_session(messages)
        self._persist_session()
        return RunResponse(content=result, messages=messages, usage=response.usage)

    @staticmethod
    def _route_failure(
        messages: list[Message], response: ModelResponse, reason: str
    ) -> RunResponse:
        return RunResponse(
            content=f"Team route failed: {reason}.",
            messages=messages,
            usage=response.usage,
        )

    @staticmethod
    def _resolve_route(response: ModelResponse) -> TeamRoute | None:
        """Extract the route from structured output, then from raw content."""
        if isinstance(response.parsed, TeamRoute):
            return response.parsed
        if isinstance(response.parsed, dict):
            try:
                return TeamRoute.model_validate(response.parsed)
            except Exception:  # noqa: BLE001
                return None
        text = (response.content or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            return TeamRoute.model_validate(json.loads(text))
        except Exception:  # noqa: BLE001
            return None

    # -- collaborate mode -----------------------------------------------------

    def _run_collaborate(
        self, user_message: Message, context: dict[str, Any] | None
    ) -> RunResponse:
        """Run every member on the task, then have the leader synthesize."""
        task = user_message.get_content()
        member_results: list[tuple[str, str]] = []
        for member in self.members:
            answer = self._execute_member(member, task)
            member_results.append((member.name or "member", answer))
        messages = self._build_messages(user_message, context)
        messages.append(self._synthesis_message(task, member_results))
        model = self.get_model()
        response = model.response(messages)
        self._record_session(messages)
        self._persist_session()
        return RunResponse(content=response.content, messages=messages, usage=response.usage)

    async def _arun_collaborate(
        self, user_message: Message, context: dict[str, Any] | None
    ) -> RunResponse:
        """Async variant of `_run_collaborate`."""
        task = user_message.get_content()
        member_results: list[tuple[str, str]] = []
        for member in self.members:
            answer = await self._aexecute_member(member, task)
            member_results.append((member.name or "member", answer))
        messages = self._build_messages(user_message, context)
        messages.append(self._synthesis_message(task, member_results))
        model = self.get_model()
        response = await model.aresponse(messages)
        self._record_session(messages)
        self._persist_session()
        return RunResponse(content=response.content, messages=messages, usage=response.usage)

    @staticmethod
    def _synthesis_message(task: str, member_results: list[tuple[str, str]]) -> Message:
        combined = "\n\n".join(f"### {name}\n{answer}" for name, answer in member_results)
        return Message(
            role="user",
            content=(
                f"Task: {task}\n\n"
                "Each team member responded as follows:\n\n"
                f"{combined}\n\n"
                "Synthesize the responses into a single final answer for the user."
            ),
        )
