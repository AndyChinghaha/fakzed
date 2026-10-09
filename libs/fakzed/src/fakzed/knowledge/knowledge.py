"""Knowledge base: document ingestion, chunking, and retrieval (RAG)."""

import re
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fakzed.knowledge.embedder import Embedder, HashEmbedder
from fakzed.knowledge.vectordb import InMemoryVectorDb, VectorDb


class KnowledgeBase(BaseModel):
    """Ingests documents and answers queries by similarity search.

    Pipeline: split text into chunks → embed → index in a vector db →
    retrieve the top chunks for a query and inject them into the prompt.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    embedder: Embedder = Field(default_factory=HashEmbedder)
    vector_db: VectorDb = Field(default_factory=InMemoryVectorDb)
    chunk_size: int = 1000
    chunk_overlap: int = 100
    num_documents: int = 3

    def add_text(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        """Split and index a text document."""
        for chunk in self._chunk(text):
            self.vector_db.add(
                uuid.uuid4().hex,
                self.embedder.embed_query(chunk),
                {"text": chunk, **(metadata or {})},
            )

    def add_file(self, path: str, encoding: str = "utf-8") -> None:
        """Read a file and index its contents."""
        with open(path, encoding=encoding) as f:
            self.add_text(f.read(), metadata={"source": path})

    def search(self, query: str, limit: int | None = None) -> list[str]:
        """Return the most relevant chunk texts for a query."""
        limit = limit or self.num_documents
        results = self.vector_db.search(self.embedder.embed_query(query), limit=limit)
        return [r.payload.get("text", "") for r in results]

    def get_context_for_query(self, query: str, limit: int | None = None) -> str:
        """Format the top chunks as a prompt block for context injection."""
        docs = self.search(query, limit)
        if not docs:
            return ""
        return "<context>\n" + "\n---\n".join(docs) + "\n</context>"

    def _chunk(self, text: str) -> list[str]:
        """Split on paragraphs, window-slicing any paragraph over the limit."""
        paragraphs = re.split(r"\n\s*\n", text.strip())
        chunks: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= self.chunk_size:
                chunks.append(paragraph)
            else:
                start = 0
                while start < len(paragraph):
                    chunks.append(paragraph[start : start + self.chunk_size])
                    start += self.chunk_size - self.chunk_overlap
        return [c for c in chunks if c.strip()]
