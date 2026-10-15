"""Offline tests of the ModelScope-only ONNX download path."""

from pathlib import Path
import sys
from types import SimpleNamespace

from app.rag import embedder


def test_modelscope_snapshot_renamed_for_fastembed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(embedder, "MINIMUM_ONNX_SIZE_BYTES", 4)
    snapshot_calls = []

    def fake_snapshot_download(*, model_id, revision, local_dir, allow_file_pattern):
        snapshot_calls.append((model_id, revision, tuple(allow_file_pattern)))
        target = Path(local_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / embedder.SOURCE_ONNX_NAME).write_bytes(b"onnx-placeholder")
        for name in embedder.TOKENIZER_FILES:
            (target / name).write_text("{}", encoding="utf-8")
        return str(target)

    monkeypatch.setitem(
        sys.modules,
        "modelscope",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    first = embedder._prepare_model(str(tmp_path))
    assert (first / "model_optimized.onnx").read_bytes() == b"onnx-placeholder"
    assert not (first / embedder.SOURCE_ONNX_NAME).exists()
    assert snapshot_calls[0][0] == "lyf219/bge-small-zh-v1.5-onnx"
    assert "tokenizer.json" in snapshot_calls[0][2]

    second = embedder._prepare_model(str(tmp_path))
    assert second == first
    assert len(snapshot_calls) == 1, "Cached model must not redownload"


def test_fastembed_uses_local_model_only(monkeypatch, tmp_path: Path) -> None:
    arguments = {}

    class FakeEmbedding:
        def __init__(self, **kwargs):
            arguments.update(kwargs)

        def embed(self, texts, batch_size):
            assert batch_size == 16
            for text in texts:
                assert text.strip()
                yield SimpleNamespace(tolist=lambda: [0.01] * 512)

    local = tmp_path / "modelscope" / "bge-small-zh-v1.5-onnx"
    local.mkdir(parents=True)
    monkeypatch.setattr(embedder, "TextEmbedding", FakeEmbedding)
    monkeypatch.setattr(embedder, "_prepare_model", lambda cache_dir: local)
    embedder._load_model.cache_clear()
    try:
        vectors = embedder.embed_texts(
            ["测试中文合同条款"],
            model_name=embedder.MODEL_NAME,
            cache_dir=str(tmp_path),
        )
    finally:
        embedder._load_model.cache_clear()

    assert len(vectors) == 1 and len(vectors[0]) == 512
    assert arguments["specific_model_path"] == str(local)
    assert arguments["local_files_only"] is True
    assert arguments["cuda"] is False


def test_reject_unexpected_model_without_network(tmp_path: Path) -> None:
    try:
        embedder._load_model("another/model", str(tmp_path))
    except ValueError as exc:
        assert "Unsupported embedding model" in str(exc)
    else:
        raise AssertionError("Unexpected model should be rejected without download")
