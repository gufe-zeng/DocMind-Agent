# API Contract

Status: **V1 surface frozen**.

## M0 — implemented

```text
GET /health
GET /metrics
```

## M1

```text
POST /v1/documents
POST /v1/documents/{id}/index
```

## M3

```text
POST /v1/chat
```

## M4

```text
GET /v1/sessions/{session_id}
```

## M6

```text
POST /v1/approvals/{approval_id}
```

Additional public endpoints require a concrete V1 requirement; they are not added speculatively.
