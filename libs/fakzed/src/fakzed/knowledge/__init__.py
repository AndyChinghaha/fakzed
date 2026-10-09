"""Knowledge system: document ingestion and retrieval (RAG)."""

from fakzed.knowledge.embedder import Embedder, HashEmbedder, OpenAIEmbedder
from fakzed.knowledge.knowledge import KnowledgeBase
from fakzed.knowledge.vectordb import InMemoryVectorDb, SearchResult, VectorDb

__all__ = [
    "KnowledgeBase",
    "Embedder",
    "HashEmbedder",
    "OpenAIEmbedder",
    "VectorDb",
    "InMemoryVectorDb",
    "SearchResult",
]
