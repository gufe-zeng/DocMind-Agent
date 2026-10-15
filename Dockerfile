# M8 optimized Docker layering:
# Only pyproject.toml changes invalidate the expensive runtime dependency layer.
# Subsequent app/scripts/docs changes rebuild only the small project wheel.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml /tmp/docmind-pyproject.toml
RUN python -c "import tomllib; from pathlib import Path; p=tomllib.loads(Path('/tmp/docmind-pyproject.toml').read_text()); Path('/tmp/docmind-deps.txt').write_text('\n'.join(p['project']['dependencies'])+'\n')" \
 && python -m pip install --no-cache-dir "setuptools>=75" wheel \
 && python -m pip install --no-cache-dir -r /tmp/docmind-deps.txt

COPY pyproject.toml README.md ./
COPY app ./app
COPY mcp_server ./mcp_server
COPY eval ./eval
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
COPY scripts/check_m7a.py ./scripts/check_m7a.py
COPY scripts/check_m7b.py ./scripts/check_m7b.py
COPY scripts/check_m7c.py ./scripts/check_m7c.py
COPY scripts/check_m8.py ./scripts/check_m8.py
COPY scripts/check_m9.py ./scripts/check_m9.py
COPY scripts/check_modelscope.py ./scripts/check_modelscope.py
COPY migrations ./migrations
COPY data/samples ./data/samples

# No network or dependency resolution after a source-only change.
RUN python -m pip install --no-deps --no-build-isolation .

# Fail Docker build on missing package installs, psycopg backend or trace support.
RUN cd /tmp && python -c "from eval.rag_metrics import evaluate_retrieval; from eval.agent_eval import evaluate_agent; from eval.system_eval import evaluate_system; from app.observability.tracing import RequestTrace; print('M8 package imports OK')"
RUN python -c "from psycopg import pq; from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver; assert pq.__impl__ == 'binary', pq.__impl__; print('psycopg binary driver OK')"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
