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


def test_generate_crossword_defaults_to_unthemed(client):
    """Omitting the theme must produce an unthemed puzzle (no theme entry),
    not silently fall back to a default theme that needs an OpenAI call."""
    response = client.post(
        "/api/generate-crossword",
        json={"template": "5x5_blocked_corners", "clueType": "existing"},
    )
    assert response.status_code == 200
    assert response.json()["theme_entries"] == {}


def test_generate_crossword_reports_theme_entries(client, monkeypatch):
    """A themed request returns `theme_entries` (the theme-related filled words the
    generator identified), passed straight through, and no longer a `theme_words` key."""

    class _FakeThemeManager:
        def __init__(self, theme, word_db=None):
            pass

        def score_all_words(self):
            return {"CAT": 0.5, "ARTS": 0.5}
        
        def get_anchor_candidates(self, **kwargs):
            return ["CAT", "ARTS"]

    class _FakeAnchorSelector:
        def select_anchors(self, *args, **kwargs):
            return ["CAT", "ARTS"]

    # The generator now returns theme_entries itself; the route just passes it on.
    fixed_crossword = {
        "grid": [["C", "A", "T"]],
        "filled_slots": {"1A": "CAT", "1D": "ARTS", "2D": "DOG"},
        "theme_entries": {"1A": "CAT", "1D": "ARTS"},
        "slots": [],
    }
    monkeypatch.setattr("src.gridgpt.crossword_builder.ThemeManager", _FakeThemeManager)
    monkeypatch.setattr("src.gridgpt.crossword_builder.ThemeAnchorSelector", lambda: _FakeAnchorSelector())
    monkeypatch.setattr("src.gridgpt.crossword_builder.generate_themed_crossword", lambda *a, **k: dict(fixed_crossword))
    monkeypatch.setattr(
        "src.gridgpt.crossword_builder.retrieve_existing_clues", lambda cw, wdb: {k: "a clue" for k in cw["filled_slots"]}
    )

    response = client.post(
        "/api/generate-crossword",
        json={"template": "5x5_blocked_corners", "theme": "animals", "clueType": "existing"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["theme_entries"] == {"1A": "CAT", "1D": "ARTS"}
    assert set(data["theme_entries"]).issubset(data["filled_slots"])
    assert "theme_words" not in data


def test_generate_crossword_failure_returns_clean_error(client, monkeypatch):
    """A failed fill (None crossword) must surface as a 503, not a 500 crash."""
    monkeypatch.setattr("src.gridgpt.crossword_builder.generate_themed_crossword", lambda *a, **k: None)

    response = client.post(
        "/api/generate-crossword",
        json={"template": "5x5_blocked_corners", "theme": "", "clueType": "existing"},
    )
    assert response.status_code == 503
    assert "try again" in response.json()["detail"].lower()
