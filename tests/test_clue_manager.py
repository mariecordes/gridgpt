from src.gridgpt.clue_manager import ClueRetriever
from src.gridgpt.word_database_manager import is_reference_clue


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
