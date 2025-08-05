import numpy as np
from typing import List, Tuple
import logging
import random

from difflib import SequenceMatcher
from sentence_transformers import SentenceTransformer

from .word_database_manager import WordDatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThemeManager(WordDatabaseManager):
    def __init__(self, theme: str):
        """Initialize the theme manager class."""
        super().__init__() # Initialize the word database manager
        self.theme = theme
        
        self.theme_entry_min_char = 5 # TODO: parameterize
        self.theme_entry_max_char = 5 # TODO: parameterize
        
        self.model = SentenceTransformer('all-MiniLM-L6-v2') # TODO: parameterize model
        self.theme_embedding = self.model.encode(theme, convert_to_numpy=True)
        
        self._theme_entries_cache = None # Cache for theme entries to avoid recomputing
    
    
    def find_theme_entries(
        self,
        min_chars: int = None,
        max_chars: int = None,
        min_frequency: int = 20,
        similarity_mode: str = "semantic",
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

        # Filter words
        candidate_words = []
        for length in range(min_chars, max_chars + 1):
            if length in self.words_by_length:
                for word, freq in self.words_by_length[length]:
                    if freq >= min_frequency:
                        candidate_words.append(word)

        logger.info(f"Filtered to {len(candidate_words)} candidates")

        if len(candidate_words) == 0:
            logger.warning("No candidate words found.")
            return []

        # Compute similarities
        if similarity_mode == "semantic":
            word_embeddings = self.model.encode(candidate_words, convert_to_numpy=True, batch_size=64)
            theme_emb = self.theme_embedding
            similarities = np.dot(word_embeddings, theme_emb) / (
                np.linalg.norm(word_embeddings, axis=1) * np.linalg.norm(theme_emb)
            )
            theme_entries = list(zip(candidate_words, similarities.tolist()))

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


    def calculate_similarity(
        self,
        word: str,
        theme: str = None,
        mode: str = "semantic",  # options: 'semantic' or 'string'
        theme_embedding: np.ndarray = None,
    ) -> float:
        """
        Calculate similarity between a word and the theme.

        Args:
            word: Single word to compare.
            theme: Full theme string (required for string similarity).
            mode: 'semantic' (default) or 'string'
            theme_embedding: Precomputed theme embedding (only for semantic)

        Returns:
            Similarity score between 0 and 1.
        """
        if mode == "semantic":
            if theme_embedding is None:
                raise ValueError("theme_embedding must be provided for semantic similarity.")
            word_embedding = self.model.encode(word, convert_to_numpy=True)
            return float(
                np.dot(word_embedding, theme_embedding) /
                (np.linalg.norm(word_embedding) * np.linalg.norm(theme_embedding))
            )
        
        elif mode == "string":
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
        max_chars: int = None
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
                # Weight selection by similarity scores
                words, scores = zip(*filtered_entries)
                selected_word = random.choices(words, weights=scores, k=1)[0]
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
    min_frequency: int = 20,
    similarity_mode: str = "semantic",
    similarity_threshold: float = 0.5,
    weigh_similarity: bool = True,
) -> str:
    """
    Generate a theme entry according to the given theme.
    
    Args:
        theme: The theme that is used to generate the entry.
    
    Returns:
        A theme entry in line with the theme (if available)
    """
    theme_manager = ThemeManager(theme)
    
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
