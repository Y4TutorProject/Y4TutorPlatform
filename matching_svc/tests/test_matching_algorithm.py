import pytest
import numpy as np
from matching_svc.vector_search import cosine_similarity


def test_identical_vectors():
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)

def test_orthogonal_vectors():
    assert cosine_similarity([1, 0], [0, 1]) == pytest.approx(0.0)

def test_opposite_vectors():
    assert cosine_similarity([1, 2], [-1, -2]) == pytest.approx(-1.0)

def test_known_value():
    expected = 32 / (np.sqrt(14) * np.sqrt(77))
    assert cosine_similarity([1, 2, 3], [4, 5, 6]) == pytest.approx(expected)

def test_scale_invariance():
    assert cosine_similarity([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)

def test_zero_vector_returns_zero():
    assert cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0

def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        cosine_similarity([1, 2, 3], [1, 2])
