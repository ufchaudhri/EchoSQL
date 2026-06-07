"""
Embedding service — generates query embeddings via sentence-transformers.
Caches results in Redis to avoid repeated model inference.
"""

import logging
from typing import List, Optional

from config import EMBEDDING_MODEL, EMBEDDING_CACHE_TTL_HOURS

logger = logging.getLogger(__name__)

# Module-level singleton; loaded lazily so startup stays fast.
_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model '%s' …", EMBEDDING_MODEL)
            _model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Embedding model ready")
        except Exception as e:
            logger.error("Could not load embedding model: %s", e)
    return _model


def embed(text: str) -> Optional[List[float]]:
    """
    Return a unit-normalised embedding vector for *text*.

    Checks Redis first; falls back to model inference and writes the result
    back to Redis.  Returns None if both the cache miss and the model fail.
    """
    from services.redis_cache import get_redis_cache

    cache = get_redis_cache()

    # --- cache hit ---
    if cache.client:
        hit = cache.get_embedding(text)
        if hit:
            return hit["embedding"]

    # --- model inference ---
    model = _get_model()
    if model is None:
        return None

    try:
        vector: List[float] = model.encode(text, normalize_embeddings=True).tolist()
    except Exception as e:
        logger.error("embed() failed for text=%r: %s", text[:80], e)
        return None

    # --- write back to cache ---
    if cache.client:
        cache.cache_embedding(text, vector, ttl_hours=EMBEDDING_CACHE_TTL_HOURS)

    return vector
