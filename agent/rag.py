import math
import time

from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

_CACHE_TTL = 1800  # seconds — rebuild embeddings after 30 minutes
_EMBEDDING_MODEL = "text-embedding-004"
_model: TextEmbeddingModel | None = None


def _get_model() -> TextEmbeddingModel:
    """Return the shared TextEmbeddingModel instance, initialising it on first call."""
    global _model
    if _model is None:
        _model = TextEmbeddingModel.from_pretrained(_EMBEDDING_MODEL)
    return _model


class PropertyRAG:
    """In-memory vector store for property similarity search.

    Converts property dicts to plain text, embeds them with Vertex AI, and
    retrieves the closest matches for a user query using cosine similarity.
    Embeddings are cached for _CACHE_TTL seconds before being rebuilt.
    """

    def __init__(self):
        self._properties: list[dict] = []
        self._embeddings: list[list[float]] = []
        self._cached_at: float = 0.0

    def is_stale(self) -> bool:
        """Return True if embeddings are missing or older than the cache TTL."""
        return not self._embeddings or (time.time() - self._cached_at > _CACHE_TTL)

    def build(self, properties: list[dict]) -> None:
        """Embed all properties and store them for later search."""
        if not properties:
            return
        model = _get_model()
        texts = [_property_to_text(p) for p in properties]
        inputs = [TextEmbeddingInput(t, "RETRIEVAL_DOCUMENT") for t in texts]
        self._embeddings = [e.values for e in model.get_embeddings(inputs)]
        self._properties = properties
        self._cached_at = time.time()

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Return the top_k properties most similar to the query string."""
        if not self._embeddings:
            return self._properties[:top_k]
        model = _get_model()
        query_emb = model.get_embeddings([TextEmbeddingInput(query, "RETRIEVAL_QUERY")])[0].values
        ranked = sorted(
            zip(self._embeddings, self._properties),
            key=lambda x: _cosine(query_emb, x[0]),
            reverse=True,
        )
        return [p for _, p in ranked[:top_k]]


def _property_to_text(p: dict) -> str:
    """Serialise a property dict to a plain text string used for embedding."""
    amenities = ", ".join(a["amenity"]["name"] for a in p.get("amenities", []))
    rooms = ", ".join(
        f"{r.get('name', r.get('type', ''))} ({r.get('sizeSqm', '')} sqm)"
        for r in p.get("rooms", [])
    )
    parts = [
        p.get("title", ""),
        p.get("description", ""),
        p.get("type", ""),
        p.get("city", ""),
        f"{p.get('sizeSqm', '')} sqm" if p.get("sizeSqm") else "",
        f"{p.get('maxOccupants', '')} occupants" if p.get("maxOccupants") else "",
        f"{p.get('pricePerMonth', '')} per month" if p.get("pricePerMonth") else "",
        "furnished" if p.get("isFurnished") else "unfurnished",
        amenities,
        rooms,
    ]
    return ". ".join(part for part in parts if part)


def _cosine(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / mag if mag else 0.0
