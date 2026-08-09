import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

logger = logging.getLogger(__name__)


class RestrictionCode(StrEnum):
    PROMPT_INJECTION = "RESTRICTION_001"
    OFF_TOPIC = "RESTRICTION_002"
    LOW_SIMILARITY = "RESTRICTION_003"
    DIAGNOSIS_LANGUAGE = "RESTRICTION_004"
    DRUG_DOSAGE = "RESTRICTION_005"
    HIGH_CERTAINTY = "RESTRICTION_006"
    ESCALATION_TRIGGER = "RESTRICTION_007"


@dataclass(frozen=True)
class RestrictionResult:
    passed: bool
    code: RestrictionCode | None = None
    reason: str | None = None


class InputLayer(Protocol):
    async def check(self, text: str) -> RestrictionResult: ...


class OutputLayer(Protocol):
    async def check(self, text: str, retrieved_chunks: list[str]) -> RestrictionResult: ...


class RestrictionPipeline:
    """
    Input layers run before any LLM call; output layers run on the generated response.
    First failure in either phase short-circuits — no partial content leaks.
    All outcomes (pass and fail) are returned for audit logging.
    """

    def __init__(
        self,
        sanitizer: InputLayer,
        classifier: InputLayer,
        output_validator: OutputLayer,
        escalation_detector: OutputLayer,
    ) -> None:
        self._input_layers: list[InputLayer] = [sanitizer, classifier]
        self._output_layers: list[OutputLayer] = [output_validator, escalation_detector]

    async def run_input(self, text: str) -> RestrictionResult:
        for layer in self._input_layers:
            result = await layer.check(text)
            logger.debug(
                "Input restriction layer=%s passed=%s code=%s",
                layer.__class__.__name__,
                result.passed,
                result.code,
            )
            if not result.passed:
                return result
        return RestrictionResult(passed=True)

    async def run_output(self, text: str, retrieved_chunks: list[str]) -> RestrictionResult:
        for layer in self._output_layers:
            result = await layer.check(text, retrieved_chunks)
            logger.debug(
                "Output restriction layer=%s passed=%s code=%s",
                layer.__class__.__name__,
                result.passed,
                result.code,
            )
            if not result.passed:
                return result
        return RestrictionResult(passed=True)
