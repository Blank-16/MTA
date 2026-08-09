import logging
import re

from app.core.config import settings
from app.services.restrictions.pipeline import RestrictionCode, RestrictionResult

logger = logging.getLogger(__name__)

# Patterns targeting common jailbreak / prompt-injection attempts.
# Ordered roughly by specificity — more specific patterns first.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"(you are|act as|pretend (to be|you('re| are)))\s+\w", re.I),
    re.compile(r"(system|developer|admin)\s*(prompt|message|instructions?)", re.I),
    re.compile(r"<\s*(system|assistant|user)\s*>", re.I),
    re.compile(r"\[INST\]|\[\/INST\]|<<SYS>>|<\/SYS>", re.I),
    re.compile(r"(override|bypass|disable)\s+(safety|filter|restriction|guardrail)", re.I),
    re.compile(r"do\s+anything\s+now|DAN\b", re.I),
    re.compile(r"```\s*(json|python|bash|sh)\b", re.I),  # code injection attempt
]


class InputSanitizer:
    async def check(self, text: str) -> RestrictionResult:
        if len(text) > settings.max_message_chars:
            logger.info("Input rejected: length=%d exceeds max=%d", len(text), settings.max_message_chars)
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.PROMPT_INJECTION,
                reason=f"Input exceeds maximum length of {settings.max_message_chars} characters",
            )

        # Reject non-UTF-8 sequences (already decoded by Pydantic, but guard control chars)
        if any(ord(c) < 9 or (13 < ord(c) < 32) for c in text):
            logger.info("Input rejected: contains non-printable control characters")
            return RestrictionResult(
                passed=False,
                code=RestrictionCode.PROMPT_INJECTION,
                reason="Input contains disallowed control characters",
            )

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning("Prompt injection pattern matched: %s", pattern.pattern)
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.PROMPT_INJECTION,
                    reason="Input contains disallowed instruction-override patterns",
                )

        return RestrictionResult(passed=True)
