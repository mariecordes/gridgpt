import random

import pytest

from src.gridgpt.crossword_generator import (
    CrosswordGenerator,
    generate_themed_crossword,
    normalized_themeness,
    _build_theme_weight_fn,
)
from src.gridgpt.template_manager import select_template


def assert_valid_crossword(crossword, template, word_db):
    """Core invariants: all slots filled, grid consistent, no duplicates, DB words only."""
    assert crossword is not None, "generation returned no crossword"

    filled_slots = crossword["filled_slots"]
    assert len(filled_slots) == len(template["slots"]), "not all slots were filled"

    # No duplicate words in the grid
    words = list(filled_slots.values())
    assert len(words) == len(set(words)), "duplicate words in grid"

    for slot in template["slots"]:
        word = filled_slots[slot["id"]]
        assert len(word) == slot["length"]
        # Every word must come from the word database
        assert word in word_db.word_list_with_frequencies, f"'{word}' not in word database"
        # Grid letters must match the slot's word (covers intersection consistency)
        for i, (row, col) in enumerate(slot["cells"]):
            assert crossword["grid"][row][col] == word[i], (
                f"grid mismatch at {(row, col)} for slot {slot['id']}"
            )


@pytest.mark.parametrize(
    "template_id", ["5x5_blocked_corners", "5x5_bottom_pillars", "5x5_diagonal_cut"]
)
def test_generate_crossword_without_theme(template_id, word_db):
    random.seed(42)
    template = select_template(template_id=template_id)
    crossword = generate_themed_crossword(template, word_db_manager=word_db)
    assert_valid_crossword(crossword, template, word_db)


def test_generate_crossword_with_theme_entry(word_db):
    """A directly provided theme entry must end up in the grid (no LLM involved)."""
    random.seed(42)
    template = select_template(template_id="5x5_blocked_corners")
    theme_entry = word_db.words_by_length[5][0][0]

    crossword = generate_themed_crossword(template, theme_entry, word_db_manager=word_db)

    assert_valid_crossword(crossword, template, word_db)
    assert theme_entry in crossword["filled_slots"].values()
    # theme_entries maps slot -> (word, themeness); check the words.
    assert theme_entry in [word for word, _ in crossword["theme_entries"].values()]


def test_validate_theme_entry(word_db):
    generator = CrosswordGenerator(word_db)
    known_word = word_db.words_by_length[5][0][0]

    assert generator.validate_theme_entry(known_word)[0] is True
    assert generator.validate_theme_entry("AB")[0] is False  # too short
    assert generator.validate_theme_entry("C3PO")[0] is False  # non-alpha
    assert generator.validate_theme_entry("ZZZZQ")[0] is False  # not in database


def test_validate_multi_word_theme_entry(word_db):
    """Multi-word entries are valid when every component word is in the DB."""
    generator = CrosswordGenerator(word_db)
    word_a = word_db.words_by_length[3][0][0]
    word_b = word_db.words_by_length[4][0][0]

    assert generator.validate_theme_entry(f"{word_a} {word_b}")[0] is True
    # A space must no longer trip the letters-only check.
    assert generator.validate_theme_entry(f"{word_a} ZZZQX")[0] is False  # unknown word


def test_fill_produces_consistent_assignment(word_db):
    """The backtracking fill returns a complete, duplicate-free assignment."""
    random.seed(3)
    template = select_template(template_id="5x5_diagonal_cut")
    generator = CrosswordGenerator(word_db)

    assignment = generator.fill(template)

    assert assignment is not None
    assert set(assignment) == {s["id"] for s in template["slots"]}
    assert len(set(assignment.values())) == len(assignment)  # no duplicate words


def test_generate_crossword_exhausted_budget_returns_none(word_db):
    """A zero node budget must return None cleanly, not raise."""
    template = select_template(template_id="5x5_blocked_corners")
    result = generate_themed_crossword(
        template, node_budget=0, restart_count=2, word_db_manager=word_db
    )
    assert result is None


def test_normalized_themeness():
    # Raw cosine clipped to the [sim_low, sim_high] band, mapped to 0..1.
    assert normalized_themeness(None, 0.2, 0.5) == 0.0
    assert normalized_themeness(0.2, 0.2, 0.5) == 0.0
    assert normalized_themeness(0.5, 0.2, 0.5) == 1.0
    assert normalized_themeness(0.8, 0.2, 0.5) == 1.0  # clipped above
    assert normalized_themeness(0.35, 0.2, 0.5) == pytest.approx(0.5)


def test_theme_weight_fn():
    # weight = frequency * (1 + boost * themeness)
    weight = _build_theme_weight_fn({"A": 10, "B": 10}, {"A": 0.5, "B": 0.2}, 4.0, 0.2, 0.5)
    assert weight("A") == 50.0   # themeness 1.0 -> 10 * (1 + 4)
    assert weight("B") == 10.0   # themeness 0.0 -> 10 * 1
    assert weight("MISSING") == 1.0  # unknown word: frequency 1, themeness 0


def test_identify_theme_entries_includes_seed_and_on_theme_words(word_db):
    """theme_entries = the pinned seed (always) plus filled words over threshold."""
    generator = CrosswordGenerator(word_db)
    filled = {"1A": "CAT", "1D": "DOG", "2D": "OWL"}
    seed = {"1A": "CAT"}
    sims = {"OWL": 0.5}  # 0.5 -> themeness 1.0 (on-theme); DOG unscored -> 0

    entries = generator._identify_theme_entries(filled, seed, sims, 0.2, 0.5, 0.6)

    # Each entry is (word, themeness): seed CAT unscored -> 0.0, OWL 0.5 -> 1.0, DOG excluded.
    assert entries == {"1A": ("CAT", 0.0), "2D": ("OWL", 1.0)}


def test_identify_theme_entries_empty_without_theme(word_db):
    generator = CrosswordGenerator(word_db)
    assert generator._identify_theme_entries({"1A": "CAT"}, {}, None, 0.2, 0.5, 0.6) == {}


def test_generate_with_theme_similarities_is_valid(word_db):
    """Theme weighting must still produce a fully valid grid (it only reorders)."""
    random.seed(5)
    template = select_template(template_id="5x5_diagonal_cut")
    sims = {word: 0.5 for word in list(word_db.word_frequencies)[:2000]}
    crossword = generate_themed_crossword(template, theme_similarities=sims, word_db_manager=word_db)
    assert_valid_crossword(crossword, template, word_db)


def test_theme_weighting_shifts_words_on_theme(word_db):
    """With weighting, the filled grid contains more of the favored (on-theme) words."""
    template = select_template(template_id="5x5_blocked_corners")
    favored = {word for word in word_db.word_frequencies if word[0] in "AEIOU"}
    sims = {word: 0.5 for word in favored}  # 0.5 -> themeness 1.0

    def count_favored(weighting):
        random.seed(123)  # deterministic comparison
        total = 0
        for _ in range(20):
            crossword = generate_themed_crossword(
                template,
                theme_similarities=sims if weighting else None,
                word_db_manager=word_db,
            )
            total += sum(1 for word in crossword["filled_slots"].values() if word in favored)
        return total

    assert count_favored(weighting=True) > count_favored(weighting=False)


def test_find_suitable_slots_no_candidates_does_not_crash(word_db):
    """An empty candidate set must return [] instead of an IndexError."""
    generator = CrosswordGenerator(word_db)
    template = {
        "slots": [
            {"id": "1A", "length": 3, "direction": "across",
             "start": [0, 0], "cells": [[0, 0], [0, 1], [0, 2]]}
        ],
        # theme_slots references a slot that doesn't exist -> no candidates
        "theme_slots": ["9Z"],
    }
    assert generator.find_suitable_slots(template, "CAT") == []


def test_get_possible_words_respects_constraints(word_db):
    generator = CrosswordGenerator(word_db)
    slot = {"length": 3}
    fixed_letters = {0: "C"}

    possible = generator.get_possible_words(slot, fixed_letters)
    assert len(possible) > 0
    assert all(word[0] == "C" for word, _ in possible)

    # Already used words must be excluded
    used = {possible[0][0]}
    remaining = generator.get_possible_words(slot, fixed_letters, used_words=used)
    assert all(word not in used for word, _ in remaining)


def test_place_theme_entries_consistent_and_skips_bad_length(word_db):
    """Placed anchors sit in matching-length slots with agreeing intersections;
    an anchor with no fitting slot is skipped rather than raising."""
    random.seed(1)
    template = select_template(template_id="5x5_blocked_corners")
    generator = CrosswordGenerator(word_db)

    working = generator.place_theme_entries(template, ["CAT", "TOOLONGWORD"])
    placed = working["filled_slots"]

    assert "TOOLONGWORD" not in placed.values()  # no length-11 slot -> skipped
    slots_by_id = {s["id"]: s for s in template["slots"]}
    cell_letter = {}
    for slot_id, word in placed.items():
        slot = slots_by_id[slot_id]
        assert slot["length"] == len(word)
        for i, (row, col) in enumerate(slot["cells"]):
            # No two placed anchors disagree at a shared cell.
            assert cell_letter.get((row, col), word[i]) == word[i]
            cell_letter[(row, col)] = word[i]


def test_generate_with_theme_entries_places_anchors(word_db):
    """A list of anchors is pinned (best-effort) and shows up as theme entries in
    a fully valid grid."""
    random.seed(2)
    template = select_template(template_id="5x5_diagonal_cut")
    a3 = word_db.words_by_length[3][0][0]
    a5 = word_db.words_by_length[5][0][0]

    crossword = generate_themed_crossword(template, theme_entries=[a5, a3], word_db_manager=word_db)

    assert_valid_crossword(crossword, template, word_db)
    seed_words = set(crossword["seed_entries"].values())
    assert seed_words, "expected at least one anchor to be placed"
    assert seed_words.issubset(set(crossword["filled_slots"].values()))
    # Seeds are recorded as theme entries (each value is a (word, themeness) tuple).
    entry_words = {word for word, _themeness in crossword["theme_entries"].values()}
    assert seed_words.issubset(entry_words)


def test_generate_theme_entries_falls_back_to_valid_grid(word_db):
    """Over-constraining with many same-length anchors must still yield a valid
    grid: placement/fill degrades to fewer anchors (down to none)."""
    random.seed(3)
    template = select_template(template_id="5x5_blocked_corners")
    fives = [w for w, _ in word_db.words_by_length[5][:5]]  # more 5-letter anchors than can co-exist

    crossword = generate_themed_crossword(template, theme_entries=fives, word_db_manager=word_db)

    assert_valid_crossword(crossword, template, word_db)
    # Never pins more anchors than there are slots, and each placed anchor is one we asked for.
    assert set(crossword["seed_entries"].values()).issubset(set(fives))
