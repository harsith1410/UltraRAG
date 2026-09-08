"""Near-duplicate detection: catch re-uploads of the same material under a new filename."""
import numpy as np

from rag.core.vector_db import embedding, returnchroma

SIMILARITY_THRESHOLD = 0.95
MATCH_RATIO = 0.8
SAMPLE_SIZE = 8


class NearDuplicate(Exception):
    def __init__(self, source: str, similarity: float, matched: int, sampled: int):
        self.source = source
        self.similarity = similarity
        self.matched = matched
        self.sampled = sampled
        super().__init__(
            f"{matched} of {sampled} sampled chunks closely match '{source}' "
            f"(mean similarity {similarity:.2f})"
        )


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _sample(items: list, size: int) -> list:
    """Evenly spaced sample, so we look at the whole document rather than just the start."""
    if len(items) <= size:
        return items
    step = len(items) / size
    return [items[int(i * step)] for i in range(size)]


def find_near_duplicate(chunks: list, subject_id: int,
                        threshold: float = SIMILARITY_THRESHOLD,
                        match_ratio: float = MATCH_RATIO):
    """Return NearDuplicate details if these chunks largely restate an existing document."""
    if not chunks:
        return None

    vs = returnchroma()
    existing = vs.get(where={"subject_id": subject_id}, include=["embeddings", "metadatas"])

    stored = np.asarray(existing.get("embeddings") if existing.get("embeddings") is not None else [])
    if stored.size == 0:
        return None

    metadatas = existing.get("metadatas") or []
    sampled = _sample(chunks, SAMPLE_SIZE)
    queries = np.asarray(embedding.embed_documents([c.page_content for c in sampled]))

    sims = _normalize(queries) @ _normalize(stored).T
    best_idx = sims.argmax(axis=1)
    best_sim = sims.max(axis=1)

    hits = best_sim >= threshold
    matched = int(hits.sum())
    if matched / len(sampled) < match_ratio:
        return None

    sources = [
        (metadatas[i] or {}).get("source", "unknown")
        for i in best_idx[hits]
        if i < len(metadatas)
    ]
    source = max(set(sources), key=sources.count) if sources else "unknown"

    return NearDuplicate(
        source=source,
        similarity=float(best_sim[hits].mean()),
        matched=matched,
        sampled=len(sampled),
    )
