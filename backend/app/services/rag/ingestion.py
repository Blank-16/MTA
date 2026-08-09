import hashlib
import logging
from pathlib import Path

from langchain_community.document_loaders import CSVLoader, PyPDFLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)

# Semantic chunking: split on section boundaries first, then paragraph, then sentence.
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=120,
    separators=["\n## ", "\n### ", "\n\n", "\n", ". "],
    length_function=len,
)

GUIDELINE_SOURCES = [
    {"source": "NICE", "jurisdiction": "UK", "confidence_tier": "high"},
    {"source": "WHO", "jurisdiction": "global", "confidence_tier": "high"},
    {"source": "CDC", "jurisdiction": "US", "confidence_tier": "high"},
]


def _chunk_id(content: str, metadata: dict) -> str:
    """
    Deterministic ID from content + source metadata.
    FIX: used as PGVector doc ID to deduplicate on re-ingestion — same chunk
    always maps to the same ID, so upsert replaces instead of appending.
    """
    key = f"{metadata.get('source', '')}:{metadata.get('section', '')}:{content}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


class GuidelineIngestionPipeline:
    def __init__(self, connection_string: str) -> None:
        self._embeddings = OpenAIEmbeddings(
            model="text-embedding-3-large",
            openai_api_key=settings.openai_api_key,
        )
        self._store = PGVector(
            embeddings=self._embeddings,
            collection_name="guidelines",
            connection=connection_string,
            distance_strategy="cosine",
        )

    async def ingest_document(self, file_path: str | Path, source_meta: dict) -> int:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        logger.info("Loading File: %s", path.name)
        try:
            if path.suffix.lower() == ".pdf":
                pages = PyPDFLoader(str(path)).load()
            elif path.suffix.lower() == ".txt":
                pages = TextLoader(str(path)).load()
            elif path.suffix.lower() == ".csv":
                pages = CSVLoader(str(path)).load()
            else:
                logger.warning("Unsupported file type: %s", path.name)
                return 0
        except Exception as exc:
            logger.error("Failed to load file %s: %s", path.name, exc, exc_info=True)
            raise

        chunks = _splitter.split_documents(pages)
        if not chunks:
            logger.warning("No chunks produced from %s", path.name)
            return 0

        ids: list[str] = []
        for chunk in chunks:
            chunk.metadata.update(source_meta)
            chunk.metadata.setdefault("confidence_tier", "moderate")
            chunk.metadata.setdefault("jurisdiction", "global")
            # Derive section from page metadata if present
            page = chunk.metadata.get("page", "")
            chunk.metadata.setdefault("section", f"p.{page}" if page else "")
            ids.append(_chunk_id(chunk.page_content, chunk.metadata))

        logger.info("Upserting %d chunks from %s into pgvector", len(chunks), path.name)
        try:
            # FIX: pass ids so PGVector uses upsert semantics — prevents duplicate chunks
            # on re-ingestion of the same PDF.
            await self._store.aadd_documents(chunks, ids=ids)
        except Exception as exc:
            logger.error("Vector store upsert failed for %s: %s", path.name, exc, exc_info=True)
            raise

        logger.info("Ingestion complete: %d chunks from %s", len(chunks), path.name)
        return len(chunks)

    async def ingest_all(self, guidelines_dir: str | Path) -> dict[str, int]:
        directory = Path(guidelines_dir)
        if not directory.is_dir():
            raise NotADirectoryError(f"Not a directory: {directory}")

        results: dict[str, int] = {}
        for file_path in sorted([p for p in directory.glob("*.*") if p.suffix.lower() in ('.pdf', '.txt', '.csv')]):
            source_name = file_path.stem.split("_")[0].upper()
            meta = next(
                (s for s in GUIDELINE_SOURCES if s["source"] == source_name),
                {"source": source_name, "jurisdiction": "global", "confidence_tier": "moderate"},
            )
            try:
                results[file_path.name] = await self.ingest_document(file_path, meta)
            except Exception as exc:
                logger.error("Skipping %s: %s", file_path.name, exc)
                results[file_path.name] = 0

        return results
