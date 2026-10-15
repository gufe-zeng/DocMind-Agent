"""CPU BGE embeddings loaded from a ModelScope ONNX snapshot, never from HF.

Source: https://modelscope.cn/models/lyf219/bge-small-zh-v1.5-onnx
This is a community ONNX conversion of BAAI/bge-small-zh-v1.5.
The runtime stays on FastEmbed/ONNX CPU to avoid installing PyTorch.
"""

from functools import lru_cache
import math
from pathlib import Path
from threading import Lock

from fastembed import TextEmbedding


MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODELSCOPE_REPO = "lyf219/bge-small-zh-v1.5-onnx"
MODELSCOPE_REVISION = "master"
SOURCE_ONNX_NAME = "bge-small-zh-v1.5.onnx"
FASTEMBED_ONNX_NAME = "model_optimized.onnx"
TOKENIZER_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json")
MINIMUM_ONNX_SIZE_BYTES = 20_000_000

_download_lock = Lock()


def _model_directory(cache_dir: str) -> Path:
    return Path(cache_dir) / "modelscope" / "bge-small-zh-v1.5-onnx"


def _is_ready(model_dir: Path) -> bool:
    onnx_file = model_dir / FASTEMBED_ONNX_NAME
    return (
        onnx_file.is_file()
        and onnx_file.stat().st_size > MINIMUM_ONNX_SIZE_BYTES
        and all((model_dir / name).is_file() for name in TOKENIZER_FILES)
    )


def _prepare_model(cache_dir: str) -> Path:
    """Download once from ModelScope, then reuse a persistent local ONNX folder."""
    model_dir = _model_directory(cache_dir)
    if _is_ready(model_dir):
        return model_dir

    with _download_lock:
        if _is_ready(model_dir):
            return model_dir

        # Import only on first download. No call to huggingface_hub is needed.
        from modelscope import snapshot_download

        model_dir.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            model_id=MODELSCOPE_REPO,
            revision=MODELSCOPE_REVISION,
            local_dir=str(model_dir),
            allow_file_pattern=[
                SOURCE_ONNX_NAME,
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "vocab.txt",
            ],
        )

        original = model_dir / SOURCE_ONNX_NAME
        optimized = model_dir / FASTEMBED_ONNX_NAME
        if not optimized.is_file():
            if not original.is_file():
                raise RuntimeError(
                    "ModelScope snapshot does not contain the expected ONNX file: "
                    f"{SOURCE_ONNX_NAME}"
                )
            if original.stat().st_size <= MINIMUM_ONNX_SIZE_BYTES:
                raise RuntimeError(
                    "Downloaded ONNX file is unexpectedly small or incomplete."
                )
            # FastEmbed's built-in BGE model descriptor expects this exact filename.
            original.replace(optimized)

        if not _is_ready(model_dir):
            raise RuntimeError("Incomplete ModelScope ONNX snapshot or tokenizer files.")
        return model_dir


@lru_cache(maxsize=2)
def _load_model(model_name: str, cache_dir: str) -> TextEmbedding:
    if model_name != MODEL_NAME:
        raise ValueError(f"Unsupported embedding model: {model_name}")

    local_dir = _prepare_model(cache_dir)
    return TextEmbedding(
        model_name=model_name,
        specific_model_path=str(local_dir),
        local_files_only=True,
        cache_dir=cache_dir,
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
    """Blocking work: invoke from asynchronous code via asyncio.to_thread."""
    if not texts:
        raise ValueError("No text supplied for embedding.")
    if any(not text.strip() for text in texts):
        raise ValueError("Empty text cannot be embedded.")

    model = _load_model(model_name, cache_dir)
    vectors = [vector.tolist() for vector in model.embed(texts, batch_size=16)]
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding output count differs from input count.")
    for vector in vectors:
        if len(vector) != expected_size or not all(math.isfinite(x) for x in vector):
            raise RuntimeError("Invalid embedding dimension or non-finite values.")
    return vectors
