import os
import json
import logging
from collections import defaultdict
from typing import Dict, List

from .utils import load_catalog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WordDatabaseManager:
    def __init__(self, min_frequency: int = 1, min_length: int = 3, max_length: int = 5, exclude_special_chars: bool = True):
        """Initialize the word database manager with a word database."""
        
        # Get word database path from catalog
        try:
            catalog = load_catalog()
            db_full_path = catalog['word_database']["full"]['file_path']
            db_filtered_path = catalog['word_database']["filtered"]['file_path']
            db_frequency_path = catalog['word_database']["frequency"]['file_path']

        except Exception as e:
            logger.warning(f"Word database path not found in catalog. Error: {e}")
            raise ValueError("Word database path not found in catalog.")

        self.word_database_full = self.load_word_database(db_full_path)
        self.word_database_filtered = self.filter_word_database(
            self.word_database_full,
            db_filtered_path,
            min_frequency=min_frequency,
            min_length=min_length,
            max_length=max_length,
            exclude_special_chars=exclude_special_chars
        )
        self.word_list_with_frequencies = self.create_word_list_with_frequencies(self.word_database_filtered, db_frequency_path)
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
    
        
    def filter_word_database(
        self,
        word_database: Dict,
        output_file: str,
        min_frequency: int = 5,
        min_length: int = 3,
        max_length: int = 15,
        exclude_special_chars: bool = True
    ) -> Dict:
        """
        Filter the word database and save the result.
        
        Args:
            word_database: Dictionary with full word database
            output_file: Path for the filtered output file
            min_frequency: Minimum frequency threshold for words
            min_length: Minimum word length (characters)
            max_length: Maximum word length (characters)
            exclude_special_chars: Whether to exclude words with special characters
            
        Returns:
            A filtered word database in JSON format
        """
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        logger.info(f"Starting to filter word database with {len(word_database)} words")
        logger.info(f"Filter criteria: min_freq={min_frequency}, length={min_length}-{max_length}, exclude_special={exclude_special_chars}")
        
        filtered_words = {}
        
        for word, data in word_database.items():
            # Extract frequency from the data structure
            frequency = data.get('frequency', 0)
            
            # Apply filtering criteria
            if self._should_include_word(word, frequency, min_frequency, min_length, max_length, exclude_special_chars):
                filtered_words[word] = data
        
        logger.info(f"Filtered database contains {len(filtered_words)} words (removed {len(word_database) - len(filtered_words)} words)")
        
        # Save the filtered database
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(filtered_words, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Filtered word database saved to {output_file}")
        
        return filtered_words
        
    
    def create_word_list_with_frequencies(self, word_database: Dict, output_file: str):
        """Create processed version of the database."""
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        word_frequency_dict = {
            word: data['frequency'] for word, data in word_database.items()
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(word_frequency_dict, f, indent=2)
        logger.info(f"Word list with frequencies saved to {output_file}")
        
        return word_frequency_dict

    def _should_include_word(
        self, 
        word: str, 
        freq: int, 
        min_frequency: int, 
        min_length: int, 
        max_length: int, 
        exclude_special_chars: bool
    ) -> bool:
        """Check if a word should be included based on filtering criteria."""
        
        # Frequency filter
        if freq < min_frequency:
            return False
        
        # Length filter
        if len(word) < min_length or len(word) > max_length:
            return False
        
        # Special characters filter
        if exclude_special_chars:
            # Allow only letters (A-Z)
            if not word.isalpha():
                return False
            
            # Additional check for common problematic patterns
            problematic_patterns = ['*', '?', '/', '\\', '<', '>', ':', '"', '|', '&', '%', '#', '@', '!']
            if any(char in word for char in problematic_patterns):
                return False
        
        return True

    def organize_words_by_length(self) -> Dict[int, List[str]]:
        """Organize words by length for faster lookup."""
        words_by_length = {}
        for word, frequency in self.word_list_with_frequencies.items():
            length = len(word)
            if length not in words_by_length:
                words_by_length[length] = []
            words_by_length[length].append((word.upper(), frequency))  # Store words in uppercase with their frequency

        logger.info(f"Stored words by length. Words ranging from {min(words_by_length.keys())} to {max(words_by_length.keys())} characters.")
        return words_by_length
