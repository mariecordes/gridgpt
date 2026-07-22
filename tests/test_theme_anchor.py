"""Offline tests for the theme anchor selector (LLM vetting + two-tier validation).

The LLM call is stubbed; these cover the selection/validation logic only.
"""

from src.gridgpt.theme_anchor import ThemeAnchorSelector


class FakeWordDB:
    """Minimal stand-in exposing the one attribute the selector reads."""

    def __init__(self, words):
        self.word_list_with_frequencies = {w.upper(): 1 for w in words}


def _selector():
    # Construction makes no network call; force the offline/known state per test.
    return ThemeAnchorSelector()


def test_fallback_to_cosine_order_is_db_only(monkeypatch):
    sel = _selector()
    sel.llm_connection_success = False  # no LLM -> use candidate order
    db = FakeWordDB(["PLUTO", "VENUS", "EARTH"])

    anchors = sel.select_anchors(
        "planets", ["PLUTO", "VENUS", "EARTH", "NOTADBWORD"], db, max_words=2,
    )

    assert anchors == ["PLUTO", "VENUS"]  # order preserved, capped at 2, non-DB dropped


def test_llm_hallucination_dropped_when_own_words_off(monkeypatch):
    sel = _selector()
    sel.llm_connection_success = True
    # LLM returns an off-list word that is not in the DB.
    monkeypatch.setattr(sel, "_request_anchor_words", lambda *a, **k: ["PLUTO", "MADEUPWORD"])
    db = FakeWordDB(["PLUTO", "VENUS"])

    anchors = sel.select_anchors("planets", ["PLUTO", "VENUS"], db, allow_llm_words=False)

    assert anchors == ["PLUTO"]  # DB-only guard drops the hallucination


def test_own_words_kept_when_valid_junk_rejected(monkeypatch):
    sel = _selector()
    sel.llm_connection_success = True
    # TACO is a real word not in this DB; ZZZQX is junk.
    monkeypatch.setattr(sel, "_request_anchor_words", lambda *a, **k: ["BREAD", "TACO", "ZZZQX"])
    db = FakeWordDB(["BREAD"])

    anchors = sel.select_anchors("food", ["BREAD"], db, allow_llm_words=True, min_zipf=2.5)

    assert "BREAD" in anchors   # Tier 1 (in DB)
    assert "TACO" in anchors    # Tier 2 (real + common)
    assert "ZZZQX" not in anchors


def test_max_words_and_dedup(monkeypatch):
    sel = _selector()
    sel.llm_connection_success = True
    monkeypatch.setattr(sel, "_request_anchor_words", lambda *a, **k: ["MARS", "MARS", "VENUS", "PLUTO"])
    db = FakeWordDB(["MARS", "VENUS", "PLUTO"])

    anchors = sel.select_anchors("planets", ["MARS", "VENUS", "PLUTO"], db, max_words=2)

    assert anchors == ["MARS", "VENUS"]  # duplicate collapsed, capped at 2


def test_is_valid_own_word():
    v = ThemeAnchorSelector._is_valid_own_word
    assert v("TACO", 2.5, 3, 5) is True       # real, common, length 4
    assert v("ZZZQX", 2.5, 3, 5) is False      # not a word
    assert v("A", 2.5, 3, 5) is False          # too short
    assert v("PIZZA1", 2.5, 3, 5) is False     # non-alpha
    assert v("ABSTRACTED", 2.5, 3, 5) is False  # too long (10)
