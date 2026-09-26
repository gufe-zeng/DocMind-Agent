# Evaluation Plan

Status: **metric set frozen; implementation scheduled for M7**.

## RAG

- Recall@K
- MRR
- Citation Accuracy

## Agent

- Task Success Rate
- Tool Selection Accuracy
- Tool Success Rate
- Average Agent Steps
- Failure Rate

## System

- Agent E2E Latency
- Retrieval Latency
- Rerank Latency
- Tool Latency
- LLM Calls
- Token Usage

Evaluation fixtures live under `eval/datasets/`. Results must be reproducible from a fixed dataset and runnable through `scripts/run_eval.bat` after M7.
