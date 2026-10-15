"""Reciprocal Rank Fusion (RRF) for already-ranked retrieval branches."""


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
    limit: int = 8,
) -> list[tuple[str, float]]:
    """Combine dense and BM25 ranks without mixing incomparable raw scores."""
    if k <= 0 or limit <= 0:
        raise ValueError("RRF k and limit must both be positive.")

    scores: dict[str, float] = {}
    for ranking in rankings:
        seen_in_branch: set[str] = set()
        for position, chunk_id in enumerate(ranking, start=1):
            if chunk_id in seen_in_branch:
                continue
            seen_in_branch.add(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + position)

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
