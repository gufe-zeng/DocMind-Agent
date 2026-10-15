"""M2b CPU ModelScope reranker tests without a real 1.11GB download."""

from pathlib import Path
import sys
from types import SimpleNamespace

from app.rag import reranker
from app.rag.retriever import RetrievalHit


def fake_hit(chunk_id: str, text: str) -> RetrievalHit:
    return RetrievalHit(
        document_id="demo",
        chunk_id=chunk_id,
        filename="demo.txt",
        page=None,
        section=None,
        text=text,
        rrf_score=0.01,
        dense_rank=1,
        sparse_rank=1,
    )


def test_modelscope_snapshot_and_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(reranker, "MIN_ONNX_BYTES", 10)
    calls = []

    def fake_snapshot_download(*, model_id, revision, local_dir, allow_file_pattern):
        calls.append(model_id)
        directory = Path(local_dir)
        (directory / "onnx").mkdir(parents=True, exist_ok=True)
        (directory / "onnx/model.onnx").write_bytes(b"onnx-placeholder")
        (directory / "tokenizer.json").write_text("{}", encoding="utf-8")
        (directory / "tokenizer_config.json").write_text("{}", encoding="utf-8")

    monkeypatch.setitem(
        sys.modules, "modelscope",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    assert reranker._prepare_model(str(tmp_path)) == reranker._model_path(str(tmp_path))
    assert reranker._prepare_model(str(tmp_path)) == reranker._model_path(str(tmp_path))
    assert calls == ["BAAI/bge-reranker-base"]


def test_local_only_reranking_and_order(monkeypatch, tmp_path: Path) -> None:
    seen = {}

    class FakeCrossEncoder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def rerank(self, query, texts, batch_size):
            assert query == "付款期限"
            assert batch_size == 4
            return iter([0.1, 4.2])

    monkeypatch.setattr(reranker, "TextCrossEncoder", FakeCrossEncoder)
    monkeypatch.setattr(reranker, "_prepare_model", lambda path: tmp_path)
    reranker._load_reranker.cache_clear()
    try:
        ranked = reranker.rerank_hits(
            "付款期限",
            [
                fake_hit("breach", "乙方违约责任"),
                fake_hit("payment", "付款期限三十日"),
            ],
            model_name=reranker.RERANKER_MODEL,
            cache_dir=str(tmp_path),
            limit=1,
        )
    finally:
        reranker._load_reranker.cache_clear()

    assert len(ranked) == 1
    assert ranked[0].hit.chunk_id == "payment"
    assert seen["local_files_only"] is True
    assert seen["cuda"] is False
    assert seen["specific_model_path"] == str(tmp_path)


def test_empty_reranking_skips_model_load(tmp_path: Path) -> None:
    assert reranker.rerank_hits(
        "付款期限", [], model_name=reranker.RERANKER_MODEL,
        cache_dir=str(tmp_path), limit=2
    ) == []


def test_parallel_cpu_rerank_requests_do_not_execute_model_simultaneously(monkeypatch):
    """The inference lock remains held by the real worker, even if caller cancels."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    from time import sleep

    gate = Lock()
    activity = {"active": 0, "max_active": 0, "calls": 0}

    class SlowFakeModel:
        def rerank(self, query, snippets, batch_size):
            with gate:
                activity["active"] += 1
                activity["calls"] += 1
                activity["max_active"] = max(
                    activity["max_active"], activity["active"]
                )
            try:
                sleep(0.02)
                return iter([0.9] * len(snippets))
            finally:
                with gate:
                    activity["active"] -= 1

    fake = SlowFakeModel()
    monkeypatch.setattr(reranker, "_load_reranker", lambda *args: fake)

    def one_call(_):
        return reranker.rerank_hits(
            "付款期限",
            [fake_hit("p", "付款期限三十日")],
            model_name=reranker.RERANKER_MODEL,
            cache_dir="/synthetic-cache-no-files",
            limit=1,
        )

    with ThreadPoolExecutor(max_workers=4) as workers:
        rows = list(workers.map(one_call, range(4)))

    assert len(rows) == 4
    assert activity["calls"] == 4
    assert activity["max_active"] == 1
    assert all(r[0].hit.chunk_id == "p" for r in rows)
