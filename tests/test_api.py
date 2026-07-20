import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(repo_root_cwd):
    from api.main import app

    return TestClient(app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_templates(client):
    response = client.get("/api/templates")
    assert response.status_code == 200
    templates = response.json()["templates"]
    assert len(templates) >= 3


def test_generate_crossword_without_theme(client):
    """No theme + existing clues: full generation without any OpenAI calls."""
    response = client.post(
        "/api/generate-crossword",
        json={"template": "5x5_blocked_corners", "theme": "", "clueType": "existing"},
    )
    assert response.status_code == 200
    data = response.json()

    assert len(data["grid"]) == 5
    assert all(len(row) == 5 for row in data["grid"])
    assert len(data["filled_slots"]) > 0
    assert set(data["clues"].keys()) == set(data["filled_slots"].keys())
    assert all(isinstance(clue, str) and clue for clue in data["clues"].values())
    assert data["theme_entries"] == {}
    assert data["template_info"]["id"] == "5x5_blocked_corners"


def test_check_solution(client):
    puzzle = {"filled_slots": {"1A": "CAT", "1D": "CAR"}}

    correct = client.post(
        "/api/check-solution",
        json={"puzzle": puzzle, "user_solution": {"1A": "CAT", "1D": "CAR"}},
    )
    assert correct.status_code == 200
    assert correct.json()["correct"] is True
    assert correct.json()["score"] == 2

    wrong = client.post(
        "/api/check-solution",
        json={"puzzle": puzzle, "user_solution": {"1A": "CAT", "1D": "CAP"}},
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["score"] == 1
    assert len(wrong.json()["errors"]) == 1
