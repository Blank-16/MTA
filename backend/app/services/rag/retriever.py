import logging
from typing import TypedDict

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

from app.core.config import settings

logger = logging.getLogger(__name__)


class RetrievedChunk(TypedDict):
    content: str
    source: str
    section: str
    jurisdiction: str
    confidence_tier: str
    similarity: float


class ClinicalRetriever:
    def __init__(self, connection_string: str) -> None:
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.openai_api_key,
        )
        self._store = PGVector(
            embeddings=self._embeddings,
            collection_name="guidelines",
            connection=connection_string,
            distance_strategy="cosine",  # type: ignore
        )

    async def retrieve(self, query: str) -> list[RetrievedChunk]:
        """
        Two-stage retrieval:
        1. Similarity search over fetch_k candidates — build filtered set above threshold.
        2. MMR re-ranking over ONLY the filtered set — guarantees no below-threshold chunk survives.

        FIX: Previously MMR searched the full store independently, so score_map.get() fallback
        silently served chunks that failed the threshold. Now MMR operates on filtered docs only.
        """
        # Stage 1: scored similarity search
        try:
            scored_docs = await self._store.asimilarity_search_with_relevance_scores(
                query, k=settings.rag_fetch_k
            )
        except Exception as exc:
            logger.error("Vector store similarity search failed: %s", exc, exc_info=True)
            return []

        above_threshold = [
            (doc, score) for doc, score in scored_docs if score >= settings.rag_min_similarity
        ]

        if not above_threshold:
            logger.info(
                "No chunks above threshold=%.2f (best=%.4f) query_len=%d",
                settings.rag_min_similarity,
                max((s for _, s in scored_docs), default=0.0),
                len(query),
            )
            return []

        # Stage 2: MMR re-rank within the already-filtered docs
        # We replicate MMR locally so we don't re-query the full store.
        filtered_docs = [doc for doc, _ in above_threshold]
        score_map = {doc.page_content: score for doc, score in above_threshold}

        selected = _mmr_select(
            filtered_docs,
            score_map,
            k=min(settings.rag_top_k, len(filtered_docs)),
            lambda_mult=settings.rag_lambda_mult,
        )

        results: list[RetrievedChunk] = []
        for doc in selected:
            meta = doc.metadata
            results.append(
                RetrievedChunk(
                    content=doc.page_content,
                    source=meta.get("source", "unknown"),
                    section=meta.get("section", ""),
                    jurisdiction=meta.get("jurisdiction", "global"),
                    confidence_tier=meta.get("confidence_tier", "moderate"),
                    similarity=round(score_map[doc.page_content], 4),
                )
            )

        logger.info("Retrieved %d chunks above threshold", len(results))
        return results


def _mmr_select(docs, score_map: dict[str, float], k: int, lambda_mult: float):
    """
    Greedy MMR over a pre-filtered doc list.
    Avoids the bug where PGVector MMR fetches from the full collection.
    lambda_mult=1 → pure relevance, lambda_mult=0 → pure diversity.
    """
    if not docs:
        return []

    # We use the relevance scores we already have as the "similarity to query"
    selected: list = []
    remaining = list(docs)

    while remaining and len(selected) < k:
        if not selected:
            # First pick: highest relevance
            best = max(remaining, key=lambda d: score_map[d.page_content])
        else:
            # Score = lambda * relevance - (1-lambda) * max_sim_to_selected
            # We approximate inter-doc similarity by jaccard on tokens (no extra embedding call)
            def mmr_score(doc) -> float:
                rel = score_map[doc.page_content]
                sel_tokens = [set(s.page_content.split()) for s in selected]
                doc_tokens = set(doc.page_content.split())
                max_sim = max(
                    (len(doc_tokens & st) / len(doc_tokens | st) if (doc_tokens | st) else 0.0)
                    for st in sel_tokens
                ) if sel_tokens else 0.0
                return lambda_mult * rel - (1 - lambda_mult) * max_sim

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    return selected
