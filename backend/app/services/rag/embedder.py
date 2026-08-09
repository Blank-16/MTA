import logging

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


class ClinicalEmbedder:
    """
    Thin wrapper around OpenAIEmbeddings so the rest of the codebase
    doesn't import langchain directly and can be easily swapped.
    """

    def __init__(self) -> None:
        self._model = OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=settings.openai_api_key,
            # Chunk large document batches automatically
            chunk_size=200,
        )

    async def embed_query(self, text: str) -> list[float]:
        logger.debug("Embedding query len=%d", len(text))
        return await self._model.aembed_query(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        logger.debug("Embedding %d documents", len(texts))
        return await self._model.aembed_documents(texts)
