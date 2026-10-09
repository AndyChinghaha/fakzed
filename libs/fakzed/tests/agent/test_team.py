"""Team primitive tests: coordination, routing, collaboration, nesting."""

import asyncio

from conftest import FakeModel

from fakzed import Agent, Team
from fakzed.agent import TeamRoute
from fakzed.model import ModelResponse, ToolCall
from fakzed.storage import InMemoryStorage


def make_member(name: str, answer: str, description: str | None = None) -> tuple[Agent, FakeModel]:
    model = FakeModel()
    model.enqueue(ModelResponse(content=answer))
    return Agent(name=name, description=description, model=model), model


# -- 5.1 + 5.3: coordinate mode delegates via transfer tools -----------------


def test_coordinate_mode_delegates_and_records_interactions() -> None:
    researcher, researcher_model = make_member("researcher", "researched facts")
    leader_model = FakeModel()
    leader_model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(id="c1", name="transfer_to_researcher", arguments={"task": "find facts"})
            ],
        ),
        ModelResponse(content="Here is the final answer."),
    )
    team = Team(name="lead", model=leader_model, members=[researcher])

    response = team.run("investigate X")

    assert response.content == "Here is the final answer."
    # the interaction history records the delegation
    assert len(team.member_interactions) == 1
    interaction = team.member_interactions[0]
    assert interaction.member_name == "researcher"
    assert interaction.task == "find facts"
    assert interaction.response == "researched facts"
    # the member received the delegated task as its user message
    member_last = researcher_model.calls[-1]["messages"]
    assert member_last[-1].content == "find facts"


def test_team_leader_prompt_lists_member_descriptions() -> None:
    team = Team(
        name="lead",
        model=FakeModel(),
        members=[
            Agent(name="researcher", description="finds facts"),
            Agent(name="writer", description="writes prose"),
        ],
    )

    prompt = team.get_system_prompt() or ""

    assert "part of a team" in prompt
    assert "researcher: finds facts" in prompt
    assert "writer: writes prose" in prompt


def test_get_member_is_case_insensitive() -> None:
    member = Agent(name="Researcher", model=FakeModel())
    team = Team(name="lead", model=FakeModel(), members=[member])

    assert team.get_member("researcher") is member
    assert team.get_member("  RESEARCHER ") is member
    assert team.get_member("ghost") is None


# -- 5.2: route mode ----------------------------------------------------------


def test_route_mode_selects_member_via_structured_route() -> None:
    researcher, _ = make_member("researcher", "found the facts")
    leader_model = FakeModel()
    leader_model.enqueue(
        ModelResponse(
            content="routing",
            parsed=TeamRoute(member="Researcher", task="look it up", reasoning="needs research"),
        )
    )
    team = Team(name="lead", model=leader_model, mode="route", members=[researcher])

    response = team.run("what is X?")

    assert response.content == "found the facts"
    assert len(team.member_interactions) == 1
    assert team.member_interactions[0].task == "look it up"
    # the leader saw the member roster in its context
    leader_messages = leader_model.calls[-1]["messages"]
    assert any("researcher" in m.content for m in leader_messages if m.role == "system")


def test_route_mode_falls_back_to_json_content() -> None:
    researcher, _ = make_member("researcher", "dug up the answer")
    leader_model = FakeModel()
    leader_model.enqueue(
        ModelResponse(content='```json\n{"member": "researcher", "task": "dig"}\n```')
    )
    team = Team(name="lead", model=leader_model, mode="route", members=[researcher])

    response = team.run("dig please")

    assert response.content == "dug up the answer"
    assert team.member_interactions[0].task == "dig"


def test_route_mode_unknown_member_fails_gracefully() -> None:
    leader_model = FakeModel()
    leader_model.enqueue(ModelResponse(parsed=TeamRoute(member="ghost", task="anything")))
    team = Team(name="lead", model=leader_model, mode="route", members=[])

    response = team.run("do something")

    assert "unknown member 'ghost'" in response.content
    assert team.member_interactions == []


def test_route_mode_without_route_fails_gracefully() -> None:
    leader_model = FakeModel()
    leader_model.enqueue(ModelResponse(content="I cannot decide."))
    team = Team(name="lead", model=leader_model, mode="route", members=[])

    response = team.run("do something")

    assert "Team route failed" in response.content
    assert team.member_interactions == []


# -- 5.4: collaborate mode -----------------------------------------------------


def test_collaborate_mode_runs_all_members_then_synthesizes() -> None:
    researcher, _ = make_member("researcher", "fact A")
    writer, _ = make_member("writer", "prose B")
    leader_model = FakeModel()
    leader_model.enqueue(ModelResponse(content="combined answer"))
    team = Team(
        name="lead",
        model=leader_model,
        mode="collaborate",
        members=[researcher, writer],
    )

    response = team.run("make a report")

    assert response.content == "combined answer"
    assert [i.member_name for i in team.member_interactions] == ["researcher", "writer"]
    # the leader synthesized over both member answers
    synthesis = leader_model.calls[-1]["messages"][-1].content
    assert "fact A" in synthesis
    assert "prose B" in synthesis


# -- 5.5: team context sharing -------------------------------------------------


def test_team_shares_storage_session_and_user_with_members() -> None:
    storage = InMemoryStorage()
    researcher, researcher_model = make_member("researcher", "facts")
    leader_model = FakeModel()
    leader_model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(id="c1", name="transfer_to_researcher", arguments={"task": "dig"})
            ],
        ),
        ModelResponse(content="final"),
    )
    team = Team(
        name="lead",
        model=leader_model,
        members=[researcher],
        storage=storage,
        session_id="team-session",
        user_id="user-1",
    )

    team.run("hello")

    assert researcher.storage is storage
    assert researcher.user_id == "user-1"
    assert researcher.session_id == "team-session:researcher"
    assert researcher_model.calls[-1]["messages"][-1].content == "dig"
    # the member's own sub-session was persisted to the shared storage
    assert storage.read_session("team-session:researcher") is not None


def test_team_shares_model_with_members() -> None:
    shared_model = FakeModel()
    member = Agent(name="researcher")
    team = Team(name="lead", model=shared_model, members=[member])

    team._prepare_members()

    assert member.model is shared_model


# -- 5.6: nested teams ----------------------------------------------------------


def test_nested_team_teams_can_be_members() -> None:
    worker, worker_model = make_member("worker", "work done")
    inner_leader = FakeModel()
    inner_leader.enqueue(ModelResponse(parsed=TeamRoute(member="worker", task="do the work")))
    inner = Team(name="inner team", model=inner_leader, mode="route", members=[worker])

    outer_leader = FakeModel()
    outer_leader.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="c1",
                    name="transfer_to_inner_team",
                    arguments={"task": "get the work done"},
                )
            ],
        ),
        ModelResponse(content="everything is done"),
    )
    outer = Team(name="outer", model=outer_leader, members=[inner])

    response = outer.run("finish the job")

    assert response.content == "everything is done"
    # outer team recorded delegating to the inner team
    assert outer.member_interactions[0].member_name == "inner team"
    assert outer.member_interactions[0].response == "work done"
    # inner team recorded delegating to the worker
    assert inner.member_interactions[0].member_name == "worker"
    assert worker_model.calls[-1]["messages"][-1].content == "do the work"


# -- async and streaming variants ---------------------------------------------


def test_route_mode_async() -> None:
    async def main() -> str:
        researcher, _ = make_member("researcher", "async facts")
        leader_model = FakeModel()
        leader_model.enqueue(ModelResponse(parsed=TeamRoute(member="researcher", task="look")))
        team = Team(name="lead", model=leader_model, mode="route", members=[researcher])
        response = await team.arun("async question")
        return response.content

    assert asyncio.run(main()) == "async facts"


def test_collaborate_mode_async() -> None:
    async def main() -> tuple[str, int]:
        researcher, _ = make_member("researcher", "async A")
        writer, _ = make_member("writer", "async B")
        leader_model = FakeModel()
        leader_model.enqueue(ModelResponse(content="async combined"))
        team = Team(
            name="lead",
            model=leader_model,
            mode="collaborate",
            members=[researcher, writer],
        )
        response = await team.arun("async report")
        return response.content, len(team.member_interactions)

    content, interactions = asyncio.run(main())
    assert content == "async combined"
    assert interactions == 2


def test_coordinate_mode_streams_events() -> None:
    leader_model = FakeModel()
    leader_model.enqueue(ModelResponse(content="streamed final"))
    team = Team(name="lead", model=leader_model, members=[])

    events = list(team.run_stream("stream please"))

    assert events[-1].event == "complete"
    assert events[-1].content == "streamed final"


def test_route_mode_stream_returns_single_complete_event() -> None:
    researcher, _ = make_member("researcher", "route stream answer")
    leader_model = FakeModel()
    leader_model.enqueue(ModelResponse(parsed=TeamRoute(member="researcher", task="go")))
    team = Team(name="lead", model=leader_model, mode="route", members=[researcher])

    events = list(team.run_stream("route stream"))

    assert len(events) == 1
    assert events[0].event == "complete"
    assert events[0].content == "route stream answer"
