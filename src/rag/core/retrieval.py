import re
import logging

from rank_bm25 import BM25Okapi
from rag.core.vector_db import returnchroma
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

_bm25_cache = {}

def vector_search(query: str, subject_id: int, k: int = 10):
    vs = returnchroma()
    results = vs.similarity_search(query=query,filter={'subject_id':subject_id}, k=k)
    return results

def build_bm25_index(subject_id: int):
    vs = returnchroma()
    results = vs.get(where={"subject_id": subject_id})

    texts = results["documents"] or []
    metadatas = results["metadatas"] or []

    if not texts:
        return None, []

    tokenized = [tokenize(text) for text in texts]
    corpus = BM25Okapi(tokenized)

    documents = [
        Document(page_content=text, metadata=meta)
        for text, meta in zip(texts, metadatas)
    ]

    return corpus, documents

def get_bm25_index(subject_id: int):
    if subject_id not in _bm25_cache:
        logger.debug("bm25 index rebuild | subject=%s", subject_id)
        index = build_bm25_index(subject_id)
        if index[0] is None:
            # don't cache an empty corpus, or a later ingest never becomes searchable
            return index
        _bm25_cache[subject_id] = index
    else:
        logger.debug("bm25 cache hit | subject=%s", subject_id)
    return _bm25_cache[subject_id]

def invalidate_bm25_cache(subject_id: int):
    _bm25_cache.pop(subject_id, None)

def bm25_search(query: str, subject_id: int, k: int = 10):
    bm25, documents = get_bm25_index(subject_id)
    if bm25 is None:
        return []

    tokenized_query = tokenize(query)
    scores = bm25.get_scores(tokenized_query)
    ranked = sorted(zip(scores, documents), key=lambda x: x[0], reverse=True)
    return [doc for score, doc in ranked[:k]]

def tokenize(text: str):
    return re.findall(r'\w+', text.lower())

def _doc_key(doc: Document) -> str:
    if "chunk_id" in doc.metadata:
        return str(doc.metadata["chunk_id"])
    return str(hash(doc.page_content))

def hybrid_search(query: str, subject_id: int, k: int = 10, fetch_k: int = 20, rrf_k: int = 60):

    vec_docs = vector_search(query, subject_id, k=fetch_k)
    bm25_docs = bm25_search(query, subject_id, k=fetch_k)

    rrf_scores = {}
    doc_map = {}

    for rank, doc in enumerate(vec_docs, start=1):
        key = _doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (rrf_k + rank))

    for rank, doc in enumerate(bm25_docs, start=1):
        key = _doc_key(doc)
        doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (rrf_k + rank))

    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    return [doc_map[key] for key in sorted_keys[:k]]
