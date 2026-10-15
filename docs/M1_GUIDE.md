# M1 — Document Pipeline

Status: **M1a Completed (2026-10-14); M1b Completed (2026-10-15)**.

M1 is split into two checkpoints to make failures easier to isolate:

- **M1a (completed)** — PDF/DOCX/TXT → normalized source blocks → deterministic chunks, with page/section provenance.
- **M1b (completed)** — Upload + metadata persistence → BGE embedding (CPU) → Qdrant indexing; only then is the full M1 complete.

## M1a: concepts

```text
PDF / DOCX / TXT
       ↓
Parser
       ↓
Source Blocks (page/section retained)
       ↓
Chunking: max 400 characters; 60-character overlap
       ↓
Chunk ID, document ID, filename, page, section, offsets, text
```

**Why source blocks?** Splitting a PDF after concatenating all pages may create chunks that cross page boundaries, making citation inaccurate. The parser first separates PDF pages; the chunker never joins them.

**Why overlap?** Text close to a split boundary remains available in an adjacent chunk. The overlap is deliberately smaller than half of the chunk size.

**DOCX/TXT page numbers:** These formats do not provide reliable physical page numbers through the chosen parser. Use `page=null`; for DOCX, preserve section headings. Do not fabricate page references.

## Changes in M1a

- `app/rag/parser.py`: PyMuPDF and python-docx parsing, plus TXT decoding and text normalization.
- `app/rag/chunker.py`: deterministic character chunks with stable IDs and source metadata.
- `data/samples/sample_contract.txt`: synthetic public test fixture.
- `scripts/check_document_pipeline.py`: offline checks for all three formats and long text.
- `tests/unit/test_document_pipeline.py`: tests for pages, headings, text tables and stable chunks.

## Run on Windows CMD

In `E:\project\DocMind-Agent`:

```cmd
git pull
docker compose up -d --build
scripts\check_m1a.bat
```

Or:

```cmd
docker compose exec -T api python scripts/check_document_pipeline.py
```

Expected final line:

```text
M1a PASS
```

Inspect the JSON output:

| Format | page | section |
|---|---|---|
| PDF | 1-based physical page | null |
| DOCX | null | detected heading title |
| TXT | null | null |

Every chunk must have a `document_id`, `chunk_id`, `filename` and `text`.

## Boundaries

- No OCR for scanned PDFs.
- PDF text extraction may be imperfect for complex layouts.
- DOCX physical pages are unknown.
- M1a only preprocesses files. **No embeddings or Qdrant writes are implemented yet.**

## M1b: Durable upload and Qdrant indexing

After the M1a checks pass:

```text
POST /v1/documents
    ↓
Save original file + metadata
    ↓
POST /v1/documents/{id}/index
    ↓
Parse → Chunk → BGE embedding on CPU
    ↓
Qdrant documents_v1
```

The chosen implementation uses **FastEmbed/ONNX on CPU**, not PyTorch. The
model is `BAAI/bge-small-zh-v1.5`, generating **512-dimensional** vectors.
For local hardware with 4 GB of VRAM, CPU embedding avoids competing with
the already deployed vLLM process.

### Service ownership

```text
POST /v1/documents
  → Validate extension, size and parseable text
  → Save original bytes in Docker volume (documents-data)
  → INSERT documents metadata in PostgreSQL (status=uploaded)

POST /v1/documents/{document_id}/index
  → claim indexing in PostgreSQL (status=indexing)
  → load source file, parse, chunk
  → FastEmbed CPU embeddings
  → Qdrant documents_v1 (cosine, dim=512, chunk metadata)
  → Verify per-document point count
  → Update PostgreSQL (status=indexed, chunk_count=n)
```

The original file, document metadata and vectors live in **different stores**.
Qdrant payload includes filename, page/section, chunk text, offset and
document ID; this becomes the basis of later source citations in M2.

### Start the M1b build (Windows CMD)

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build
docker compose ps
curl --noproxy "*" http://127.0.0.1:8090/health
scripts\check_m1b.bat
```

Expected output: TXT, PDF and DOCX all indexed with 512-dimensional vectors,
plus `PASS idempotent reindex` and the final `M1b PASS`.

### Manual upload example

```cmd
curl --noproxy "*" -X POST -F "file=@data/samples/sample_contract.txt" http://127.0.0.1:8090/v1/documents
```

The response includes a `document_id`. Copy it into Windows CMD:

```cmd
set DOC_ID=replace-with-the-uploaded-uuid
curl --noproxy "*" -X POST http://127.0.0.1:8090/v1/documents/%DOC_ID%/index
```

Expect JSON with `"status":"indexed"`, `"chunk_count"` and
`"vector_size":512`. Qdrant's local dashboard is
`http://127.0.0.1:6333/dashboard`.

### The first embedding model download

The BGE model is obtained **from ModelScope rather than Hugging Face**:

- ModelScope ONNX source: `lyf219/bge-small-zh-v1.5-onnx`
- Web page: https://modelscope.cn/models/lyf219/bge-small-zh-v1.5-onnx
- Original model identity: `BAAI/bge-small-zh-v1.5`
- ModelScope source is a *community conversion*, not a distribution from
  BAAI or Qdrant; use a reviewed, pinned revision for production deployment.
- The snapshot contains an ONNX weight file and tokenizer files. The weight
  filename is adapted locally to `model_optimized.onnx`, which is expected
  by FastEmbed's built-in BGE descriptor.
- `TextEmbedding(specific_model_path=..., local_files_only=True)` loads the
  converted ONNX file from the local volume. No Hugging Face API call occurs.
- Inference remains CPU-only with 512-dimensional vectors.

A named Docker volume (`embedding-cache`) retains files between restarts.

**First-run validation (Windows CMD)**:

```cmd
git pull
docker compose up -d --build api
scripts\check_modelscope.bat
scripts\check_m1b.bat
```

The first check confirms ONNX download, tokenizer loading and two real
Chinese embeddings before exercising the database/indexing pipeline.

If `.env` still contains `DOCMIND_PROXY_URL` from the earlier Clash
workaround, remove or comment it out to prefer direct ModelScope access.
The ModelScope domain and its Aliyun CDN are listed under `NO_PROXY` by
default. Do **not** set `HF_ENDPOINT`; it is unused for embedding downloads.

Downloaded weights are community-converted ONNX artifacts; validate actual
retrieval quality before treating their output as equivalent to official
BAAI weights. The verification script prints the locally downloaded file
size and SHA-256 hash for later reproducibility checks.

If the index endpoint returns HTTP 503, inspect:

```cmd
docker compose logs --tail 100 api
```

Do not delete Docker volumes while troubleshooting: they contain the original
documents, PostgreSQL data, Qdrant indexes and embedding-model cache.

### Re-index and failure semantics

- Re-indexing the same immutable document first prepares its vectors, then
  replaces Qdrant points with the same document ID.
- PostgreSQL prevents concurrent indexing of the same document.
- Index errors change status to `failed` and retain the uploaded file for retry.
- The example pipeline is **not an atomic transaction spanning PostgreSQL and
  Qdrant**; a failed write may temporarily leave partial index state. A retry
  replaces it.

### Explicit V1 limits

- File size max **10 MiB**; at most **1000 chunks per document**.
- No OCR, no scanned-image PDF ingestion.
- No claimed physical page numbers for DOCX/TXT.
- No authentication or production-grade document access control at this stage.
- Hybrid search/reranking/answer generation belong to **M2**, not M1.

**M1 Completed.** The user's Docker test returned `M1b PASS` after verifying TXT/PDF/DOCX and idempotent reindexing. See [M1 Acceptance](M1_ACCEPTANCE.md).
