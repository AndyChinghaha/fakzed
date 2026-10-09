"""Cookbook 03: memory and knowledge — user-level long-term memory plus RAG.

Run:  python cookbook/03_memory_and_knowledge.py
"""

from _cookbook_utils import scripted

from fakzed import (
    Agent,
    AgenticMemory,
    HashEmbedder,
    InMemoryStorage,
    InMemoryVectorDb,
    KnowledgeBase,
)

# ---- 1. user memory ---------------------------------------------------------
storage = InMemoryStorage()
memory = AgenticMemory(storage=storage, user_id="alice")
memory.add_memory("用户偏好：回答用中文，风格简洁，不要 emoji。")

memory_model = scripted("好的，我会用简洁的中文回答。")
agent = Agent(
    name="memory-bot",
    model=memory_model,
    instructions="你是个人助理。",
    memory=memory,  # injects add_to_memory / search_memory tools
    storage=storage,
    user_id="alice",
)
print("1) 记忆检索:", [m.content for m in memory.search_memories("偏好")])

# ---- 2. knowledge (RAG) -----------------------------------------------------
kb = KnowledgeBase(
    embedder=HashEmbedder(),  # local hash embedding, no key needed
    vector_db=InMemoryVectorDb(),
)
kb.add_text("fakzed 是一个轻量级 Agent 框架，模仿 agno 架构，核心是 Agent/Team/Workflow 三个原语。")
kb.add_text("fakzed 平台层叫 fakzed-server，提供 REST + SSE 接口和 Web 控制台。")

kb_model = scripted("fakzed 是模仿 agno 架构的轻量级 Agent 框架。")
rag_agent = Agent(
    name="kb-bot",
    model=kb_model,
    instructions="根据知识库回答问题，只回答知识库中有的内容。",
    knowledge=kb,  # relevant chunks injected into the prompt
)
print("2) 知识问答:", rag_agent.run("fakzed 是什么？").content)
