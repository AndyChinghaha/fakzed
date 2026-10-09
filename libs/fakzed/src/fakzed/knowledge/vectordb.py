"""Vector databases: pluggable similarity-search backends.

`InMemoryVectorDb` covers development; chroma/qdrant/pgvector land with the
platform layer behind the same `VectorDb` interface.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot  # embeddings are L2-normalized by the embedders


class SearchResult(BaseModel):
    """A single hit from a vector search."""

    id: str
    score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class VectorDb(BaseModel, ABC):
    """Similarity-search backend for document chunks."""

    @abstractmethod
    def add(self, doc_id: str, vector: list[float], payload: dict[str, Any] | None = None) -> None:
        """Index a document vector with optional payload."""

    @abstractmethod
    def search(self, vector: list[float], limit: int = 5) -> list[SearchResult]:
        """Return the most similar documents, best first."""

    @abstractmethod
    def clear(self) -> None:
        """Drop all indexed documents."""


class InMemoryVectorDb(VectorDb):
    """Plain-list backend with cosine similarity."""

    entries: list[dict[str, Any]] = Field(default_factory=list)

    def add(self, doc_id: str, vector: list[float], payload: dict[str, Any] | None = None) -> None:
        self.entries.append({"id": doc_id, "vector": vector, "payload": payload or {}})

    def search(self, vector: list[float], limit: int = 5) -> list[SearchResult]:
        scored = [
            SearchResult(id=e["id"], score=_cosine(vector, e["vector"]), payload=e["payload"])
            for e in self.entries
        ]
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def clear(self) -> None:
        self.entries = []
