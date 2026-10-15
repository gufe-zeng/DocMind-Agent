"""Validate BGE-small-zh-v1.5 ModelScope download and offline CPU inference.

This test intentionally does not call the Hugging Face API.
It is safe to run more than once: model files persist in the Docker volume.
"""

import math
from pathlib import Path

from app.core.config import get_settings
from app.rag.embedder import (
    FASTEMBED_ONNX_NAME,
    MODELSCOPE_REPO,
    _model_directory,
    embed_texts,
)


def main() -> None:
    settings = get_settings()
    print(f"ModelScope source: {MODELSCOPE_REPO}", flush=True)
    print("Loading or downloading the ONNX model and tokenizer...", flush=True)

    texts = ["合同约定付款期限为三十日。", "乙方未按期履约应承担违约责任。"]
    vectors = embed_texts(
        texts,
        model_name=settings.embedding_model,
        cache_dir=settings.embedding_cache_dir,
        expected_size=settings.embedding_vector_size,
    )
    assert len(vectors) == len(texts)
    assert all(len(v) == 512 for v in vectors)
    assert all(all(math.isfinite(x) for x in v) for v in vectors)

    directory = _model_directory(settings.embedding_cache_dir)
    onnx = directory / FASTEMBED_ONNX_NAME
    assert onnx.is_file()
    print(f"Cached local ONNX: {onnx}", flush=True)
    print(f"Model size: {onnx.stat().st_size:,} bytes", flush=True)
    print(f"Embedding dimension: {len(vectors[0])}", flush=True)
    print("ModelScope ONNX PASS", flush=True)


if __name__ == "__main__":
    main()
