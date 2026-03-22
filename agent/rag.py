import math
import time

from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

_CACHE_TTL = 300  # seconds — rebuild embeddings after 5 minutes
_EMBEDDING_MODEL = "text-embedding-004"


class PropertyRAG:
    def __init__(self):
        self._properties: list[dict] = []
        self._embeddings: list[list[float]] = []
        self._cached_at: float = 0.0

    def is_stale(self) -> bool:
        return not self._embeddings or (time.time() - self._cached_at > _CACHE_TTL)

    def build(self, properties: list[dict]) -> None:
        if not properties:
            return
        model = TextEmbeddingModel.from_pretrained(_EMBEDDING_MODEL)
        texts = [_property_to_text(p) for p in properties]
        inputs = [TextEmbeddingInput(t, "RETRIEVAL_DOCUMENT") for t in texts]
        self._embeddings = [e.values for e in model.get_embeddings(inputs)]
        self._properties = properties
        self._cached_at = time.time()

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not self._embeddings:
            return self._properties[:top_k]
        model = TextEmbeddingModel.from_pretrained(_EMBEDDING_MODEL)
        query_emb = model.get_embeddings([TextEmbeddingInput(query, "RETRIEVAL_QUERY")])[0].values
        ranked = sorted(
            zip(self._embeddings, self._properties),
            key=lambda x: _cosine(query_emb, x[0]),
            reverse=True,
        )
        return [p for _, p in ranked[:top_k]]


def _property_to_text(p: dict) -> str:
    amenities = ", ".join(a["amenity"]["name"] for a in p.get("amenities", []))
    return (
        f"{p.get('title', '')}. {p.get('description', '')} "
        f"Type: {p.get('type', '')}. City: {p.get('city', '')}. "
        f"Size: {p.get('sizeSqm', '')} sqm. Max occupants: {p.get('maxOccupants', '')}. "
        f"Price: {p.get('pricePerMonth', '')} per month. "
        f"Furnished: {p.get('isFurnished', '')}. Amenities: {amenities}."
    )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / mag if mag else 0.0
