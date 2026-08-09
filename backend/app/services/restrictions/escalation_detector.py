import logging
import re

from app.services.restrictions.pipeline import RestrictionCode, RestrictionResult

logger = logging.getLogger(__name__)

# Red-flag combinations that mandate immediate escalation regardless of LLM output.
# Each tuple is (primary_pattern, optional_modifier_pattern).
# If primary matches alone, escalate. Modifier increases confidence but is not required.
_RED_FLAG_RULES: list[tuple[re.Pattern[str], re.Pattern[str] | None, str]] = [
    (
        re.compile(r"\bchest\s+pain\b", re.I),
        None,  # chest pain alone is an emergency — no modifier required
        "Chest pain — possible cardiac event",
    ),
    (
        re.compile(r"\b(difficulty|trouble|unable to|can.t)\s+breath(e|ing)\b", re.I),
        None,
        "Breathing difficulty — possible respiratory emergency",
    ),
    (
        re.compile(r"\b(stroke|facial?\s+droop|slurred?\s+speech|sudden\s+(weakness|numbness))\b", re.I),
        None,
        "Possible stroke symptoms",
    ),
    (
        re.compile(r"\b(severe\s+head(ache)?|worst.{0,10}head(ache)?|thunder.{0,10}head)\b", re.I),
        re.compile(r"\b(sudden|stiff\s+neck|vomit|light.{0,5}sensitiv)\b", re.I),
        "Sudden severe headache — possible subarachnoid haemorrhage or meningitis",
    ),
    (
        re.compile(r"\b(stiff\s+neck|neck\s+stiff)\b", re.I),
        re.compile(r"\b(fever|rash|head|light|vomit)\b", re.I),
        "Neck stiffness with fever/rash — possible meningitis",
    ),
    (
        re.compile(r"\b(unresponsive|unconscious|collapsed|not\s+breathing|no\s+pulse)\b", re.I),
        None,
        "Loss of consciousness or absent vital signs",
    ),
    (
        re.compile(r"\b(severe\s+bleed|bleed(ing)?\s+won.t\s+stop|bleed(ing)?\s+heavily)\b", re.I),
        None,
        "Severe uncontrolled bleeding",
    ),
    (
        re.compile(r"\b(anaphyl|severe\s+allerg|throat\b.{0,20}(clos|swell|tight))", re.I),
        None,
        "Possible anaphylaxis",
    ),
    (
        re.compile(r"\b(overdos|took\s+too\s+many|took\s+all\s+(my|the)\s+(pill|tablet|med))\b", re.I),
        None,
        "Possible medication overdose",
    ),
    (
        re.compile(r"\b(suicid|kill\s+myself|end\s+my\s+life|don.t\s+want\s+to\s+live)\b", re.I),
        None,
        "Suicidal ideation — mental health emergency",
    ),
]


class EscalationDetector:
    async def check(self, text: str, retrieved_chunks: list[str]) -> RestrictionResult:
        for primary, modifier, reason in _RED_FLAG_RULES:
            primary_match = primary.search(text)
            if not primary_match:
                continue

            # If no modifier required, escalate on primary match alone
            if modifier is None or modifier.search(text):
                logger.warning(
                    "Escalation triggered: reason=%s primary=%s",
                    reason,
                    primary.pattern,
                )
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.ESCALATION_TRIGGER,
                    reason=reason,
                )

        # passed=False with ESCALATION_TRIGGER forces escalate=true in the response.
        # We return passed=True here because the escalation is handled at response
        # construction level — this layer doesn't block the response, it annotates it.
        return RestrictionResult(passed=True)

    def detect_in_user_input(self, text: str) -> RestrictionResult:
        """
        Synchronous check run on user input before the LLM call.
        If red flags are in the *question* itself we must escalate proactively.
        """
        for primary, modifier, reason in _RED_FLAG_RULES:
            primary_match = primary.search(text)
            if not primary_match:
                continue
            if modifier is None or modifier.search(text):
                logger.info("Pre-LLM escalation from user input: %s", reason)
                return RestrictionResult(
                    passed=False,
                    code=RestrictionCode.ESCALATION_TRIGGER,
                    reason=reason,
                )
        return RestrictionResult(passed=True)
