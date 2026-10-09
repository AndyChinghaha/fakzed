"""Tests for Skills injection and team delegation (fake model)."""

from conftest import FakeModel

from fakzed.agent import Agent
from fakzed.model import ModelResponse, ToolCall
from fakzed.skills import Skill
from fakzed.tools import tool


def make_agent(model: FakeModel) -> Agent:
    return Agent(name="test agent", model=model)


def test_skill_injected_into_system_prompt() -> None:
    skill = Skill(
        name="legal-review",
        description="Reviews contracts.",
        instructions="Always flag missing termination clauses.",
    )
    agent = make_agent(FakeModel())
    agent.skills = [skill]

    prompt = agent.get_system_prompt()

    assert "## legal-review" in prompt
    assert "flag missing termination clauses" in prompt


def test_multiple_skills_injected() -> None:
    skills = [
        Skill(name="a", instructions="First skill."),
        Skill(name="b", instructions="Second skill."),
    ]
    agent = make_agent(FakeModel())
    agent.skills = skills

    prompt = agent.get_system_prompt()

    assert "## a" in prompt
    assert "## b" in prompt
    assert "Second skill." in prompt


def test_no_skill_no_injection() -> None:
    agent = make_agent(FakeModel())
    assert agent.get_system_prompt() is None or "##" not in agent.get_system_prompt()


def test_transfer_tools_built_from_team() -> None:
    member = Agent(name="researcher", model=FakeModel())
    lead = Agent(name="lead", model=FakeModel(), team=[member])

    transfer_tools = lead.get_transfer_tools()

    assert transfer_tools is not None and len(transfer_tools) == 1
    transfer = transfer_tools[0]
    assert transfer.name == "transfer_to_researcher"
    assert "researcher" in transfer.description
    # the closure signature only exposes the task argument
    assert list(transfer.parameters.get("properties", {})) == ["task"]


def test_transfer_tool_runs_member_agent() -> None:
    member_model = FakeModel()
    member_model.enqueue(ModelResponse(content="answer from researcher"))
    member = Agent(name="researcher", model=member_model)
    lead = Agent(name="lead", model=FakeModel(), team=[member])

    transfer_tool = lead.get_transfer_tools()[0]
    result = transfer_tool.call({"task": "look this up"})

    assert result == "answer from researcher"
    # the member received the delegated task
    assert member_model.calls[0]["messages"][-1].content == "look this up"


def test_lead_delegates_and_finalizes() -> None:
    member_model = FakeModel()
    member_model.enqueue(ModelResponse(content="the capital is Paris"))
    member = Agent(name="geo expert", model=member_model)

    lead_model = FakeModel()
    lead_model.enqueue(
        ModelResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="c1", name="transfer_to_geo_expert", arguments={"task": "capital of France?"}
                )
            ],
        ),
        ModelResponse(content="The capital of France is Paris."),
    )
    lead = Agent(name="lead", model=lead_model, team=[member])

    result = lead.run("what is the capital of France?")

    assert result.content == "The capital of France is Paris."
    # tool message carries the member's answer back to the lead
    tool_message = result.messages[3]
    assert tool_message.role == "tool"
    assert tool_message.content == "the capital is Paris"
    # the model saw both the member transfer tool and no regular tools
    sent_tools = lead_model.calls[0]["tools"]
    assert sent_tools is not None and sent_tools[0].name == "transfer_to_geo_expert"


def test_team_prompt_mentions_members() -> None:
    lead = Agent(
        name="lead",
        model=FakeModel(),
        team=[Agent(name="writer", model=FakeModel()), Agent(name="critic", model=FakeModel())],
    )
    prompt = lead.get_system_prompt()

    assert "part of a team" in prompt
    assert "writer" in prompt
    assert "critic" in prompt


def test_own_tools_and_transfer_tools_coexist() -> None:
    @tool
    def lookup(term: str) -> str:
        """Look up a term."""
        return f"found {term}"

    lead = Agent(
        name="lead",
        model=FakeModel(),
        tools=[lookup],
        team=[Agent(name="helper", model=FakeModel())],
    )

    names = [t.name for t in lead._all_tools()]  # noqa: SLF001

    # own and transfer tools come first, then the built-in state tools
    assert names[:2] == ["lookup", "transfer_to_helper"]
    assert {"get_agent_state", "update_agent_state"} <= set(names[2:])
