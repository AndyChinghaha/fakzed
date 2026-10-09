"""Toolkit bundling tests: tools merge into the agent and instructions inject."""

from conftest import FakeModel

from fakzed import Agent
from fakzed.model import ModelResponse
from fakzed.tools import ToolKit, tool, url_read, web_search


def test_toolkit_tools_and_instructions_inject():
    @tool
    def lookup(term: str) -> str:
        """Look up a term."""
        return f"found {term}"

    toolkit = ToolKit(
        name="web",
        description="Web browsing tools.",
        instructions="Prefer the web tools for anything online.",
        tools=[url_read, web_search, lookup],
    )
    model = FakeModel(responses=[ModelResponse(content="done")])
    agent = Agent(model=model, toolkits=[toolkit])
    agent.run("search something")

    names = {t.name for t in agent._all_tools()}  # noqa: SLF001
    assert {"url_read", "web_search", "lookup"} <= names

    system = model.calls[-1]["messages"][0]
    assert "Toolkit: web" in system.content
    assert "Prefer the web tools" in system.content


def test_toolkit_without_instructions_injects_nothing():
    toolkit = ToolKit(name="math", tools=[])
    model = FakeModel(responses=[ModelResponse(content="ok")])
    agent = Agent(model=model, toolkits=[toolkit])
    agent.run("hi")
    system = model.calls[-1]["messages"][0]
    assert "Toolkit: math" not in system.content


def test_multiple_toolkits_merge():
    tk1 = ToolKit(name="a", tools=[])
    tk2 = ToolKit(name="b", tools=[url_read])
    agent = Agent(model=FakeModel(), toolkits=[tk1, tk2])
    names = {t.name for t in agent._all_tools()}  # noqa: SLF001
    assert "url_read" in names
