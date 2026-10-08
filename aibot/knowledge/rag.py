"""
Semantic ranking of tool results with embeddings (RAG).

Every search ranks its own results, so one user's filters never leak into another
user's answer. Embeddings are cached by text content, so unchanged items are not
embedded again and changed items are picked up automatically.
"""
import hashlib
import logging
import math
from collections import OrderedDict
from typing import Any

from aibot.llm import LLMProvider

logger = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    magnitude = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / magnitude if magnitude else 0.0


class EmbeddingCache:
    """Least-recently-used cache of document embeddings keyed by model and text."""

    def __init__(self, max_items: int = 5000) -> None:
        self.max_items = max_items
        self._items: OrderedDict[str, list[float]] = OrderedDict()

    @staticmethod
    def key(provider: str, model: str, text: str) -> str:
        return hashlib.sha256(f"{provider}\0{model}\0{text}".encode()).hexdigest()

    def get(self, key: str) -> list[float] | None:
        vector = self._items.get(key)
        if vector is not None:
            self._items.move_to_end(key)
        return vector

    def put(self, key: str, vector: list[float]) -> None:
        self._items[key] = vector
        self._items.move_to_end(key)
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)


class Ranker:
    """Ranks items by similarity to a query."""

    def __init__(self, cache: EmbeddingCache | None = None) -> None:
        self.cache = cache or EmbeddingCache()

    async def rank(
        self,
        provider: LLMProvider,
        model: str | None,
        query: str,
        items: list[Any],
        texts: list[str],
        top_k: int,
    ) -> list[Any]:
        """Return the `top_k` items whose texts are closest to the query.

        Falls back to the first `top_k` items if embedding fails, so the agent can
        still answer.
        """
        if len(items) <= top_k:
            return items
        model_key = model or getattr(provider, "embedding_model", "") or ""
        try:
            keys = [self.cache.key(provider.name, model_key, text) for text in texts]
            missing = [i for i, key in enumerate(keys) if self.cache.get(key) is None]
            if missing:
                vectors = await provider.embed([texts[i] for i in missing], model=model, task="document")
                for i, vector in zip(missing, vectors):
                    self.cache.put(keys[i], vector)
            documents = [self.cache.get(key) or [] for key in keys]
            query_vector = (await provider.embed([query], model=model, task="query"))[0]
        except Exception as exc:
            logger.warning("Embedding failed, returning unranked results: %s", exc)
            return items[:top_k]

        order = sorted(range(len(items)), key=lambda i: cosine(query_vector, documents[i]), reverse=True)
        return [items[i] for i in order[:top_k]]
