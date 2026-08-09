
from app.services.rag.ingestion import _chunk_id
from app.services.rag.retriever import _mmr_select


class TestMMRSelect:
    def _make_doc(self, content: str, score: float):
        from langchain_core.documents import Document
        return Document(page_content=content, metadata={}), score

    def test_returns_k_docs(self):
        docs_scores = [self._make_doc(f"doc {i} " * 20, 0.9 - i * 0.01) for i in range(10)]
        docs = [d for d, _ in docs_scores]
        score_map = {d.page_content: s for d, s in docs_scores}
        selected = _mmr_select(docs, score_map, k=5, lambda_mult=0.6)
        assert len(selected) == 5

    def test_returns_fewer_when_not_enough_docs(self):
        docs_scores = [self._make_doc(f"doc {i}", 0.9) for i in range(3)]
        docs = [d for d, _ in docs_scores]
        score_map = {d.page_content: s for d, s in docs_scores}
        selected = _mmr_select(docs, score_map, k=10, lambda_mult=0.6)
        assert len(selected) == 3

    def test_empty_input_returns_empty(self):
        selected = _mmr_select([], {}, k=5, lambda_mult=0.6)
        assert selected == []

    def test_high_lambda_favours_relevance(self):
        # lambda=1.0 → pure relevance → first picked is highest score
        from langchain_core.documents import Document
        docs = [
            Document(page_content="low score doc", metadata={}),
            Document(page_content="high score doc", metadata={}),
        ]
        score_map = {"low score doc": 0.75, "high score doc": 0.95}
        selected = _mmr_select(docs, score_map, k=1, lambda_mult=1.0)
        assert selected[0].page_content == "high score doc"


class TestChunkDeduplication:
    def test_same_content_same_id(self):
        meta = {"source": "NICE", "section": "2.1"}
        id1 = _chunk_id("identical content", meta)
        id2 = _chunk_id("identical content", meta)
        assert id1 == id2

    def test_different_content_different_id(self):
        meta = {"source": "NICE", "section": "2.1"}
        id1 = _chunk_id("content A", meta)
        id2 = _chunk_id("content B", meta)
        assert id1 != id2

    def test_different_source_different_id(self):
        id1 = _chunk_id("same content", {"source": "NICE", "section": "1"})
        id2 = _chunk_id("same content", {"source": "WHO",  "section": "1"})
        assert id1 != id2

    def test_id_is_hex_string(self):
        cid = _chunk_id("content", {"source": "CDC"})
        assert all(c in "0123456789abcdef" for c in cid)
        assert len(cid) == 32


class TestCeleryConfig:
    def test_result_expires_set(self):
        """Celery must have result_expires to prevent Redis accumulation."""
        from app.workers.ingestion_worker import celery_app
        assert celery_app.conf.result_expires is not None, \
            "result_expires must be configured"
        assert celery_app.conf.result_expires <= 86400, \
            "result_expires should be <= 24h to keep Redis lean"


class TestMigration0003:
    def test_gin_index_migration_exists(self):
        """Migration 0003 must create GIN index for admin jsonb queries."""
        src = open("migrations/versions/0003_jsonb_gin_index.py").read()
        assert "gin" in src.lower(), "Must create a GIN index"
        assert "restriction_log" in src, "Index must be on restriction_log column"
        assert "CONCURRENTLY" in src, "Must use CONCURRENTLY to avoid table lock"
