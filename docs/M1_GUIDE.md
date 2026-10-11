# M1 — Document Pipeline

Status: **M1a implemented; user acceptance pending**.

M1 is split into two checkpoints to make failures easier to isolate:

- **M1a** — PDF/DOCX/TXT → normalized source blocks → deterministic chunks, with page/section provenance.
- **M1b** — Upload + metadata persistence → BGE embedding (CPU) → Qdrant indexing; only then is the full M1 complete.

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

## Next: M1b

After these checks pass:

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

CPU inference is chosen for the embedding model so it does not compete with the 4GB GTX 1650 used by vLLM.

M1 will only be marked completed after an actual document is indexed and vectors/payloads can be verified in Qdrant.
