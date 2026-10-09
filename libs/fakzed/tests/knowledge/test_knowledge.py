"""Knowledge system tests: embedders, vector db, and the knowledge base."""

from fakzed.knowledge import HashEmbedder, InMemoryVectorDb, KnowledgeBase


def test_hash_embedder_is_deterministic_and_normalized():
    embedder = HashEmbedder(dim=64)
    v1 = embedder.embed_query("faker zed outplay")
    v2 = embedder.embed_query("faker zed outplay")
    assert v1 == v2
    assert len(v1) == 64
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_hash_embedder_different_texts_differ():
    embedder = HashEmbedder(dim=64)
    v1 = embedder.embed_query("英雄联盟中单选手")
    v2 = embedder.embed_query("完全无关的内容啊")
    assert v1 != v2


def test_in_memory_vector_db_ranks_by_similarity():
    db = InMemoryVectorDb()
    embedder = HashEmbedder(dim=64)
    db.add("a", embedder.embed_query("faker zed outplay"), {"text": "A"})
    db.add("b", embedder.embed_query("totally different words"), {"text": "B"})
    db.add("c", embedder.embed_query("faker zed play"), {"text": "C"})
    results = db.search(embedder.embed_query("faker zed outplay"), limit=3)
    assert results[0].id == "a"
    assert results[0].payload["text"] == "A"
    assert results[0].score > results[1].score


def test_in_memory_vector_db_clear():
    db = InMemoryVectorDb()
    db.add("a", [1.0, 0.0], {"text": "A"})
    db.clear()
    assert db.search([1.0, 0.0]) == []


def test_knowledge_base_search_returns_relevant_text():
    kb = KnowledgeBase()
    kb.add_text("Faker is a League of Legends mid laner known for his Zed play.")
    kb.add_text("Cooking pasta requires boiling water and salt.")
    results = kb.search("Zed mid laner", limit=1)
    assert results
    assert "Faker" in results[0]


def test_knowledge_base_context_block_format():
    kb = KnowledgeBase()
    kb.add_text("The Zed outplay happened at Worlds.")
    block = kb.get_context_for_query("Zed outplay", limit=1)
    assert block.startswith("<context>")
    assert "Zed outplay happened" in block
    assert block.endswith("</context>")


def test_knowledge_base_returns_empty_context_without_docs():
    kb = KnowledgeBase()
    assert kb.get_context_for_query("anything") == ""


def test_knowledge_base_chunks_long_paragraphs():
    kb = KnowledgeBase(chunk_size=100, chunk_overlap=20)
    text = "长文本" * 60  # 180 chars, one paragraph
    kb.add_text(text)
    chunks = kb.search("长文本", limit=50)
    assert len(chunks) >= 2
    assert all(0 < len(c) <= 100 for c in chunks)


def test_knowledge_base_add_file(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("Faker won three world championships.", encoding="utf-8")
    kb = KnowledgeBase()
    kb.add_file(str(path))
    results = kb.search("Faker championships")
    assert "Faker" in results[0]
