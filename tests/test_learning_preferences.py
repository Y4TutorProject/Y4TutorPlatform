import uuid
from unittest.mock import Mock

import mongomock
import pytest

from users_svc.Objects.LearningTeachingStyles import LearningTeachingStyles
from users_svc.Objects.User import User
from users_svc.users_dao.MongoUsersDAO import MongoUsersDAO
from users_svc.users_svc import UsersService


@pytest.fixture
def dao(monkeypatch):
    monkeypatch.setattr(
        "users_svc.users_dao.MongoUsersDAO.MongoClient", mongomock.MongoClient,
    )
    return MongoUsersDAO(uri="mongodb://localhost")


def test_scores_persist_and_partial_updates_preserve_existing_scores(dao):
    user = User("student", "hash", "student@example.com")
    dao.add_user(user)
    service = UsersService(dao)
    service.set_learning_preferences(user.id, {LearningTeachingStyles.VISUAL: 5, "auditory": 3})
    service.set_learning_preferences(user.id, {"visual": 2})

    loaded = dao.get_user(user.id)
    assert loaded.preferences == {
        LearningTeachingStyles.VISUAL: 2, LearningTeachingStyles.AUDITORY: 3, LearningTeachingStyles.READING_WRITING: 0,
        LearningTeachingStyles.KINESTHETIC: 0,
    }
    assert dao.collection.find_one({"id": str(user.id)})["preferences"] == {
        "visual": 2, "auditory": 3, "reading_writing": 0, "kinesthetic": 0,
    }


def test_all_enum_styles_persist_and_complete_onboarding(dao):
    user = User("student", "hash", "student@example.com")
    dao.add_user(user)
    scores = {style: score for score, style in enumerate(LearningTeachingStyles, start=1)}

    updated = UsersService(dao).set_learning_preferences(user.id, scores)

    assert updated.preferences_completed is True
    loaded = dao.get_user(user.id)
    assert loaded.preferences == scores
    assert loaded.preferences_completed is True
    assert loaded.to_public_dict()["preferences"] == {
        style.value: score for style, score in scores.items()
    }


@pytest.mark.parametrize("invalid", [
    None, [], {"unknown": 1}, {"verbal": 1}, {"logical": 1},
    {"visual": -1}, {"visual": True},
    {"visual": 1.5}, {"visual": "2"}, {"visual": 11},
])
def test_invalid_preferences_do_not_mutate_or_save_user(invalid):
    user = User("student", "hash", "student@example.com")
    dao = Mock()
    dao.get_user.return_value = user
    with pytest.raises(ValueError):
        UsersService(dao).set_learning_preferences(user.id, invalid)
    assert all(score == 0 for score in user.preferences.values())
    dao.update_user.assert_not_called()


def test_validation_is_atomic():
    user = User("student", "hash", "student@example.com")
    with pytest.raises(ValueError):
        user.set_learning_preferences({"visual": 5, "auditory": -1})
    assert user.preferences[LearningTeachingStyles.VISUAL] == 0


def test_score_boundaries_persist(dao):
    user = User("student", "hash", "student@example.com", preferences={"visual": 5})
    dao.add_user(user)
    UsersService(dao).set_learning_preferences(user.id, {"visual": 0, "auditory": 10})
    loaded = dao.get_user(user.id)
    assert loaded.preferences[LearningTeachingStyles.VISUAL] == 0
    assert loaded.preferences[LearningTeachingStyles.AUDITORY] == 10


def test_legacy_documents_default_all_preferences_to_zero(dao):
    user = User("student", "hash", "student@example.com")
    document = dao._to_document(user)
    del document["preferences"]
    del document["preferences_completed"]
    dao.collection.insert_one(document)
    loaded = dao.get_user(user.id)
    assert len(loaded.preferences) == 4
    assert all(score == 0 for score in loaded.preferences.values())
    assert loaded.preferences_completed is True


def test_missing_user_returns_none(dao):
    assert UsersService(dao).set_learning_preferences(uuid.uuid4(), {"visual": 1}) is None


def test_unmatched_update_returns_none():
    dao = Mock()
    dao.get_user.return_value = User("student", "hash", "student@example.com")
    dao.update_user.return_value = False
    assert UsersService(dao).set_learning_preferences(uuid.uuid4(), {"visual": 1}) is None


@pytest.mark.parametrize("reading_writing,expected", [(None, 7), (4, 4)])
def test_old_preference_documents_load_and_save_with_new_styles(dao, reading_writing, expected):
    user = User("student", "hash", "student@example.com")
    document = dao._to_document(user)
    document["preferences"] = {
        "visual": 8, "auditory": 3, "verbal": 7, "kinesthetic": 6, "logical": 9,
    }
    if reading_writing is not None:
        document["preferences"]["reading_writing"] = reading_writing
    dao.collection.insert_one(document)

    loaded = dao.get_user(user.id)
    assert loaded.to_public_dict()["preferences"] == {
        "visual": 8, "auditory": 3, "reading_writing": expected, "kinesthetic": 6,
    }
    # Reads leave stored data intact; the next update persists the new schema.
    assert dao.collection.find_one({"id": str(user.id)})["preferences"] == document["preferences"]
    updated = UsersService(dao).set_learning_preferences(user.id, {"auditory": 5})
    assert updated.preferences[LearningTeachingStyles.READING_WRITING] == expected
    stored = dao.collection.find_one({"id": str(user.id)})["preferences"]
    assert "verbal" not in stored and "logical" not in stored
    assert stored["auditory"] == 5
