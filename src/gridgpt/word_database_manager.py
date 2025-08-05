import json
from typing import Dict, List
import logging

from .utils import load_catalog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WordDatabaseManager:
    def __init__(self):
        """Initialize the word database manager with a word database."""
        
        # Get word database path from catalog
        try:
            catalog = load_catalog()
            word_database_path = catalog['word_database']["filtered"]['file_path']
        except Exception as e:
            logger.warning(f"Word database path not found in catalog. Error: {e}")
            raise ValueError("Word database path not found in catalog.")

        self.word_database = self.load_word_database(word_database_path)
        self.words_by_length = self.organize_words_by_length()
    
    
    def load_word_database(self, path: str) -> List[str]:
        """Load the word database from a JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                words = json.load(f)
            logger.info(f"Loaded {len(words)} words from database.")
            return words
        except Exception as e:
            logger.error(f"Error loading word database from {path}: {e}")
            return []
    
         
    def organize_words_by_length(self) -> Dict[int, List[str]]:
        """Organize words by length for faster lookup."""
        words_by_length = {}
        for word, frequency in self.word_database.items():
            length = len(word)
            if length not in words_by_length:
                words_by_length[length] = []
            words_by_length[length].append((word.upper(), frequency))  # Store words in uppercase with their frequency

        logger.info(f"Stored words by length. Words ranging from {min(words_by_length.keys())} to {max(words_by_length.keys())} characters.")
        return words_by_length
    
