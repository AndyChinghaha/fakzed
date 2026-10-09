"""Embedders: turn text into vectors.

Plug-in style: `HashEmbedder` runs fully locally (no API key, deterministic)
for development and tests; `OpenAIEmbedder` targets production embeddings.
"""

import hashlib
import math
import os
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, PrivateAttr


class Embedder(BaseModel, ABC):
    """Embeds texts into dense vectors for similarity search."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, one vector per text."""

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        return self.embed([text])[0]


class HashEmbedder(Embedder):
    """Local character n-gram hashing embedder.

    No network or API key required. Not semantic — same-character-similarity
    only — but exercises the full RAG pipeline and is deterministic.
    """

    dim: int = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            chars = text.lower()
            for i in range(len(chars) - 2):
                gram = chars[i : i + 3]
                digest = hashlib.md5(gram.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:2], "big") % self.dim
                vec[idx] += 1.0
            norm = math.sqrt(sum(x * x for x in vec))
            if norm > 0:
                vec = [x / norm for x in vec]
            vectors.append(vec)
        return vectors


class OpenAIEmbedder(Embedder):
    """OpenAI-compatible embeddings API (any provider with an /embeddings endpoint)."""

    id: str = "text-embedding-3-small"
    api_key: str | None = None
    base_url: str | None = None
    _client: Any = PrivateAttr(default=None)

    def get_api_key(self) -> str | None:
        return self.api_key or os.getenv("OPENAI_API_KEY")

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.get_api_key(), base_url=self.base_url)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._get_client().embeddings.create(model=self.id, input=texts)
        return [item.embedding for item in response.data]
