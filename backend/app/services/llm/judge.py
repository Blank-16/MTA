import json
import logging
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class JudgeVerdict(TypedDict):
    safe: bool
    issue: str | None
    category: str | None  # "diagnosis" | "dosage" | "certainty" | "other" | None


_SYSTEM = """You are a medical triage output safety reviewer.
Return ONLY a JSON object:
{
  "safe": boolean,
  "issue": "reason if unsafe, null if safe",
  "category": "diagnosis | dosage | certainty | other | null"
}
Unsafe if: definitive diagnosis stated, specific drug dosages given, high-certainty misleading language used.
No prose outside JSON."""


class LLMJudge:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.0,
            response_format={"type": "json_object"},
            openai_api_key=settings.openai_api_key,
        )

    async def evaluate(self, response_text: str) -> JudgeVerdict:
        """
        Returns a structured verdict. On any API or parse error, returns
        safe=False to fail-safe — never silently allows unsafe content through.
        """
        try:
            result = await self._llm.ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=f"Review:\n\n{response_text}"),
            ])
            verdict = json.loads(result.content)  # type: ignore
            return JudgeVerdict(
                safe=bool(verdict.get("safe", False)),
                issue=verdict.get("issue"),
                category=verdict.get("category"),
            )
        except json.JSONDecodeError as exc:
            logger.error("Judge returned non-JSON: %s", exc)
        except Exception as exc:
            logger.error("Judge API call failed: %s", exc, exc_info=True)

        # Fail safe — unverified content is treated as unsafe
        return JudgeVerdict(safe=False, issue="Safety validation unavailable", category="other")
