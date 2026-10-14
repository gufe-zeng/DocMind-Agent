"""Lightweight CPU embeddings using BGE Chinese via FastEmbed/ONNX.

The model is lazy-loaded on first index; FastEmbed downloads it into a
persistent Docker cache directory. No CUDA or PyTorch is required.
"""

from functools import lru_cache
import math

from fastembed import TextEmbedding


@lru_cache(maxsize=2)
def _load_model(model_name: str, cache_dir: str) -> TextEmbedding:
    return TextEmbedding(
        model_name=model_name,
        cache_dir=cache_dir,
        providers=["CPUExecutionProvider"],
        cuda=False,
        threads=2,
    )


def embed_texts(
    texts: list[str],
    *,
    model_name: str,
    cache_dir: str,
    expected_size: int = 512,
) -> list[list[float]]:
    """Blocking work: call through asyncio.to_thread from async endpoints."""
    if not texts:
        raise ValueError("No text supplied for embedding.")
    if any(not t.strip() for t in texts):
        raise ValueError("Empty text cannot be embedded.")

    model = _load_model(model_name, cache_dir)
    vectors = [v.tolist() for v in model.embed(texts, batch_size=16)]
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding output count differs from input count.")
    for vector in vectors:
        if len(vector) != expected_size or not all(math.isfinite(x) for x in vector):
            raise RuntimeError("Invalid embedding dimension or non-finite values.")
    return vectors
