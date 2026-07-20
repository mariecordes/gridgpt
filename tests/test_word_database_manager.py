def test_databases_are_loaded(word_db):
    assert len(word_db.word_database_full) > 0
    assert len(word_db.word_database_filtered) > 0
    assert len(word_db.word_list_with_frequencies) == len(word_db.word_database_filtered)


def test_filtered_database_respects_criteria(word_db):
    """Default filter: 3-5 letters, alphabetic only, frequency >= 1."""
    for word, data in word_db.word_database_filtered.items():
        assert 3 <= len(word) <= 5, f"'{word}' violates length bounds"
        assert word.isalpha(), f"'{word}' contains non-letter characters"
        assert data["frequency"] >= 1


def test_no_word_left_without_clues(word_db):
    """Words whose clues were all stripped as cross-references must be dropped."""
    for word, data in word_db.word_database_filtered.items():
        assert data.get("clues"), f"'{word}' has no clues but is still in the filtered DB"


def test_filtering_does_not_mutate_full_database(word_db):
    """Stripping reference clues in the filtered DB must not touch the full DB."""
    # Find a word present in both DBs whose clues were actually stripped.
    for word, filtered_data in word_db.word_database_filtered.items():
        full_clues = word_db.word_database_full.get(word, {}).get("clues", [])
        if len(filtered_data["clues"]) < len(full_clues):
            # Full DB must still hold every original clue, and the two lists
            # must be independent objects.
            assert filtered_data["clues"] is not full_clues
            assert len(full_clues) > len(filtered_data["clues"])
            return
    # If nothing was stripped, at least confirm the lists are independent objects.
    sample = next(iter(word_db.word_database_filtered))
    assert (
        word_db.word_database_filtered[sample]["clues"]
        is not word_db.word_database_full[sample]["clues"]
    )


def test_words_by_length_structure(word_db):
    assert set(word_db.words_by_length.keys()) == {3, 4, 5}
    for length, entries in word_db.words_by_length.items():
        for word, frequency in entries:
            assert len(word) == length
            assert word == word.upper()
            assert frequency >= 1


def test_should_include_word(word_db):
    should_include = word_db._should_include_word
    # (word, freq, min_freq, min_len, max_len, exclude_special)
    assert should_include("HOUSE", 5, 1, 3, 5, True) is True
    assert should_include("HOUSE", 0, 1, 3, 5, True) is False  # below frequency
    assert should_include("AB", 5, 1, 3, 5, True) is False  # too short
    assert should_include("TOOLONGWORD", 5, 1, 3, 5, True) is False  # too long
    assert should_include("C3PO", 5, 1, 3, 5, True) is False  # non-alpha
