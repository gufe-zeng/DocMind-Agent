"""M2b: BGE cross-encoder reranking with a ModelScope-local ONNX model.

The original BAAI reranker-base is a 278M-parameter Chinese/English model.
Its ONNX artifact is ~1.11 GB: use CPU, a small Top-K and persistent cache.
No Hugging Face runtime download or GPU is needed.
"""

from dataclasses import dataclass
from functools import lru_cache
import math
from pathlib import Path
from threading import Lock

from fastembed import TextCrossEncoder

from app.rag.retriever import RetrievalHit


RERANKER_MODEL = "BAAI/bge-reranker-base"
MODELSCOPE_MODEL = "BAAI/bge-reranker-base"
MODELSCOPE_REVISION = "master"
ONNX_FILE = Path("onnx/model.onnx")
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json")
MIN_ONNX_BYTES = 100_000_000
_DOWNLOAD_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class RerankedHit:
    hit: RetrievalHit
    reranker_score: float


def _model_path(cache_dir: str) -> Path:
    return Path(cache_dir) / "modelscope" / "bge-reranker-base-onnx"


def _ready(path: Path) -> bool:
    onnx_path = path / ONNX_FILE
    return (
        onnx_path.is_file()
        and onnx_path.stat().st_size > MIN_ONNX_BYTES
        and all((path / item).is_file() for item in TOKENIZER_FILES)
    )


def _prepare_model(cache_dir: str) -> Path:
    directory = _model_path(cache_dir)
    if _ready(directory):
        return directory

    with _DOWNLOAD_LOCK:
        if _ready(directory):
            return directory

        from modelscope import snapshot_download

        directory.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            model_id=MODELSCOPE_MODEL,
            revision=MODELSCOPE_REVISION,
            local_dir=str(directory),
            allow_file_pattern=[
                "onnx/model.onnx",
                "config.json",
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "sentencepiece.bpe.model",
            ],
        )
        if not _ready(directory):
            raise RuntimeError(
                "ModelScope reranker ONNX snapshot incomplete. "
                "Expected onnx/model.onnx plus tokenizer files."
            )
        return directory


@lru_cache(maxsize=1)
def _load_reranker(model_name: str, cache_dir: str) -> TextCrossEncoder:
    if model_name != RERANKER_MODEL:
        raise ValueError(f"Unsupported reranker model: {model_name}")
    path = _prepare_model(cache_dir)
    return TextCrossEncoder(
        model_name=model_name,
        specific_model_path=str(path),
        local_files_only=True,
        cache_dir=cache_dir,
        cuda=False,
        threads=2,
    )


def rerank_hits(
    query: str,
    hits: list[RetrievalHit],
    *,
    model_name: str,
    cache_dir: str,
    limit: int = 2,
) -> list[RerankedHit]:
    """Score (query, chunk) pairs and return descending Cross-Encoder results.

    This is blocking ONNX inference: call via asyncio.to_thread in async paths.
    """
    if not query.strip():
        raise ValueError("Query cannot be empty.")
    if limit <= 0:
        raise ValueError("Rerank limit must be positive.")
    if not hits:
        return []

    # Keep individual inputs small on CPU. Truncation is explicit here;
    # retrieved source/citation metadata is preserved in each original hit.
    snippets = [hit.text[:400] for hit in hits]
    model = _load_reranker(model_name, cache_dir)
    scores = [float(value) for value in model.rerank(query, snippets, batch_size=4)]
    if len(scores) != len(hits) or not all(math.isfinite(s) for s in scores):
        raise RuntimeError("Invalid BGE cross-encoder scores.")
    ranked = [RerankedHit(hit=hit, reranker_score=score) for hit, score in zip(hits, scores, strict=True)]
    return sorted(
        ranked,
        key=lambda item: (-item.reranker_score, -item.hit.rrf_score, item.hit.chunk_id),
    )[:limit]
