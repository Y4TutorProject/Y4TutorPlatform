from math import sqrt

def cosine_similarity(first: list[float], second: list[float]) -> float:
    """Return the cosine similarity of two vectors."""
    first_values = list(first)
    second_values = list(second)
    if len(first_values) != len(second_values):
        raise ValueError("vectors must have the same length")

    first_norm = sqrt(sum(value * value for value in first_values))
    second_norm = sqrt(sum(value * value for value in second_values))
    if first_norm == 0 or second_norm == 0:
        return 0.0

    dot_product = sum(left * right for left, right in zip(first_values, second_values))
    return dot_product / (first_norm * second_norm)


def vector_search(
    query_vector: list[float],
    candidate_vectors: dict[str, list[float]] | list[list[float]],
    candidate_ids: list[str] | None = None,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Rank candidate vectors by cosine similarity to a query vector."""
    if isinstance(candidate_vectors, dict):
        candidates = list(candidate_vectors.items())
    else:
        vectors = list(candidate_vectors)
        ids = list(candidate_ids) if candidate_ids is not None else [str(index) for index in range(len(vectors))]
        if len(ids) != len(vectors):
            raise ValueError("candidate IDs and vectors must have the same length")
        candidates = list(zip(ids, vectors))

    results = [(candidate_id, round(float(cosine_similarity(query_vector, vector))*100)) for candidate_id, vector in candidates]
    results.sort(key=lambda result: result[1], reverse=True)
    return results if top_k is None else results[:top_k]
