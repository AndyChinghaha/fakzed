"""M3 feature tests: summarization, agent state, context, and knowledge."""

from conftest import FakeModel

from fakzed import Agent, KnowledgeBase, SqliteStorage, TimeProvider
from fakzed.model import ModelResponse


def test_session_summarization_trims_history_and_injects_summary():
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="答案1"),
        ModelResponse(content="答案2"),
        ModelResponse(content="- 用户问了两个问题"),  # summarization response
        ModelResponse(content="答案3"),
    )
    agent = Agent(
        model=model,
        session_id="s-sum",
        summarize=True,
        summarize_threshold=2,
        summarize_keep=2,
        num_history_runs=100,
    )
    agent.run("问题1")
    assert agent.session is not None
    assert len(agent.session.messages) == 2  # no trigger yet
    assert agent.session.summary is None

    agent.run("问题2")
    assert agent.session.summary == "- 用户问了两个问题"
    assert len(agent.session.messages) == 2  # trimmed to summarize_keep

    agent.run("问题3")
    # the summary is injected into the third run's prompt
    sent = next(
        c["messages"]
        for c in reversed(model.calls)
        if any(m.role == "user" and m.content == "问题3" for m in c["messages"])
    )
    summary_messages = [m for m in sent if m.role == "system" and "summary so far" in m.content]
    assert len(summary_messages) == 1
    assert "用户问了两个问题" in summary_messages[0].content


def test_agent_state_persists_and_restores(tmp_path):
    storage = SqliteStorage(db_path=str(tmp_path / "state.db"))
    agent = Agent(
        model=FakeModel(responses=[ModelResponse(content="ok")]),
        session_id="s-state",
        storage=storage,
    )
    agent.update_state(plan="research", step=1)
    agent.run("你好")

    restored = Agent(model=FakeModel(), session_id="s-state", storage=storage)
    restored._load_session()
    assert restored.agent_state == {"plan": "research", "step": 1}

    # stored row also carries the state
    row = storage.read_session("s-state")
    assert row.session_data["agent_state"] == {"plan": "research", "step": 1}


def test_state_tools_read_and_update():
    agent = Agent(model=FakeModel())
    tool_map = agent._tool_map()
    assert {"get_agent_state", "update_agent_state"} <= set(tool_map)

    result = tool_map["update_agent_state"].call({"state": {"theme": "dark"}})
    assert "updated" in result
    assert agent.agent_state == {"theme": "dark"}

    state_json = tool_map["get_agent_state"].call({})
    assert "dark" in state_json


def test_agent_state_tools_are_disabled_by_flag():
    agent = Agent(model=FakeModel(), add_state_tools=False)
    assert "get_agent_state" not in agent._tool_map()


def test_context_template_rendering():
    model = FakeModel(responses=[ModelResponse(content="你好 Alice！")])
    agent = Agent(
        model=model,
        name="greeter",
        instructions="向 {{user_name}} 问好，今天是 {{date}}。",
    )
    agent.run("打招呼", context={"user_name": "Alice", "date": "2026-09-22"})
    system = model.calls[-1]["messages"][0]
    assert "Alice" in system.content
    assert "2026-09-22" in system.content
    assert "{{" not in system.content


def test_context_provider_injects_dynamic_context():
    model = FakeModel(responses=[ModelResponse(content="ok")])
    agent = Agent(model=model, context_providers=[TimeProvider(timezone_name="Asia/Shanghai")])
    agent.run("现在几点")
    system_messages = [m for m in model.calls[-1]["messages"] if m.role == "system"]
    assert any("Current time" in m.content for m in system_messages)


def test_knowledge_injected_into_prompt():
    model = FakeModel(responses=[ModelResponse(content="Faker 使用 Zed。")])
    kb = KnowledgeBase()
    kb.add_text("Faker 在 2015 年世界赛用 Zed 打出双劫名场面。")
    kb.add_text("披萨需要发酵面团。")
    agent = Agent(model=model, knowledge=kb)
    agent.run("Zed 是哪个选手的成名英雄？")
    context_blocks = [m for m in model.calls[-1]["messages"] if "<context>" in m.content]
    assert len(context_blocks) == 1
    assert "Faker" in context_blocks[0].content


def test_knowledge_skipped_when_flag_off():
    model = FakeModel(responses=[ModelResponse(content="ok")])
    kb = KnowledgeBase()
    kb.add_text("Faker 用 Zed。")
    agent = Agent(model=model, knowledge=kb, add_knowledge_to_context=False)
    agent.run("查询")
    assert not any("<context>" in m.content for m in model.calls[-1]["messages"])


def test_summary_survives_sqlite_roundtrip(tmp_path):
    storage = SqliteStorage(db_path=str(tmp_path / "sum.db"))
    model = FakeModel()
    model.enqueue(
        ModelResponse(content="a1"), ModelResponse(content="a2"), ModelResponse(content="摘要")
    )
    agent = Agent(
        model=model,
        session_id="s-rt",
        storage=storage,
        summarize=True,
        summarize_threshold=2,
        summarize_keep=2,
    )
    agent.run("q1")
    agent.run("q2")

    row = storage.read_session("s-rt")
    assert row.summary == "摘要"
    assert len(row.messages) == 2
