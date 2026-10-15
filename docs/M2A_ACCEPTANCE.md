# M2a Acceptance Record — 2026-10-15

The developer executed `scripts\check_m2a.bat` in Windows Docker Desktop.

Evidence:

- Three synthetic TXT contracts indexed:
  - `m2a_payment.txt`
  - `m2a_breach.txt`
  - `m2a_delivery.txt`
- `document_id` filter successfully restricted results to the payment document.
- Top payment hit returned **dense_rank=1, sparse_rank=1** with
  `rrf_score=0.03278688524590164`. This equals `1/(60+1)+1/(60+1)`.
- Global ranking returned source filenames, rank positions and RRF scores.
- A nonexistent document UUID returned zero evidence, not unrelated chunks.
- Terminal output: **`M2a PASS`** / **`M2a validation passed.`**

**Decision: M2a Completed.**

This was a functional integration test, not a labeled retrieval benchmark.
Recall@K and MRR are deferred to M7.
