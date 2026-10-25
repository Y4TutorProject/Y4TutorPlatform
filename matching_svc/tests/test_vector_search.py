import pytest

from matching_svc.vector_search import vector_search
from data import student, tutors

def test_ranks_sample_tutors_by_similarity():
    results = vector_search(student, tutors)

    assert [tutor_id for tutor_id, _ in results[:3]] == ["user5", "user7", "user3"]
    assert results[0][1] == pytest.approx(99.60)
    assert all(
        similarity >= next_similarity
        for (_, similarity), (_, next_similarity) in zip(results, results[1:])
    )


def test_limits_sample_results_with_top_k():
    results = vector_search(student, tutors, top_k=3)

    assert len(results) == 3
    assert [tutor_id for tutor_id, _ in results] == ["user5", "user7", "user3"]


def test_ranks_sample_vectors_with_explicit_ids():
    tutor_ids = list(tutors)
    tutor_vectors = list(tutors.values())

    results = vector_search(student, tutor_vectors, tutor_ids, top_k=2)

    assert results[0][0] == "user5"
    assert results[1][0] == "user7"


def test_rejects_mismatched_sample_ids_and_vectors():
    with pytest.raises(ValueError, match="candidate IDs and vectors"):
        vector_search(student, list(tutors.values()), list(tutors)[:-1])
