import json
from typing import Dict, List
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def combine_and_filter_words(
    input_dir: str = "data/01_raw/crossword_tracker",
    output_file: str = "data/02_intermediary/crossword_word_database.json",
    min_frequency: int = 5,
    min_length: int = 3,
    max_length: int = 15,
    exclude_special_chars: bool = True
) -> Dict[str, int]:
    """
    Combine all letter files into one filtered word database.
    
    Args:
        input_dir: Directory containing crossword_words_<letter>.json files
        output_file: Path for the combined output file
        min_frequency: Minimum frequency threshold for words
        min_length: Minimum word length (characters)
        max_length: Maximum word length (characters)
        exclude_special_chars: Whether to exclude words with special characters
        
    Returns:
        Dictionary of {word: frequency} pairs
    """
    logger.info(f"Starting to combine word files from {input_dir}")
    
    combined_words = {}
    letters_processed = 0
    
    # Process each letter file
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        file_path = os.path.join(input_dir, f"crossword_words_{letter}.json")
        
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Extract words from the letter key
            if letter in data:
                letter_words = data[letter]
                logger.info(f"Processing letter {letter}: {len(letter_words)} words")
                
                for word, freq in letter_words.items():
                    # Apply filters
                    if should_include_word(word, freq, min_frequency, min_length, max_length, exclude_special_chars):
                        # Keep the highest frequency if word appears multiple times
                        if word in combined_words:
                            combined_words[word] = max(combined_words[word], freq)
                        else:
                            combined_words[word] = freq
                
                letters_processed += 1
                
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    
    logger.info(f"Processed {letters_processed} letter files")
    logger.info(f"Combined database contains {len(combined_words)} words")
    
    # Save the combined database
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combined_words, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Word database saved to {output_file}")
    
    # Print statistics
    print_word_statistics(combined_words, min_frequency, min_length, max_length)
    
    return combined_words

def should_include_word(
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

def print_word_statistics(words: Dict[str, int], min_frequency: int, min_length: int, max_length: int):
    """Print statistics about the word database."""
    print(f"\n=== Word Database Statistics ===")
    print(f"Filters applied:")
    print(f"  - Min frequency: {min_frequency}")
    print(f"  - Length range: {min_length}-{max_length} characters")
    print(f"  - Exclude special characters: Yes")
    print(f"\nTotal words: {len(words)}")
    
    # Length distribution
    length_counts = {}
    for word in words.keys():
        length = len(word)
        length_counts[length] = length_counts.get(length, 0) + 1
    
    print(f"\nLength distribution:")
    for length in sorted(length_counts.keys()):
        print(f"  {length} chars: {length_counts[length]} words")
    
    # Frequency distribution
    freq_ranges = [
        (5, 9, "5-9"),
        (10, 19, "10-19"), 
        (20, 49, "20-49"),
        (50, 99, "50-99"),
        (100, 999, "100+")
    ]
    
    print(f"\nFrequency distribution:")
    for min_f, max_f, label in freq_ranges:
        count = sum(1 for freq in words.values() if min_f <= freq <= max_f)
        if count > 0:
            print(f"  {label} times: {count} words")
    
    # Top words by frequency
    print(f"\nTop 20 most frequent words:")
    sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:20]
    for i, (word, freq) in enumerate(sorted_words, 1):
        print(f"  {i:2d}. {word}: {freq}")

def create_word_database_by_length(words: Dict[str, int]) -> Dict[int, List[str]]:
    """Organize words by length for faster crossword generation."""
    words_by_length = {}
    
    for word, freq in words.items():
        length = len(word)
        if length not in words_by_length:
            words_by_length[length] = []
        words_by_length[length].append(word)
    
    # Sort each length group by frequency (highest first)
    for length in words_by_length:
        words_by_length[length].sort(key=lambda w: words[w], reverse=True)
    
    return words_by_length

def save_word_database_formats(
    words: Dict[str, int],
    base_output_path: str = "data/02_intermediary/word_database/word_database"
):
    """Save the word database in multiple useful formats."""
    
    # 1. Full database with frequencies
    full_path = f"{base_output_path}_with_frequencies.json"
    with open(full_path, 'w', encoding='utf-8') as f:
        json.dump(words, f, indent=2, ensure_ascii=False)
    logger.info(f"Full database saved to {full_path}")
    
    # 2. Words organized by length (for crossword generation)
    words_by_length = create_word_database_by_length(words)
    length_path = f"{base_output_path}_by_length.json"
    with open(length_path, 'w', encoding='utf-8') as f:
        json.dump(words_by_length, f, indent=2, ensure_ascii=False)
    logger.info(f"Words by length saved to {length_path}")
    
    # 3. Simple word list (just the words)
    word_list = sorted(words.keys())
    list_path = f"{base_output_path}_list.json"
    with open(list_path, 'w', encoding='utf-8') as f:
        json.dump(word_list, f, indent=2, ensure_ascii=False)
    logger.info(f"Simple word list saved to {list_path}")
    
    return {
        'full': full_path,
        'by_length': length_path,
        'list': list_path
    }
    
def create_word_database():
    """Create the combined word database with default settings."""
    words = combine_and_filter_words(
        min_frequency=5,      # Will be relevant when you have real frequencies
        min_length=3,         # Minimum 3 characters
        max_length=15,        # Maximum 15 characters
        exclude_special_chars=True
    )
    
    # Save in multiple formats
    file_paths = save_word_database_formats(words)
    
    print(f"\n=== Files Created ===")
    for format_name, path in file_paths.items():
        print(f"{format_name}: {path}")
    
    return words
