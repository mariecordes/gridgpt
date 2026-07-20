import json
from types import SimpleNamespace

from src.gridgpt.clue_manager import ClueGenerator, ClueRetriever, slot_sort_key
from src.gridgpt.word_database_manager import is_reference_clue


class _FakeDB:
    """Minimal stand-in for WordDatabaseManager (only the full clue map is used)."""

    def __init__(self, full=None):
        self.word_database_full = full or {}


def _fake_response(content):
    """Shape a minimal OpenAI chat-completion response object."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _make_generator(create_fn, full=None):
    """Build a ClueGenerator with a fake DB and a scripted LLM (no network)."""
    gen = ClueGenerator(word_db_manager=_FakeDB(full))
    gen.llm_connection_success = True
    gen.llm = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create_fn))
    )
    return gen


def test_slot_sort_key_orders_numerically():
    """'10A' must sort after '2A' numerically, not lexicographically before it."""
    slots = ["10A", "2A", "1A", "10D", "2D", "1D"]
    ordered = sorted(slots, key=slot_sort_key)
    # (number, letter) ordering: numeric first, so directions interleave.
    assert ordered == ["1A", "1D", "2A", "2D", "10A", "10D"]
    # The key property: within each direction the numbers are in order.
    across = [s for s in ordered if s.endswith("A")]
    assert across == ["1A", "2A", "10A"]


def test_is_reference_clue():
    # Cross-references and grid-feature clues are flagged.
    assert is_reference_clue("See 5-Across")
    assert is_reference_clue("With 12-Down")
    assert is_reference_clue("Circled letters, maybe")
    assert is_reference_clue("Shaded squares")
    # Normal clues that merely contain a directional word are not flagged.
    assert not is_reference_clue("Down under, informally")
    assert not is_reference_clue("Across the pond")


def test_get_available_clues_keeps_directional_words():
    """Only true cross-references are dropped; 'Down under' etc. are kept."""

    class _FakeDB:
        word_database_full = {
            "OZ": {"clues": ["Down under, informally", "See 5-Across", "A fair clue"]}
        }

    retriever = ClueRetriever(_FakeDB())
    clues = retriever.get_available_clues("OZ")

    assert "Down under, informally" in clues
    assert "A fair clue" in clues
    assert "See 5-Across" not in clues


def test_is_valid_clue():
    assert ClueGenerator._is_valid_clue("CAT", "Feline pet") is True
    assert ClueGenerator._is_valid_clue("CAT", "A cat toy") is False  # contains the answer
    assert ClueGenerator._is_valid_clue("CAT", "   ") is False  # blank
    assert ClueGenerator._is_valid_clue("CAT", None) is False  # missing


def test_generate_clues_batch_happy_path():
    """One valid JSON response fills every slot in a single call."""
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        assert kwargs.get("response_format") == {"type": "json_object"}
        return _fake_response(json.dumps({"1A": "Feline friend", "1D": "Loyal pet"}))

    gen = _make_generator(create, full={"CAT": {"clues": ["Meower"]}, "DOG": {"clues": ["Barker"]}})
    crossword = {"filled_slots": {"1A": "CAT", "1D": "DOG"}}

    clues = gen.generate_clues_batch(crossword, theme=None)

    assert clues == {"1A": "Feline friend", "1D": "Loyal pet"}
    assert crossword["clues"] == clues
    assert len(calls) == 1  # a single batched call, no per-word fallback


def test_generate_clues_batch_falls_back_per_slot():
    """Invalid (contains answer) or missing slots regenerate individually."""

    def create(**kwargs):
        if kwargs.get("response_format"):
            # 1A contains its own answer (invalid); 1D absent entirely.
            return _fake_response(json.dumps({"1A": "A CAT and dog"}))
        return _fake_response("A fair single clue")  # per-word fallback path

    gen = _make_generator(create, full={"CAT": {"clues": []}, "DOG": {"clues": []}})
    crossword = {"filled_slots": {"1A": "CAT", "1D": "DOG"}}

    clues = gen.generate_clues_batch(crossword, theme=None)

    assert clues == {"1A": "A fair single clue", "1D": "A fair single clue"}


def test_generate_clues_batch_malformed_json_falls_back():
    """A non-JSON batch response falls back to per-word generation."""

    def create(**kwargs):
        if kwargs.get("response_format"):
            return _fake_response("not valid json at all")
        return _fake_response("Per-word clue")

    gen = _make_generator(create, full={"CAT": {"clues": []}})
    crossword = {"filled_slots": {"1A": "CAT"}}

    clues = gen.generate_clues_batch(crossword, theme=None)

    assert clues == {"1A": "Per-word clue"}


def test_generate_clues_batch_without_llm_retrieves():
    """With no LLM connection, clues come from the database, no API call."""
    gen = ClueGenerator(word_db_manager=_FakeDB({"CAT": {"clues": ["Feline pet"]}}))
    gen.llm_connection_success = False
    crossword = {"filled_slots": {"1A": "CAT"}}

    clues = gen.generate_clues_batch(crossword, theme=None)

    assert clues == {"1A": "Feline pet"}
