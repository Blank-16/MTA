import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.restrictions.pipeline import RestrictionCode, RestrictionResult

logger = logging.getLogger(__name__)

# Layer 4 — diagnosis language
_DIAGNOSIS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\byou (have|suffer from|are suffering from|are experiencing)\b", re.I),
    re.compile(r"\bthis is (definitely|certainly|clearly)\b", re.I),
    re.compile(r"\bdiagnosis (is|confirms?)\b", re.I),
    re.compile(r"\bconfirm(ed|s)? (that )?(you have|diagnosis)\b", re.I),
]

# Layer 5 — drug dosage
_DOSAGE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d+(\.\d+)?\s*(mg|ml|mcg|ug|units?|tablets?|capsules?)\b", re.I),
    re.compile(r"\btake\s+\d+\b", re.I),
    re.compile(r"\b(dose|dosage|dosing)\s+(of|is)\s+\d+", re.I),
]

# Layer 6 — high certainty
_CERTAINTY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(definitely|certainly|absolutely|without (a )?doubt|100%|guaranteed)\b", re.I),
    re.compile(r"\b(this is|it is|that is) (a |an )?(definite|certain)\b", re.I),
]

_JUDGE_SYSTEM = """You are a medical triage output safety reviewer.
Return ONLY a JSON object with exactly these keys:
- safe: boolean
- issue: string or null
- category: one of diagnosis, dosage, certainty, other, or null

Unsafe if: definitive diagnosis stated, specific drug dosages given, high-certainty misleading language.
No prose outside the JSON object."""

_CODE_MAP: dict[str, RestrictionCode] = {
    "diagnosis": RestrictionCode.DIAGNOSIS_LANGUAGE,
    "dosage":    RestrictionCode.DRUG_DOSAGE,
    "certainty": RestrictionCode.HIGH_CERTAINTY,
}


class OutputValidator:
    def __init__(self) -> None:
        # FIX: pass explicit api key — consistent with all other OpenAI usages
        self._judge = ChatOpenAI(
            model="gpt-4o",
            temperature=0.0,
            response_format={"type": "json_object"},
            openai_api_key=settings.openai_api_key,
        )

    async def check(self, text: str, retrieved_chunks: list[str]) -> RestrictionResult:
        # Layer 3: RAG gate
        if not retrieved_chunks:
            logger.warning("Output rejected: no retrieved chunks above threshold")
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.LOW_SIMILARITY,
                reason="No clinical guidelines met the minimum similarity threshold",
            )

        # Layers 4-6: fast regex before paying for an LLM call
        for pattern in _DIAGNOSIS_PATTERNS:
            if pattern.search(text):
                logger.warning("Diagnosis language detected pattern=%s", pattern.pattern)
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.DIAGNOSIS_LANGUAGE,
                    reason="Response contains diagnostic language",
                )

        for pattern in _DOSAGE_PATTERNS:
            if pattern.search(text):
                logger.warning("Drug dosage detected pattern=%s", pattern.pattern)
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.DRUG_DOSAGE,
                    reason="Response contains specific drug dosage information",
                )

        for pattern in _CERTAINTY_PATTERNS:
            if pattern.search(text):
                logger.warning("High-certainty language detected pattern=%s", pattern.pattern)
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.HIGH_CERTAINTY,
                    reason="Response contains high-certainty language",
                )

        # LLM-as-judge: catches subtle violations that regex patterns might miss.
        # Only invoked when text length suggests a substantive response (>50 chars).
        # Short rejection messages and empty strings don't need judging.
        # This avoids a gpt-4o API call on every trivially safe response.
        if len(text) < 50:
            return RestrictionResult(passed=True)

        try:
            result = await self._judge.ainvoke([
                SystemMessage(content=_JUDGE_SYSTEM),
                HumanMessage(content=f"Review:\n\n{text}"),
            ])
            verdict = json.loads(result.content)

            if not verdict.get("safe", True):
                category = verdict.get("category", "other")
                reason = verdict.get("issue", "LLM judge flagged unsafe content")
                logger.warning("LLM judge flagged output category=%s reason=%s", category, reason)
                return RestrictionResult(
                    passed=False,
                    code=_CODE_MAP.get(category, RestrictionCode.DIAGNOSIS_LANGUAGE),
                    reason=reason,
                )
        except json.JSONDecodeError as exc:
            logger.error("Judge returned non-JSON: %s", exc)
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.DIAGNOSIS_LANGUAGE,
                reason="Safety validation produced invalid response",
            )
        except Exception as exc:
            # Fail safe — unverified content is never served
            logger.error("LLM judge call failed: %s", exc, exc_info=True)
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.DIAGNOSIS_LANGUAGE,
                reason="Safety validation could not be completed",
            )

        return RestrictionResult(passed=True)
