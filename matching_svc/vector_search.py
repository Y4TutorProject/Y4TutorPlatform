from math import sqrt

def cosine_similarity(first: list[float], second: list[float]) -> float:
    """
    Calculate the cosine similarity between two vectors.

    Args:
        first (list[float]): The first vector.
        second (list[float]): The second vector.

    Returns:
        float: The cosine similarity between the two vectors.
    """
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
    """
    Rank candidate vectors by cosine similarity to a query vector.

    Args:
        query_vector (list[float]): The vector to compare against.
        candidate_vectors (dict[str, list[float]] | list[list[float]]): A dictionary or list of candidate vectors.
        candidate_ids (list[str] | None, optional): A list of IDs for the candidate vectors. Defaults to None.
        top_k (int | None, optional): The number of top results to return. Defaults to None.

    Raises:
        ValueError: Raised when the input parameters are invalid.

    Returns:
        list[tuple[str, float]]: a list of tuples containing candidate IDs and their corresponding cosine similarity scores, sorted in descending order. If top_k is specified, only the top_k results are returned.
    """
    if not isinstance(query_vector, list):
        raise ValueError("query_vector must be a list of floats")
    if not all(isinstance(x, (int, float)) for x in query_vector):
        raise ValueError("query_vector must be a list of floats")
    if isinstance(candidate_vectors, dict):
        candidates = list(candidate_vectors.items())
    else:
        if candidate_ids is None:
            raise ValueError("candidate_ids must be provided when candidate_vectors is a list")
        vectors = list(candidate_vectors)
        ids = list(candidate_ids) if candidate_ids is not None else [str(index) for index in range(len(vectors))]
        if len(ids) != len(vectors):
            raise ValueError("candidate IDs and vectors must have the same length")
        candidates = list(zip(ids, vectors))

    results = [(candidate_id, round(float(cosine_similarity(query_vector, vector))*100)) for candidate_id, vector in candidates]
    results.sort(key=lambda result: result[1], reverse=True)
    return results if top_k is None else results[:top_k]
