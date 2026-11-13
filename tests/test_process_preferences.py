import pytest

from dashboard_svc import process_preferences


def test_preference_to_vector_builds_sorted_vectors_and_validates_scores(monkeypatch):
    captured = {}

    def recommendations(request_body):
        captured.update(request_body)
        return [["tutor-1", 85]]

    monkeypatch.setattr(process_preferences, "get_recommendations", recommendations)

    result = process_preferences.preference_to_vector(
        {"visual": 5},
        [{"tutor-1": {"auditory": 3}}],
    )

    assert captured == {
        "student_vector": [0.0, 5.0],
        "tutors": {"tutor-1": [3.0, 0.0]},
    }
    assert result == [("tutor-1", 85.0)]


@pytest.mark.parametrize(
    "student_preferences,tutors",
    [
        (None, []),
        ({}, [{}]),
        ({"visual": float("nan")}, []),
        ({}, [{"tutor-1": {"visual": True}}]),
        ({}, [{"tutor-1": {}}, {"tutor-1": {}}]),
    ],
)
def test_preference_to_vector_rejects_malformed_preferences(
    monkeypatch,
    student_preferences,
    tutors,
):
    def unexpected_request(_):
        pytest.fail("Invalid preferences must be rejected before making a request.")

    monkeypatch.setattr(process_preferences, "get_recommendations", unexpected_request)

    with pytest.raises(ValueError):
        process_preferences.preference_to_vector(student_preferences, tutors)


@pytest.mark.parametrize(
    "matcher_response",
    [
        {"tutor-1": 80},
        [["unknown-tutor", 80]],
        [["tutor-1", float("nan")]],
        [["tutor-1", 80], ["tutor-1", 90]],
        [],
    ],
)
def test_preference_to_vector_rejects_malformed_matcher_response(
    monkeypatch,
    matcher_response,
):
    monkeypatch.setattr(
        process_preferences,
        "get_recommendations",
        lambda _: matcher_response,
    )

    with pytest.raises(ValueError):
        process_preferences.preference_to_vector({}, [{"tutor-1": {}}])
