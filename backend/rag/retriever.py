"""In-memory embedding index over rag/catalog.py for reuse-detection search.

Deliberately dependency-light (numpy only, no vector DB) since the catalog
is ~10 rows — this is a real embedding-based cosine similarity search, just
sized for a hackathon prototype rather than a production vector store.

Concept-aware: the query text is expanded with the entity's resolved
canonical clinical concept and its synonyms (see clinical_concepts.py) before
embedding, and candidates sharing that concept get a small score boost. This
lets "heart attack" retrieve a Condition-tagged asset even when the catalog
text never uses that literal phrase.
"""
import logging
from typing import Optional

import numpy as np

from llm_client import get_client, EMBEDDING_DEPLOYMENT
from clinical_concepts import expand_query_text
from rag.catalog import CATALOG

logger = logging.getLogger(__name__)

_catalog_vectors: Optional[np.ndarray] = None

CONCEPT_MATCH_BOOST_PCT = 8  # added to similarity_pct when catalog concept matches


def _embed(texts: list[str]) -> Optional[np.ndarray]:
    client = get_client()
    if client is None:
        return None
    try:
        response = client.embeddings.create(input=texts, model=EMBEDDING_DEPLOYMENT)
        return np.array([d.embedding for d in response.data], dtype=np.float32)
    except Exception as e:
        logger.error(f"Embedding call failed: {e}")
        return None


def _ensure_index() -> Optional[np.ndarray]:
    global _catalog_vectors
    if _catalog_vectors is None:
        texts = [f"{c['name']}: {c['definition']} (clinical concept: {c['concept']})" for c in CATALOG]
        _catalog_vectors = _embed(texts)
    return _catalog_vectors


def best_match(
    entity_name: str, entity_definition: str, clinical_concept: str = "Other", industry: str = "healthcare"
) -> Optional[dict]:
    """Return the catalog row closest to the given entity, restricted to rows
    from the same industry, with a similarity percentage, or None if no rows
    exist for that industry or the index/embeddings aren't available.
    Candidates that share the entity's canonical concept are boosted so
    concept-matching outranks purely literal text similarity."""
    candidate_idx = [i for i, c in enumerate(CATALOG) if c["industry"] == industry]
    if not candidate_idx:
        return None

    vectors = _ensure_index()
    if vectors is None:
        return None

    query_text = expand_query_text(entity_name, entity_definition, clinical_concept)
    query_vec = _embed([query_text])
    if query_vec is None:
        return None

    query = query_vec[0]
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
    norms[norms == 0] = 1e-9
    scores_pct = (vectors @ query) / norms * 100

    boosted = scores_pct.copy()
    for i in candidate_idx:
        if CATALOG[i]["concept"] == clinical_concept:
            boosted[i] = min(100, boosted[i] + CONCEPT_MATCH_BOOST_PCT)

    top_idx = max(candidate_idx, key=lambda i: boosted[i])
    match = dict(CATALOG[top_idx])
    match["similarity_pct"] = round(float(scores_pct[top_idx]))
    match["concept_match"] = match["concept"] == clinical_concept
    return match

