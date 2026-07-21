import numpy as np
import pytest

from src.gridgpt.theme_manager import ThemeManager


class _FakeEmbeddingProvider:
    """Controlled stand-in for OpenAIEmbeddingProvider (no API, no cache)."""

    def __init__(self, words, matrix, theme_vec):
        self._words = words
        self._matrix = matrix
        self._theme_vec = theme_vec

    def embed(self, texts):
        return np.array([self._theme_vec], dtype=np.float32)

    def get_word_embeddings(self):
        return self._matrix

    def get_word_list(self):
        return self._words


def _bare_theme_manager(theme, provider):
    """A ThemeManager with a controlled provider, bypassing __init__ (offline)."""
    tm = ThemeManager.__new__(ThemeManager)
    tm.theme = theme
    tm.theme_embedding = None
    tm.embedding_provider = provider
    tm._theme_entries_cache = None
    tm.word_db_manager = None
    return tm


def test_score_all_words_cosine():
    words = ["CAT", "DOG", "CAR"]
    matrix = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float32)
    provider = _FakeEmbeddingProvider(words, matrix, np.array([1.0, 0.0], dtype=np.float32))
    tm = _bare_theme_manager("feline", provider)

    sims = tm.score_all_words()

    assert set(sims) == set(words)
    assert sims["CAT"] == pytest.approx(1.0, abs=1e-6)   # aligned with theme
    assert sims["DOG"] == pytest.approx(0.0, abs=1e-6)   # orthogonal
    assert sims["CAR"] == pytest.approx(1 / 2 ** 0.5, abs=1e-6)  # 45 degrees


def test_score_all_words_without_provider_returns_empty():
    tm = _bare_theme_manager("anything", None)
    assert tm.score_all_words() == {}


def test_calculate_similarity_string_mode():
    tm = _bare_theme_manager("music", None)
    # A substring match scores 1.0; unrelated words stay in [0, 1].
    assert tm.calculate_similarity("music", theme="music", mode="string") == 1.0
    assert 0.0 <= tm.calculate_similarity("xylophone", theme="music", mode="string") <= 1.0
