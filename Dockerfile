FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY mcp_server ./mcp_server
COPY eval ./eval
COPY scripts/check_m7a.py ./scripts/check_m7a.py
COPY scripts/check_document_pipeline.py ./scripts/check_document_pipeline.py
COPY scripts/check_m1b.py ./scripts/check_m1b.py
COPY scripts/check_m2a.py ./scripts/check_m2a.py
COPY scripts/check_reranker.py ./scripts/check_reranker.py
COPY scripts/check_m2b.py ./scripts/check_m2b.py
COPY scripts/check_m3a.py ./scripts/check_m3a.py
COPY scripts/check_m3b.py ./scripts/check_m3b.py
COPY scripts/check_m4a.py ./scripts/check_m4a.py
COPY scripts/check_m4b.py ./scripts/check_m4b.py
COPY scripts/check_m4b_resume.py ./scripts/check_m4b_resume.py
COPY scripts/check_m5a.py ./scripts/check_m5a.py
COPY scripts/check_m5b.py ./scripts/check_m5b.py
COPY scripts/check_m6a.py ./scripts/check_m6a.py
COPY scripts/check_m6b.py ./scripts/check_m6b.py
COPY scripts/check_modelscope.py ./scripts/check_modelscope.py
COPY migrations ./migrations
COPY data/samples ./data/samples

RUN pip install --no-cache-dir .

# A direct script execution does not add /app to sys.path; require eval to be installed.
RUN python -c "from eval.rag_metrics import evaluate_retrieval; print('eval package import OK')"

# Fail image build if the psycopg native backend cannot load in slim Linux.
RUN python -c "from psycopg import pq; from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; assert pq.__impl__ == 'binary', pq.__impl__; print('psycopg binary driver OK')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
