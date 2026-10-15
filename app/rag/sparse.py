"""Chinese-oriented character-pattern BM25 for the bounded V1 document collection.

This initial lexical baseline uses CJK character bigrams, preserving terms
without requiring an external word segmenter. It scores stored Qdrant chunk
payloads, not embeddings, using BM25 (k1=1.5, b=0.75).
"""

from collections import Counter
import math
import re


_WORDS = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")


def lexical_tokens(text: str) -> list[str]:
    """Emit Chinese character 2-grams and lowercase Latin/digit terms."""
    tokens: list[str] = []
    for match in _WORDS.finditer(text):
        word = match.group()
        if "\u4e00" <= word[0] <= "\u9fff":
            if len(word) == 1:
                tokens.append(word)
            else:
                tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word.lower())
    return tokens


def bm25_rank(
    query: str,
    documents: dict[str, str],
    *,
    limit: int = 20,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    """Rank chunk IDs with positive-IDF BM25; ignore zero-overlap chunks."""
    if not 0 <= b <= 1 or k1 <= 0 or limit <= 0:
        raise ValueError("Require k1 > 0, 0 <= b <= 1 and limit > 0.")

    terms = set(lexical_tokens(query))
    if not documents or not terms:
        return []

    tokenized = {key: Counter(lexical_tokens(value)) for key, value in documents.items()}
    lengths = {key: sum(counts.values()) for key, counts in tokenized.items()}
    size = len(documents)
    mean_length = max(sum(lengths.values()) / size, 1.0)

    doc_frequency = Counter(
        term for counts in tokenized.values() for term in counts if term in terms
    )
    scores: list[tuple[str, float]] = []
    for chunk_id, counts in tokenized.items():
        doc_length = lengths[chunk_id]
        length_norm = k1 * (1.0 - b + b * doc_length / mean_length)
        score = 0.0
        for term in terms:
            freq = counts.get(term, 0)
            if not freq:
                continue
            df = doc_frequency[term]
            idf = math.log1p((size - df + 0.5) / (df + 0.5))
            score += idf * freq * (k1 + 1.0) / (freq + length_norm)
        if score > 0:
            scores.append((chunk_id, score))

    return sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]
