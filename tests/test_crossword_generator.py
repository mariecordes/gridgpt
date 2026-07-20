import random

import pytest

from src.gridgpt.crossword_generator import CrosswordGenerator, generate_themed_crossword
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
    assert theme_entry in crossword["theme_entries"].values()


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
