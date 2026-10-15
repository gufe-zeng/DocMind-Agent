"""Verify a real ModelScope BGE reranker download and CPU ONNX inference."""

import hashlib
from math import isfinite
from pathlib import Path

from app.core.config import get_settings
from app.rag.reranker import ONNX_FILE, _model_path, _load_reranker


def main() -> None:
    settings = get_settings()
    print("ModelScope reranker: BAAI/bge-reranker-base", flush=True)
    print("Downloading official BGE reranker ONNX (~1.11 GB) if not cached...", flush=True)

    model = _load_reranker(settings.reranker_model, settings.embedding_cache_dir)
    texts = [
        "甲方应于乙方服务验收后三十日内付款。",
        "乙方的违约责任包括承担相应损失。",
    ]
    scores = [float(x) for x in model.rerank("合同付款期限是多少天？", texts, batch_size=2)]
    assert len(scores) == len(texts)
    assert all(isfinite(x) for x in scores)
    print(f"Two real CPU reranker scores: {scores}", flush=True)

    directory = _model_path(settings.embedding_cache_dir)
    model_file: Path = directory / ONNX_FILE
    assert model_file.exists() and model_file.stat().st_size > 100_000_000
    print(f"Cached ONNX: {model_file}", flush=True)
    print(f"Bytes: {model_file.stat().st_size:,}", flush=True)
    sha = hashlib.sha256()
    with model_file.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(data)
    print(f"ONNX SHA256: {sha.hexdigest()}", flush=True)
    print("M2b reranker PASS", flush=True)


if __name__ == "__main__":
    main()
