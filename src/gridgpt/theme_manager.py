import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
import random

from difflib import SequenceMatcher

from .embedding_provider import OpenAIEmbeddingProvider

from .word_database_manager import WordDatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThemeManager:
    def __init__(self, theme: str, word_db_manager: WordDatabaseManager = None, embedding_model: str = None):
        """Initialize the theme manager class.

        `embedding_model` overrides the active model from parameters.yml (used to
        compare embedding models); None uses the configured default.
        """
        if word_db_manager is None:
            self.word_db_manager = WordDatabaseManager()
        else:
            self.word_db_manager = word_db_manager
            
        self.theme = theme
        
        self.theme_entry_min_char = 5 # TODO: parameterize
        self.theme_entry_max_char = 5 # TODO: parameterize
        
        # Initialize embedding provider from config (lazy creation of word embeddings file if missing)
        try:
            self.embedding_provider = OpenAIEmbeddingProvider.from_config(model=embedding_model)
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAIEmbeddingProvider: {e}")
            self.embedding_provider = None

        self.theme_embedding = None  # will be computed lazily for semantic mode
        
        self._theme_entries_cache = None # Cache for theme entries to avoid recomputing
    
    
    def find_theme_entries(
        self,
        min_chars: int = None,
        max_chars: int = None,
        min_frequency: int = 0,
        similarity_mode: str = "semantic",
        exclude_substring: bool = True,
    ) -> List[Tuple[str, float]]:
        """
        Find all possible theme entries with scoring of theme similarity.
        
        Args:
            min_chars: minimum number of characters of possible theme entries.
            max_chars: maximum number of characters of possible theme entries.
            min_frequency: minimum frequency of possible theme entries; frequency as listed in original word database.
            similarity_mode: mode with which to calculate similarity scores (default: "semantic", other options: "string")
        
        Returns:
            List of possible theme entries with their similarity scores. 
        """
        if min_chars is None:
            min_chars = self.theme_entry_min_char
        if max_chars is None:
            max_chars = self.theme_entry_max_char

        logger.info(f"Finding theme entries for '{self.theme}' using '{similarity_mode}' similarity")

        # Filter words (length + frequency)
        candidate_words = []
        for length in range(min_chars, max_chars + 1):
            if length in self.word_db_manager.words_by_length:
                for word, freq in self.word_db_manager.words_by_length[length]:
                    if freq >= min_frequency:
                        candidate_words.append(word)

        # Optional: exclude words that are substring related to theme (either direction)
        if exclude_substring:
            theme_l = self.theme.lower()
            before_count = len(candidate_words)
            candidate_words = [
                w for w in candidate_words
                if (w.lower() not in theme_l) and (theme_l not in w.lower())
            ]
            logger.info(
                f"Excluded {before_count - len(candidate_words)} candidates due to substring relation with theme '{self.theme}'."
            )

        logger.info(f"Filtered to {len(candidate_words)} candidates")

        if len(candidate_words) == 0:
            logger.warning("No candidate words found.")
            return []

        # Compute similarities
        if similarity_mode == "semantic":
            if self.embedding_provider is None:
                raise RuntimeError("Semantic similarity requested but embedding provider unavailable.")

            # Compute theme embedding if not already
            if self.theme_embedding is None:
                self.theme_embedding = self.embedding_provider.embed([self.theme])[0]

            # Retrieve precomputed word embeddings and corresponding word list
            word_matrix = self.embedding_provider.get_word_embeddings()  # (N, D) fp16
            provider_words = self.embedding_provider.get_word_list()     # list of uppercase words
            index_map = {w: i for i, w in enumerate(provider_words)}

            selected_vectors = []
            filtered_words_for_vectors = []
            for w in candidate_words:
                idx = index_map.get(w.upper())
                if idx is not None:
                    selected_vectors.append(word_matrix[idx])
                    filtered_words_for_vectors.append(w)

            if not selected_vectors:
                logger.warning("No candidate words had precomputed embeddings.")
                return []

            similarities = self._cosine_to_theme(np.array(selected_vectors), self.theme_embedding)
            theme_entries = list(zip(filtered_words_for_vectors, similarities.tolist()))

        elif similarity_mode == "string":
            theme_entries = [
                (word, self.calculate_similarity(word, theme=self.theme, mode="string"))
                for word in candidate_words
            ]
        
        else:
            raise ValueError(f"Unknown similarity mode: {similarity_mode}")

        # Sort and return
        theme_entries.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"Top results: {theme_entries[:5]}")
        self._theme_entries_cache = theme_entries
        return theme_entries


    @staticmethod
    def _cosine_to_theme(word_matrix: np.ndarray, theme_embedding: np.ndarray) -> np.ndarray:
        """Cosine similarity of each row in word_matrix (N, D) to the theme (D,)."""
        matrix = word_matrix if word_matrix.dtype == np.float32 else word_matrix.astype(np.float32)
        theme = theme_embedding.astype(np.float32)
        denom = np.linalg.norm(matrix, axis=1) * np.linalg.norm(theme) + 1e-12
        return (matrix @ theme) / denom


    def score_all_words(self) -> Dict[str, float]:
        """Cosine similarity of every embedded word to the theme.

        Returns {WORD: raw_cosine} over all words in the embedding cache, reusing
        the theme embedding computed for entry selection (no extra API call). One
        matrix multiply over the full ~10k x 1536 matrix, well under 100 ms. Words
        not in the cache are simply absent from the result (treated as 0 downstream).
        """
        if self.embedding_provider is None:
            logger.warning("Embedding provider unavailable; cannot score words against theme.")
            return {}

        if self.theme_embedding is None:
            self.theme_embedding = self.embedding_provider.embed([self.theme])[0]

        word_matrix = np.asarray(self.embedding_provider.get_word_embeddings())  # (N, D)
        provider_words = self.embedding_provider.get_word_list()                 # uppercase, aligned
        similarities = self._cosine_to_theme(word_matrix, self.theme_embedding)
        return {word: float(sim) for word, sim in zip(provider_words, similarities)}


    def prepare_theme(
        self,
        threshold: float = 0.5,
        weigh_similarity: bool = True,
        min_chars: int = None,
        max_chars: int = None,
        min_frequency: int = 0,
    ) -> Tuple[Optional[str], Dict[str, float]]:
        """Pick one seed theme entry and score every word against the theme.

        Both share a single theme embedding (one API call). Returns
        (seed_entry_or_None, {WORD: raw_cosine}).
        """
        self.find_theme_entries(
            min_chars=min_chars, max_chars=max_chars,
            min_frequency=min_frequency, similarity_mode="semantic",
        )
        selected = self.choose_theme_entries(
            number_of_theme_entries=1, threshold=threshold, weigh_similarity=weigh_similarity,
        )
        seed_entry = selected[0] if selected else None
        similarities = self.score_all_words()
        return seed_entry, similarities


    def get_anchor_candidates(
        self, pool_size: int = 30, min_chars: int = 3, max_chars: int = 5, min_frequency: int = 1,
    ) -> List[str]:
        """Top `pool_size` on-theme DB words across the given length range, best
        first, to hand to the anchor selector. Deterministic (unlike
        `choose_theme_entries`, which samples), and spans all usable lengths rather
        than only 5-letter seeds."""
        entries = self.find_theme_entries(
            min_chars=min_chars, max_chars=max_chars,
            min_frequency=min_frequency, similarity_mode="semantic",
        )
        return [word.upper() for word, _score in entries[:pool_size]]


    def calculate_similarity(
        self,
        word: str,
        theme: str = None,
        mode: str = "string",  # only 'string'; semantic scoring goes through score_all_words
    ) -> float:
        """
        Calculate string similarity between a word and the theme.

        Semantic similarity is not handled here: it is computed in bulk against the
        cached embedding matrix (`find_theme_entries` / `score_all_words`), which is
        both faster and avoids a per-word API call.

        Args:
            word: Single word to compare.
            theme: Full theme string.
            mode: 'string' (the only supported mode).

        Returns:
            Similarity score between 0 and 1.
        """
        if mode == "string":
            if theme is None:
                raise ValueError("theme must be provided for string similarity.")
            
            word_lower = word.lower()
            theme_lower = theme.lower()
            
            # Direct substring match
            if word_lower in theme_lower or theme_lower in word_lower:
                return 1.0

            # Basic ratio
            similarity = SequenceMatcher(None, word_lower, theme_lower).ratio()
            
            # Bonus for overlap with theme components
            for t in theme_lower.split():
                if len(t) > 2:
                    similarity = max(similarity, SequenceMatcher(None, word_lower, t).ratio())
            
            return similarity
        
        else:
            raise ValueError(f"Unknown similarity mode: {mode}")

        
    def choose_theme_entries(
        self, 
        number_of_theme_entries: int = 1,
        threshold: float = 0.1,
        weigh_similarity: bool = True,
        min_chars: int = None,
    max_chars: int = None,
    sampling_temperature: float = 0.7,
    ) -> List[str]:
        """
        Choose theme entries randomly from available options.
        
        Args:
            number_of_theme_entries: Number of entries to return (default: 1)
            threshold: Minimum similarity score to consider (default: 0.1)
            weigh_similarity: If True, weight selection by similarity score (default: True)
            min_chars: Minimum character length (default: self.theme_entry_min_char)
            max_chars: Maximum character length (default: self.theme_entry_max_char)
            
        Returns:
            List of selected theme entries
        """
        # Use cached entries if available and parameters match
        if self._theme_entries_cache is None:
            theme_entries = self.find_theme_entries(min_chars, max_chars)
        else:
            theme_entries = self._theme_entries_cache
        
        # Filter by threshold
        filtered_entries = [(word, score) for word, score in theme_entries if score >= threshold]
        
        if not filtered_entries:
            logger.warning(f"No theme entries found above threshold {threshold}")
            return []
        
        logger.info(f"Selecting {number_of_theme_entries} entries from {len(filtered_entries)} candidates above threshold {threshold}")
        
        selected_entries = []
        
        for _ in range(min(number_of_theme_entries, len(filtered_entries))):
            if weigh_similarity:
                # Temperature-based weighting to avoid always picking the absolute top
                words, scores = zip(*filtered_entries)
                scores_arr = np.array(scores, dtype=np.float32)
                # Normalize scores between 0 and 1 for stability
                if scores_arr.size > 1:
                    min_s = scores_arr.min()
                    max_s = scores_arr.max()
                    if max_s - min_s > 1e-9:
                        norm_scores = (scores_arr - min_s) / (max_s - min_s)
                    else:
                        norm_scores = np.ones_like(scores_arr)
                else:
                    norm_scores = np.ones_like(scores_arr)
                # Apply temperature (lower temperature -> more greedy). Use softmax.
                if sampling_temperature <= 0:
                    sampling_temperature = 0.01
                logits = norm_scores / sampling_temperature
                exp_logits = np.exp(logits - logits.max())
                probs = exp_logits / exp_logits.sum()
                selected_word = random.choices(words, weights=probs, k=1)[0]
            else:
                # Uniform random selection
                selected_word = random.choice(filtered_entries)[0]
            
            selected_entries.append(selected_word)
            
            # Remove selected word to avoid duplicates
            filtered_entries = [(w, s) for w, s in filtered_entries if w != selected_word]
            
            if not filtered_entries:
                break
        
        logger.info(f"Selected theme entries: {selected_entries}")
        return selected_entries


def generate_theme_entry(
    theme: str,
    min_chars: int = None,
    max_chars: int = None,
    min_frequency: int = 0,
    similarity_mode: str = "semantic",
    similarity_threshold: float = 0.5,
    weigh_similarity: bool = True,
    word_db_manager: WordDatabaseManager = None,
) -> str:
    """
    Generate a theme entry according to the given theme.
    
    Args:
        theme: The theme that is used to generate the entry.
        word_db_manager: Optional WordDatabaseManager instance to reuse
    
    Returns:
        A theme entry in line with the theme (if available)
    """
    theme_manager = ThemeManager(theme, word_db_manager)
    
    theme_entries = theme_manager.find_theme_entries(
        min_chars=min_chars,
        max_chars=max_chars,
        min_frequency=min_frequency,
        similarity_mode=similarity_mode
    )
    logger.info(f"Found {len(theme_entries)} potential theme entries for theme '{theme}'.")
    
    selected_theme_entries = theme_manager.choose_theme_entries(
        number_of_theme_entries=1, threshold=similarity_threshold, weigh_similarity=weigh_similarity
    )
    
    if len(selected_theme_entries) == 0:
        logger.warning(f"No theme entries found for theme '{theme}'. No theme entry will be used to initialize crossword")
        return None

    selected_theme_entry = selected_theme_entries[0]
    logger.info(f"Selected theme entry for theme '{theme}': {selected_theme_entry}")
    return selected_theme_entry
