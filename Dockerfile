FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY mcp_server ./mcp_server
COPY scripts/check_document_pipeline.py ./scripts/check_document_pipeline.py
COPY scripts/check_m1b.py ./scripts/check_m1b.py
COPY scripts/check_m2a.py ./scripts/check_m2a.py
COPY scripts/check_reranker.py ./scripts/check_reranker.py
COPY scripts/check_m2b.py ./scripts/check_m2b.py
COPY scripts/check_m3a.py ./scripts/check_m3a.py
COPY scripts/check_modelscope.py ./scripts/check_modelscope.py
COPY migrations ./migrations
COPY data/samples ./data/samples

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
