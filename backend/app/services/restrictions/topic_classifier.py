import asyncio
import logging

import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.services.restrictions.pipeline import RestrictionCode, RestrictionResult

logger = logging.getLogger(__name__)

_MEDICAL_ANCHORS = [
    "symptoms fever headache pain treatment diagnosis",
    "medication prescription dosage side effects drug",
    "chest pain shortness of breath emergency ambulance",
    "mental health anxiety depression therapy psychiatry",
    "skin rash allergy infection wound",
    "blood pressure heart rate pulse vital signs",
    "pregnancy birth infant child paediatric",
    "cancer tumour oncology chemotherapy",
    "diabetes insulin glucose blood sugar",
    "fracture bone injury orthopaedic surgery",
]

_OFF_TOPIC_THRESHOLD = 0.60


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


class TopicClassifier:
    def __init__(self) -> None:
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=settings.openai_api_key,
        )
        self._anchor_vectors: list[np.ndarray] | None = None
        # FIX: asyncio.Lock prevents concurrent requests from double-embedding anchors
        self._lock = asyncio.Lock()

    async def _ensure_anchors(self) -> None:
        # Fast path — no lock needed once initialised
        if self._anchor_vectors is not None:
            return
        async with self._lock:
            # Re-check inside lock — another coroutine may have initialised while we waited
            if self._anchor_vectors is not None:
                return
            logger.info("Embedding medical topic anchors (once per process lifetime)")
            vectors = await self._embeddings.aembed_documents(_MEDICAL_ANCHORS)
            self._anchor_vectors = [np.array(v) for v in vectors]

    async def check(self, text: str) -> RestrictionResult:
        await self._ensure_anchors()
        if self._anchor_vectors is None:
            raise RuntimeError("TopicClassifier anchor vectors failed to initialise")

        query_vector = np.array(await self._embeddings.aembed_query(text))
        max_sim = max(_cosine(query_vector, anchor) for anchor in self._anchor_vectors)

        logger.debug("Topic classifier max_sim=%.4f threshold=%.4f", max_sim, _OFF_TOPIC_THRESHOLD)

        if max_sim < _OFF_TOPIC_THRESHOLD:
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.OFF_TOPIC,
                reason=f"Query does not appear medical (similarity={max_sim:.3f})",
            )
        return RestrictionResult(passed=True)
